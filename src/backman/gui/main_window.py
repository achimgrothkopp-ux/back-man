"""Hauptfenster mit Job-Liste, Detail-Panel, Backup-Button und Log-Dock."""

from __future__ import annotations

import logging
from pathlib import Path

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
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DISPLAY_NAME, __version__
from ..config import AppConfig, Job, LocalTarget, load_config, save_config
from ..engine import (
    ProgressEvent,
    ResticRunner,
    SummaryEvent,
    WrongPasswordError,
)
from ..logging_setup import GuiLogQueue
from ..paths import AppPaths
from .backup_worker import BackupWorker
from .job_editor import JobEditorDialog
from .log_panel import LogDock
from .password import forget_password, get_or_prompt_password, prompt_new_password

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths, log_sink: GuiLogQueue) -> None:
        super().__init__()
        self._paths = paths
        self._config: AppConfig = load_config(paths.config_file)
        self._current_job: Job | None = None
        self._thread: QThread | None = None
        self._worker: BackupWorker | None = None

        self.setWindowTitle(f"{APP_DISPLAY_NAME} {__version__}")
        self.resize(960, 640)

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

        # Rechte Seite: Details + Aktionen
        right = QWidget()
        r = QVBoxLayout(right)

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

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

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
            return
        job_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_job = self._config.get_job(job_id)
        self._render_details()
        self._run_btn.setEnabled(self._current_job is not None and self._worker is None)

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

    def _run_backup(self) -> None:
        if not self._current_job or self._worker is not None:
            return
        job = self._current_job

        runner = self._prepare_runner(job)
        if runner is None:
            return

        # Worker starten
        self._start_worker(job, runner)

    def _prepare_runner(self, job: Job) -> ResticRunner | None:
        """Stellt Passwort und Repo-Initialisierung sicher.

        Logik:
          - Wenn Repo (lokal) noch nicht existiert: Neues-Passwort-Dialog
            (mit Bestätigung), dann `runner.init()`.
          - Wenn Repo existiert: Passwort aus Keyring oder normaler Prompt,
            dann `is_initialized()` zur Validierung.
        """
        repo_url = job.target.repo_url
        is_new = self._repo_seems_new(job.target)

        if is_new:
            password = prompt_new_password(repo_url, parent=self)
            if not password:
                return None
            runner = ResticRunner(job.target.to_repository(), password=password)
            try:
                runner.init()
            except Exception as exc:  # noqa: BLE001
                # Repo-Anlage fehlgeschlagen → frischen Keyring-Eintrag entfernen
                forget_password(repo_url)
                QMessageBox.critical(self, "Init fehlgeschlagen", str(exc))
                return None
            log.info("Repository initialisiert: %s", repo_url)
            return runner

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
            # Verzeichnis existiert, aber kein restic-Repo darin
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
        from pathlib import Path

        repo_dir = Path(target.repo_url)
        return not (repo_dir / "config").exists()

    def _start_worker(self, job: Job, runner: ResticRunner) -> None:

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
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.done.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._worker = worker
        self._thread = thread
        thread.start()
        log.info("Backup '%s' gestartet", job.name)

    def _on_progress(self, event: ProgressEvent) -> None:
        pct = int(round(event.percent_done * 100))
        self._progress_bar.setValue(pct)
        mb_done = event.bytes_done / 1_000_000
        mb_total = event.total_bytes / 1_000_000
        files = f"{event.files_done}/{event.total_files} Dateien"
        size = f"{mb_done:.1f}/{mb_total:.1f} MB"
        self._progress_label.setText(f"{pct}% — {files}, {size}")

    def _on_finished(self, summary: SummaryEvent) -> None:
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

    def _on_failed(self, message: str) -> None:
        log.error("Backup fehlgeschlagen: %s", message)
        # WrongPassword: Keyring-Eintrag für künftige Läufe löschen
        if "passwort" in message.lower() or "wrong password" in message.lower():
            if self._current_job:
                forget_password(self._current_job.target.repo_url)
        QMessageBox.critical(self, "Backup fehlgeschlagen", message)
        self.statusBar().showMessage("Backup fehlgeschlagen.", 5000)

    def _on_thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        self._run_btn.setEnabled(self._current_job is not None)
        # Progressbar nicht sofort verstecken — letzte Meldung sichtbar lassen.
