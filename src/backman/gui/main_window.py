"""Hauptfenster mit Job-Liste, Detail-/Snapshots-Tabs und Log-Dock."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DISPLAY_NAME, __version__
from .. import notifications
from ..config import AppConfig, Job, LocalTarget, ScheduleKind, load_config, save_config
from ..engine import (
    ProgressEvent,
    ResticRunner,
    Snapshot,
    SummaryEvent,
    WrongPasswordError,
)
from ..logging_setup import GuiLogQueue
from ..paths import AppPaths
from ..scheduler import (
    SystemctlError,
    daemon_reload,
    disable_timer,
    enable_timer,
    is_systemctl_available,
    job_unit_basename,
    remove_units,
    show_timer_status,
    write_units,
)
from ..scheduler.systemctl import TimerStatus
from .backup_worker import BackupWorker
from .engine_task_worker import EngineTaskWorker
from .job_editor import JobEditorDialog
from .log_panel import LogDock
from .password import forget_password, get_or_prompt_password, prompt_new_password
from .restore_dialog import RestoreDialog
from .snapshots_panel import SnapshotsPanel
from .tray import TrayIcon, is_tray_available
from .usb_watcher import UsbWatcher

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths, log_sink: GuiLogQueue) -> None:
        super().__init__()
        self._paths = paths
        self._config: AppConfig = load_config(paths.config_file)
        self._current_job: Job | None = None

        # Threads/Worker als Member, damit Qt sie nicht zwischendurch GC't
        self._thread: QThread | None = None
        self._worker: BackupWorker | None = None
        self._task_thread: QThread | None = None
        self._task_worker: EngineTaskWorker | None = None
        # Kontext der zuletzt gestarteten Engine-Task, um sie nach dem Aufheben
        # einer Repo-Sperre wiederholen zu können.
        TaskCtx = tuple[str, ResticRunner, Callable[[], object],
                        Callable[[object], None] | None]
        self._last_task: TaskCtx | None = None
        # Task, die nach erfolgreichem Unlock wiederholt werden soll.
        self._pending_retry: TaskCtx | None = None
        # Verhindert eine Endlosschleife, falls auch nach dem Unlock noch
        # eine Sperre gemeldet wird.
        self._unlock_retried = False

        self.setWindowTitle(f"{APP_DISPLAY_NAME} {__version__}")
        self.resize(1040, 680)

        self._build_ui()
        self._build_toolbar()
        self.setStatusBar(QStatusBar())

        self._log_dock = LogDock(log_sink, parent=self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock)

        # Tray-Icon (Hauptfenster minimiert beim Schließen ins Tray)
        self._tray: TrayIcon | None = None
        self._allow_quit = False  # wird auf True gesetzt, wenn echter Quit gewünscht
        if is_tray_available():
            self._tray = TrayIcon(APP_DISPLAY_NAME, parent=self)
            self._tray.show_requested.connect(self._restore_from_tray)
            self._tray.quit_requested.connect(self._quit_from_tray)
            self._tray.show()
        else:
            log.info("System-Tray nicht verfügbar — Close schließt die Anwendung normal")

        # USB-Watcher
        self._usb_watcher = UsbWatcher(parent=self)
        self._usb_watcher.mount_appeared.connect(self._on_mount_appeared)

        self._refresh_jobs()
        log.info("Hauptfenster bereit. %d Jobs geladen.", len(self._config.jobs))

    # ---- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Linke Seite: Job-Liste
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Jobs"))
        self._job_list = QListWidget()
        self._job_list.currentItemChanged.connect(self._on_job_selected)
        left_layout.addWidget(self._job_list, stretch=1)
        splitter.addWidget(left)

        # Rechte Seite: Tabs (Details + Snapshots)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_details_tab(), "Details")

        self._snapshots_panel = SnapshotsPanel()
        self._snapshots_panel.request_refresh.connect(self._on_refresh_snapshots)
        self._snapshots_panel.request_restore.connect(self._on_restore_requested)
        self._snapshots_panel.request_delete.connect(self._on_delete_snapshot_requested)
        self._snapshots_panel.request_check.connect(self._on_check_requested)
        self._tabs.addTab(self._snapshots_panel, "Snapshots")

        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)

    def _build_details_tab(self) -> QWidget:
        widget = QWidget()
        r = QVBoxLayout(widget)

        self._detail_label = QLabel("Kein Job ausgewählt.")
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        r.addWidget(self._detail_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        r.addWidget(self._progress_bar)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        r.addWidget(self._progress_label)

        actions_row = QHBoxLayout()
        self._run_btn = QPushButton("Backup jetzt")
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_backup)
        actions_row.addWidget(self._run_btn)
        actions_row.addStretch(1)
        r.addLayout(actions_row)

        # Schedule-Status-Sektion
        self._schedule_status_label = QLabel("Kein Job ausgewählt.")
        self._schedule_status_label.setTextFormat(Qt.TextFormat.RichText)
        self._schedule_status_label.setWordWrap(True)
        r.addWidget(self._schedule_status_label)

        sched_btns = QHBoxLayout()
        self._refresh_schedule_btn = QPushButton("Timer-Status aktualisieren")
        self._refresh_schedule_btn.clicked.connect(self._refresh_schedule_status)
        self._refresh_schedule_btn.setEnabled(False)
        sched_btns.addWidget(self._refresh_schedule_btn)
        sched_btns.addStretch(1)
        r.addLayout(sched_btns)

        r.addStretch(1)
        return widget

    def _build_toolbar(self) -> None:
        tb = QToolBar("Hauptaktionen")
        tb.setMovable(False)
        self.addToolBar(tb)

        add = QAction("Neuer Job…", self)
        add.triggered.connect(self._on_new_job)
        tb.addAction(add)

        edit = QAction("Bearbeiten…", self)
        edit.triggered.connect(self._on_edit_job)
        tb.addAction(edit)

        delete = QAction("Löschen", self)
        delete.triggered.connect(self._on_delete_job)
        tb.addAction(delete)

    # ---- Job-Liste ---------------------------------------------------

    def _refresh_jobs(self) -> None:
        self._job_list.clear()
        for job in self._config.jobs:
            item = QListWidgetItem(job.name)
            item.setData(Qt.ItemDataRole.UserRole, job.id)
            self._job_list.addItem(item)

    def _on_job_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self._current_job = None
            self._detail_label.setText("Kein Job ausgewählt.")
            self._schedule_status_label.setText("Kein Job ausgewählt.")
            self._refresh_schedule_btn.setEnabled(False)
            self._run_btn.setEnabled(False)
            self._snapshots_panel.clear()
            return
        job_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_job = self._config.get_job(job_id)
        self._render_details()
        self._refresh_schedule_status()
        self._refresh_schedule_btn.setEnabled(self._current_job is not None)
        self._snapshots_panel.clear()
        self._run_btn.setEnabled(self._current_job is not None and not self._is_busy())

    def _render_details(self) -> None:
        if not self._current_job:
            self._detail_label.setText("")
            return
        j = self._current_job
        retention_summary = self._format_retention_summary(j)
        text = (
            f"<b>{j.name}</b><br>"
            f"<b>Ziel:</b> {j.target.path}<br>"
            f"<b>Quellen:</b><br>&nbsp;&nbsp;" + "<br>&nbsp;&nbsp;".join(j.sources) + "<br>"
            f"<b>Tags:</b> {', '.join(j.tags) or '—'}<br>"
            f"<b>Excludes:</b> {', '.join(j.excludes) or '—'}<br>"
            f"<b>Aufbewahrung:</b> {retention_summary}"
        )
        self._detail_label.setText(text)

    @staticmethod
    def _format_retention_summary(j: Job) -> str:
        if not j.retention.is_active():
            return "keine (Snapshots werden nicht automatisch entfernt)"
        bits = []
        for label, val in (
            ("last", j.retention.keep_last),
            ("daily", j.retention.keep_daily),
            ("weekly", j.retention.keep_weekly),
            ("monthly", j.retention.keep_monthly),
            ("yearly", j.retention.keep_yearly),
        ):
            if val > 0:
                bits.append(f"{label}={val}")
        suffix = " (Auto-Prune AN)" if j.auto_prune else " (Auto-Prune aus)"
        return ", ".join(bits) + suffix

    @staticmethod
    def _format_timer_status(j: Job, status: TimerStatus) -> str:
        on_cal = j.schedule.to_on_calendar()
        if on_cal is None:
            return "<b>Zeitplan:</b> Manuell (kein systemd-Timer)"
        parts = [f"<b>Zeitplan:</b> {on_cal}"]
        if not is_systemctl_available():
            parts.append("<i>(systemctl nicht gefunden — Timer-Status nicht verfügbar)</i>")
            return "<br>".join(parts)
        parts.append(
            f"Timer enabled: {'ja' if status.enabled else 'nein'}, "
            f"aktiv: {'ja' if status.active else 'nein'}"
        )
        if status.next_run is not None:
            parts.append(f"Nächster Lauf: {status.next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            parts.append("Nächster Lauf: —")
        if status.last_run is not None:
            res = status.last_result or "?"
            parts.append(
                f"Letzter Lauf: {status.last_run.strftime('%Y-%m-%d %H:%M:%S')} ({res})"
            )
        else:
            parts.append("Letzter Lauf: noch nie")
        return "<br>".join(parts)

    def _refresh_schedule_status(self) -> None:
        if not self._current_job:
            return
        timer_unit = f"{job_unit_basename(self._current_job)}.timer"
        status = show_timer_status(timer_unit)
        self._schedule_status_label.setText(
            self._format_timer_status(self._current_job, status)
        )

    # ---- Job-CRUD ----------------------------------------------------

    def _on_new_job(self) -> None:
        dlg = JobEditorDialog(parent=self)
        if dlg.exec() and (job := dlg.accepted_job()):
            self._config.upsert_job(job)
            self._persist()
            self._sync_schedule_for(job)
            self._refresh_jobs()
            log.info("Job '%s' angelegt", job.name)

    def _on_edit_job(self) -> None:
        if not self._current_job:
            return
        dlg = JobEditorDialog(job=self._current_job, parent=self)
        if dlg.exec() and (job := dlg.accepted_job()):
            self._config.upsert_job(job)
            self._persist()
            self._sync_schedule_for(job)
            self._refresh_jobs()
            self._refresh_schedule_status()
            log.info("Job '%s' aktualisiert", job.name)

    def _on_delete_job(self) -> None:
        if not self._current_job:
            return
        job = self._current_job
        if QMessageBox.question(self, "Job löschen", f"Job '{job.name}' wirklich löschen?") != QMessageBox.StandardButton.Yes:
            return
        self._remove_schedule_for(job)
        self._config.remove_job(job.id)
        self._persist()
        self._current_job = None
        self._refresh_jobs()
        log.info("Job '%s' gelöscht", job.name)

    # ---- Schedule-Sync -----------------------------------------------

    def _sync_schedule_for(self, job: Job) -> None:
        """Schreibt/aktualisiert oder entfernt Unit-Files für den Job.

        Fehler werden geloggt und dem User gemeldet — die Config-Änderung
        bleibt aber bestehen.
        """
        on_calendar = job.schedule.to_on_calendar()
        timer_unit = f"{job_unit_basename(job)}.timer"

        if on_calendar is None:
            self._remove_schedule_for(job)
            return

        try:
            write_units(job, on_calendar)
        except OSError as exc:
            QMessageBox.warning(
                self, "Unit-Dateien", f"Konnte Unit-Files nicht schreiben: {exc}"
            )
            return

        if not is_systemctl_available():
            QMessageBox.information(
                self,
                "systemctl fehlt",
                "Die .service- und .timer-Dateien wurden geschrieben, aber "
                "`systemctl` ist nicht im PATH — der Timer muss manuell aktiviert "
                "werden.",
            )
            return
        try:
            daemon_reload()
            enable_timer(timer_unit, now=True)
            log.info("Timer aktiviert: %s (OnCalendar=%s)", timer_unit, on_calendar)
        except SystemctlError as exc:
            QMessageBox.warning(self, "Timer-Aktivierung fehlgeschlagen", str(exc))

    def _remove_schedule_for(self, job: Job) -> None:
        timer_unit = f"{job_unit_basename(job)}.timer"
        if is_systemctl_available():
            try:
                disable_timer(timer_unit, now=True)
            except SystemctlError as exc:
                log.warning("disable_timer fehlgeschlagen: %s", exc)
        s_existed, t_existed = remove_units(job)
        if (s_existed or t_existed) and is_systemctl_available():
            try:
                daemon_reload()
            except SystemctlError as exc:
                log.warning("daemon-reload fehlgeschlagen: %s", exc)

    def _persist(self) -> None:
        save_config(self._config, self._paths.config_file)

    # ---- Backup-Lauf -------------------------------------------------

    def _is_busy(self) -> bool:
        return self._worker is not None or self._task_worker is not None

    def _run_backup(self) -> None:
        if not self._current_job or self._is_busy():
            return
        job = self._current_job

        runner = self._prepare_runner_for_backup(job)
        if runner is None:
            return
        self._start_backup_worker(job, runner)

    def _prepare_runner_for_backup(self, job: Job) -> ResticRunner | None:
        """Backup-Flow: bei neuem Repo Init-Dialog, sonst bestehendes nutzen."""
        if self._repo_seems_new(job.target):
            return self._init_new_repo(job)
        return self._prepare_runner_existing(job)

    def _prepare_runner_for_read(self, job: Job) -> ResticRunner | None:
        """Lese-Operationen (Snapshots/Restore/Check/Forget): kein Auto-Init."""
        if self._repo_seems_new(job.target):
            QMessageBox.information(
                self,
                "Kein Repository",
                "Für diesen Job wurde noch kein Backup ausgeführt — "
                "es gibt noch nichts in diesem Repository.",
            )
            return None
        return self._prepare_runner_existing(job)

    def _init_new_repo(self, job: Job) -> ResticRunner | None:
        repo_url = job.target.repo_url
        password = prompt_new_password(repo_url, parent=self)
        if not password:
            return None
        runner = ResticRunner(job.target.to_repository(), password=password)
        try:
            runner.init()
        except Exception as exc:  # noqa: BLE001
            forget_password(repo_url)
            QMessageBox.critical(self, "Init fehlgeschlagen", str(exc))
            return None
        log.info("Repository initialisiert: %s", repo_url)
        return runner

    def _prepare_runner_existing(self, job: Job) -> ResticRunner | None:
        repo_url = job.target.repo_url
        password = get_or_prompt_password(repo_url, parent=self)
        if not password:
            return None
        runner = ResticRunner(job.target.to_repository(), password=password)
        try:
            initialized = runner.is_initialized()
        except WrongPasswordError:
            forget_password(repo_url)
            QMessageBox.warning(
                self,
                "Falsches Passwort",
                "Das Passwort für dieses Repository ist falsch. Der "
                "Keyring-Eintrag wurde entfernt — bitte erneut versuchen.",
            )
            return None
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Repo-Prüfung fehlgeschlagen", str(exc))
            return None

        if not initialized:
            reply = QMessageBox.question(
                self,
                "Repository initialisieren?",
                f"Das Verzeichnis '{repo_url}' enthält noch kein "
                "restic-Repository.\n\nJetzt initialisieren?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return None
            try:
                runner.init()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Init fehlgeschlagen", str(exc))
                return None
            log.info("Repository initialisiert: %s", repo_url)
        return runner

    @staticmethod
    def _repo_seems_new(target: LocalTarget) -> bool:
        """Heuristik: lokales Verzeichnis ohne `config`-Datei → neues Repo."""
        repo_dir = Path(target.repo_url)
        return not (repo_dir / "config").exists()

    def _start_backup_worker(self, job: Job, runner: ResticRunner) -> None:
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setVisible(True)
        self._progress_label.setText("Backup läuft…")
        self._run_btn.setEnabled(False)
        self.statusBar().showMessage(f"Backup '{job.name}' läuft…")

        sources = [Path(s) for s in job.sources]
        retention = job.retention.to_forget_policy() if job.auto_prune else None
        worker = BackupWorker(
            runner, sources, tags=job.tags, excludes=job.excludes, retention=retention
        )
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_backup_progress)
        worker.finished_ok.connect(self._on_backup_finished)
        worker.failed.connect(self._on_backup_failed)
        worker.done.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_backup_thread_finished)

        self._worker = worker
        self._thread = thread
        thread.start()
        log.info("Backup '%s' gestartet", job.name)

    def _on_backup_progress(self, event: ProgressEvent) -> None:
        pct = int(round(event.percent_done * 100))
        self._progress_bar.setValue(pct)
        mb_done = event.bytes_done / 1_000_000
        mb_total = event.total_bytes / 1_000_000
        files = f"{event.files_done}/{event.total_files} Dateien"
        size = f"{mb_done:.1f}/{mb_total:.1f} MB"
        self._progress_label.setText(f"{pct}% — {files}, {size}")

    def _on_backup_finished(self, summary: SummaryEvent) -> None:
        log.info(
            "Backup abgeschlossen: snapshot=%s, neu=%d, geändert=%d, +%d Bytes",
            summary.snapshot_id[:8],
            summary.files_new,
            summary.files_changed,
            summary.data_added,
        )
        self._progress_bar.setValue(100)
        self._progress_label.setText(
            f"Fertig. Snapshot {summary.snapshot_id[:8]} — "
            f"{summary.files_new} neu, {summary.files_changed} geändert, "
            f"+{summary.data_added / 1_000_000:.2f} MB"
        )
        self.statusBar().showMessage("Backup abgeschlossen.", 5000)
        job_name = self._current_job.name if self._current_job else "?"
        notifications.notify_success(
            f"Backup '{job_name}' fertig",
            f"Snapshot {summary.snapshot_id[:8]} — {summary.files_new} neu, "
            f"+{summary.data_added / 1_000_000:.2f} MB",
        )
        # Snapshot-Liste automatisch nachladen (kein neuer Passwort-Prompt — Keyring)
        if self._current_job is not None:
            self._on_refresh_snapshots()

    def _on_backup_failed(self, message: str) -> None:
        log.error("Backup fehlgeschlagen: %s", message)
        if "passwort" in message.lower() or "wrong password" in message.lower():
            if self._current_job:
                forget_password(self._current_job.target.repo_url)
        QMessageBox.critical(self, "Backup fehlgeschlagen", message)
        self.statusBar().showMessage("Backup fehlgeschlagen.", 5000)
        job_name = self._current_job.name if self._current_job else "?"
        notifications.notify_failure(f"Backup '{job_name}' fehlgeschlagen", message[:200])

    def _on_backup_thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        self._run_btn.setEnabled(self._current_job is not None)

    # ---- Snapshots ---------------------------------------------------

    def _on_refresh_snapshots(self) -> None:
        if not self._current_job or self._is_busy():
            return
        runner = self._prepare_runner_for_read(self._current_job)
        if runner is None:
            return
        self._snapshots_panel.set_busy(True, "Lade Snapshots…")
        self._run_engine_task(
            name="snapshots",
            runner=runner,
            action=runner.snapshots,
            on_success=self._handle_snapshots_loaded,
        )

    def _handle_snapshots_loaded(self, result: object) -> None:
        snaps: list[Snapshot] = result or []  # type: ignore[assignment]
        self._snapshots_panel.set_snapshots(snaps)
        self.statusBar().showMessage(f"{len(snaps)} Snapshot(s) geladen.", 3000)

    def _on_restore_requested(self, snapshot: Snapshot) -> None:
        if not self._current_job or self._is_busy():
            return
        dlg = RestoreDialog(snapshot, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        target = dlg.target()
        include = dlg.include()

        runner = self._prepare_runner_for_read(self._current_job)
        if runner is None:
            return

        includes = [include] if include else []
        self._snapshots_panel.set_busy(True, "Restore läuft…")
        self.statusBar().showMessage(
            f"Restore von {snapshot.short_id} nach {target}…"
        )
        self._run_engine_task(
            name="restore",
            runner=runner,
            action=lambda: runner.restore(snapshot.id, target, include=includes),
            on_success=lambda _r: self._on_restore_ok(snapshot, target),
        )

    def _on_restore_ok(self, snapshot: Snapshot, target: str) -> None:
        QMessageBox.information(
            self,
            "Restore abgeschlossen",
            f"Snapshot {snapshot.short_id} wurde nach\n{target}\nwiederhergestellt.",
        )
        self.statusBar().showMessage("Restore abgeschlossen.", 5000)

    def _on_delete_snapshot_requested(self, snapshot: Snapshot) -> None:
        if not self._current_job or self._is_busy():
            return
        reply = QMessageBox.question(
            self,
            "Snapshot löschen",
            f"Snapshot {snapshot.short_id} (vom {snapshot.time[:19]}) "
            "endgültig löschen?\n\nDie Daten werden anschließend per "
            "`restic prune` aus dem Repository entfernt.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        runner = self._prepare_runner_for_read(self._current_job)
        if runner is None:
            return

        self._snapshots_panel.set_busy(True, "Snapshot wird gelöscht…")
        self._run_engine_task(
            name="forget_snapshot",
            runner=runner,
            action=lambda: runner.forget_snapshot(snapshot.id, prune=True),
            on_success=lambda _r: self._after_snapshot_deleted(),
        )

    def _after_snapshot_deleted(self) -> None:
        self.statusBar().showMessage("Snapshot gelöscht.", 3000)
        # Snapshot-Liste auffrischen
        self._on_refresh_snapshots()

    def _on_check_requested(self) -> None:
        if not self._current_job or self._is_busy():
            return
        runner = self._prepare_runner_for_read(self._current_job)
        if runner is None:
            return

        self._snapshots_panel.set_busy(True, "Repo-Check läuft…")
        self.statusBar().showMessage("Repo-Check läuft (kann dauern)…")
        self._run_engine_task(
            name="check",
            runner=runner,
            action=runner.check,
            on_success=lambda _r: QMessageBox.information(
                self, "Repo-Check", "Repository ist in Ordnung."
            ),
        )

    # ---- generischer Worker-Helper -----------------------------------

    def _run_engine_task(
        self,
        *,
        name: str,
        runner: ResticRunner,
        action: Callable[[], object],
        on_success: Callable[[object], None] | None = None,
    ) -> None:
        # Kontext merken, damit wir die Task nach einem Unlock wiederholen können.
        self._last_task = (name, runner, action, on_success)

        worker = EngineTaskWorker(name, action)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        if on_success is not None:
            worker.finished_ok.connect(on_success)
        worker.failed.connect(lambda msg, n=name: self._on_task_failed(n, msg))
        worker.done.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_task_thread_finished)

        self._task_worker = worker
        self._task_thread = thread
        thread.start()

    def _on_task_failed(self, name: str, message: str) -> None:
        log.error("%s fehlgeschlagen: %s", name, message)
        lower = message.lower()
        if "passwort" in lower or "wrong password" in lower:
            if self._current_job:
                forget_password(self._current_job.target.repo_url)
        elif ("gesperrt" in lower or "rc=11" in lower or "locked" in lower) \
                and name != "unlock":
            # Repo durch eine zurückgebliebene Sperre blockiert — anbieten,
            # sie aufzuheben und den Vorgang zu wiederholen.
            self._offer_unlock_and_retry()
            return
        QMessageBox.critical(self, f"{name} fehlgeschlagen", message)
        self.statusBar().showMessage(f"{name} fehlgeschlagen.", 5000)

    def _offer_unlock_and_retry(self) -> None:
        """Fragt nach, ob eine zurückgebliebene Repo-Sperre aufgehoben werden soll."""
        task = self._last_task
        if task is None:
            return

        if self._unlock_retried:
            # Wir haben bereits einmal entsperrt und es ist erneut gesperrt —
            # nicht weiter automatisch versuchen.
            self._unlock_retried = False
            QMessageBox.critical(
                self,
                "Repository weiterhin gesperrt",
                "Das Repository ist trotz Entsperren noch gesperrt. Läuft evtl. "
                "ein anderes Backup gleichzeitig? Bitte später erneut versuchen.",
            )
            self.statusBar().showMessage("Repository weiterhin gesperrt.", 5000)
            return

        reply = QMessageBox.question(
            self,
            "Repository gesperrt",
            "Das Repository ist durch eine zurückgebliebene Sperre blockiert — "
            "typischerweise von einem abgebrochenen Vorgang oder einem zu früh "
            "entfernten Laufwerk.\n\nSperre jetzt aufheben und den Vorgang "
            "wiederholen?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Vorgang abgebrochen (Repo gesperrt).", 5000)
            return

        # Erst ausführen, wenn der Thread der fehlgeschlagenen Task aufgeräumt
        # ist (done-Signal kommt nach failed) — sonst kollidieren die Worker.
        QTimer.singleShot(0, self._do_unlock_and_retry)

    def _do_unlock_and_retry(self) -> None:
        task = self._last_task
        if task is None or self._is_busy():
            return
        _name, runner, _action, _on_success = task
        self._unlock_retried = True
        self._pending_retry = task
        self._snapshots_panel.set_busy(True, "Sperre wird aufgehoben…")
        self.statusBar().showMessage("Sperre wird aufgehoben…")

        # Nach dem Unlock die ursprüngliche Task wiederholen — aber erst, wenn
        # der Unlock-Thread vollständig aufgeräumt ist (deshalb singleShot).
        self._run_engine_task(
            name="unlock",
            runner=runner,
            action=runner.unlock,
            on_success=lambda _r: QTimer.singleShot(0, self._run_pending_retry),
        )

    def _run_pending_retry(self) -> None:
        task = self._pending_retry
        self._pending_retry = None
        if task is None or self._is_busy():
            return
        name, runner, action, on_success = task
        self.statusBar().showMessage("Sperre aufgehoben — wiederhole Vorgang…", 3000)

        def on_retry_ok(result: object) -> None:
            self._unlock_retried = False  # erfolgreich → Schutz zurücksetzen
            if on_success is not None:
                on_success(result)

        self._snapshots_panel.set_busy(True, f"{name} wird wiederholt…")
        self._run_engine_task(
            name=name, runner=runner, action=action, on_success=on_retry_ok
        )

    def _on_task_thread_finished(self) -> None:
        self._task_worker = None
        self._task_thread = None
        self._snapshots_panel.set_busy(False)
        self._run_btn.setEnabled(self._current_job is not None)

    # ---- Tray + USB --------------------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Wenn ein Tray vorhanden ist: Fenster minimieren statt schließen.

        So bleibt der USB-Watcher aktiv und Timer-Notifications kommen
        weiter durch. Echter Quit nur über das Tray-Menü oder File → Quit.
        """
        if self._tray and not self._allow_quit:
            self.hide()
            event.ignore()
            # Einmalig im Statusbar-Stil als Hinweis
            self._tray._tray.showMessage(
                APP_DISPLAY_NAME,
                "Läuft im Hintergrund weiter. Über das Tray-Icon zurückholen.",
                msecs=4000,
            )
            return
        super().closeEvent(event)

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._allow_quit = True
        if self._tray:
            self._tray.hide()
        self.close()
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _on_mount_appeared(self, mount_path: str) -> None:
        """Prüft, ob ein Job-Ziel unter dem neuen Mount liegt, und informiert."""
        mount = Path(mount_path).resolve()
        for job in self._config.jobs:
            target = Path(job.target.repo_url).resolve()
            try:
                target.relative_to(mount)
            except ValueError:
                continue
            log.info("Job-Ziel auf neuem Mount erkannt: %s (Job '%s')", target, job.name)
            notifications.notify(
                f"Back-Man: Ziel-Laufwerk verfügbar",
                f"Job '{job.name}': Ziel {target} ist gemountet. "
                "Du kannst jetzt das Backup starten.",
            )
