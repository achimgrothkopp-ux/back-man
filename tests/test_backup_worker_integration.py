"""End-to-End-Test: BackupWorker mit echtem restic + Qt-Signal-Capture."""

from __future__ import annotations

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(
    shutil.which("restic") is None, reason="restic-Binary nicht im PATH"
)

from backman.engine import ProgressEvent, ResticRunner, SummaryEvent, local_repo  # noqa: E402
from backman.gui.backup_worker import BackupWorker  # noqa: E402


def test_backup_worker_emits_summary_via_signals(qt_app, tmp_path):
    repo_path = tmp_path / "repo"
    src = tmp_path / "src"
    src.mkdir()
    (src / "file.txt").write_text("Back-Man-Test", encoding="utf-8")

    runner = ResticRunner(local_repo(repo_path), password="x")
    runner.init()

    progress_events: list[ProgressEvent] = []
    summary_holder: list[SummaryEvent] = []
    failures: list[str] = []
    done_count = [0]

    worker = BackupWorker(runner, [src], tags=["unittest"])
    worker.progress.connect(progress_events.append)
    worker.finished_ok.connect(summary_holder.append)
    worker.failed.connect(failures.append)
    worker.done.connect(lambda: done_count.__setitem__(0, done_count[0] + 1))

    worker.run()  # blockierend, im Hauptthread (Signale werden direkt zugestellt)

    assert failures == []
    assert done_count[0] == 1
    assert len(summary_holder) == 1
    summary = summary_holder[0]
    assert isinstance(summary, SummaryEvent)
    assert summary.snapshot_id
    assert summary.files_new >= 1
    # Progress kann auch leer sein bei winzigen Backups — nicht erzwingen.
    assert all(isinstance(p, ProgressEvent) for p in progress_events)


def test_backup_worker_failure_emits_failed(qt_app, tmp_path):
    # Repo gar nicht initialisiert → backup wird fehlschlagen
    repo_path = tmp_path / "leeres-repo"
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.txt").write_text("x", encoding="utf-8")

    runner = ResticRunner(local_repo(repo_path), password="x")

    failures: list[str] = []
    successes: list = []
    done_count = [0]

    worker = BackupWorker(runner, [src])
    worker.failed.connect(failures.append)
    worker.finished_ok.connect(successes.append)
    worker.done.connect(lambda: done_count.__setitem__(0, done_count[0] + 1))

    worker.run()

    assert successes == []
    assert len(failures) == 1
    assert done_count[0] == 1
