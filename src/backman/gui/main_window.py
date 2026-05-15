"""Hauptfenster mit Job-Liste, Detail-/Snapshots-Tabs und Log-Dock."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QThread
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
from ..config import AppConfig, Job, LocalTarget, load_config, save_config
from ..engine import (
    ProgressEvent,
    ResticRunner,
    Snapshot,
    SummaryEvent,
    WrongPasswordError,
)
from ..logging_setup import GuiLogQueue
from ..paths import AppPaths
from .backup_worker import BackupWorker
from .engine_task_worker import EngineTaskWorker
from .job_editor import JobEditorDialog
from .log_panel import LogDock
from .password import forget_password, get_or_prompt_password, prompt_new_password
from .restore_dialog import RestoreDialog
from .snapshots_panel import SnapshotsPanel

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

        self.setWindowTitle(f"{APP_DISPLAY_NAME} {__version__}")
        self.resize(1040, 680)

        self._build_ui()
        self._build_toolbar()
        self.setStatusBar(QStatusBar())

        self._log_dock = LogDock(log_sink, parent=self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock)

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
            self._run_btn.setEnabled(False)
            self._snapshots_panel.clear()
            return
        job_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_job = self._config.get_job(job_id)
        self._render_details()
        self._snapshots_panel.clear()
        self._run_btn.setEnabled(self._current_job is not None and not self._is_busy())

    def _render_details(self) -> None:
        if not self._current_job:
            self._detail_label.setText("")
            return
        j = self._current_job
        text = (
            f"<b>{j.name}</b><br>"
            f"<b>Ziel:</b> {j.target.path}<br>"
            f"<b>Quellen:</b><br>&nbsp;&nbsp;" + "<br>&nbsp;&nbsp;".join(j.sources) + "<br>"
            f"<b>Tags:</b> {', '.join(j.tags) or '—'}<br>"
            f"<b>Excludes:</b> {', '.join(j.excludes) or '—'}"
        )
        self._detail_label.setText(text)

    # ---- Job-CRUD ----------------------------------------------------

    def _on_new_job(self) -> None:
        dlg = JobEditorDialog(parent=self)
        if dlg.exec() and (job := dlg.accepted_job()):
            self._config.upsert_job(job)
            self._persist()
            self._refresh_jobs()
            log.info("Job '%s' angelegt", job.name)

    def _on_edit_job(self) -> None:
        if not self._current_job:
            return
        dlg = JobEditorDialog(job=self._current_job, parent=self)
        if dlg.exec() and (job := dlg.accepted_job()):
            self._config.upsert_job(job)
            self._persist()
            self._refresh_jobs()
            log.info("Job '%s' aktualisiert", job.name)

    def _on_delete_job(self) -> None:
        if not self._current_job:
            return
        name = self._current_job.name
        if QMessageBox.question(self, "Job löschen", f"Job '{name}' wirklich löschen?") != QMessageBox.StandardButton.Yes:
            return
        self._config.remove_job(self._current_job.id)
        self._persist()
        self._current_job = None
        self._refresh_jobs()
        log.info("Job '%s' gelöscht", name)

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
        worker = BackupWorker(runner, sources, tags=job.tags, excludes=job.excludes)
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
        if "passwort" in message.lower() or "wrong password" in message.lower():
            if self._current_job:
                forget_password(self._current_job.target.repo_url)
        QMessageBox.critical(self, f"{name} fehlgeschlagen", message)
        self.statusBar().showMessage(f"{name} fehlgeschlagen.", 5000)

    def _on_task_thread_finished(self) -> None:
        self._task_worker = None
        self._task_thread = None
        self._snapshots_panel.set_busy(False)
        self._run_btn.setEnabled(self._current_job is not None)
