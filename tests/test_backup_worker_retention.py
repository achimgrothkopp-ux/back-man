"""BackupWorker mit Retention läuft auch echtes restic dagegen — verifiziert,
dass die forget-Phase nach dem Backup tatsächlich Snapshots entfernt."""

from __future__ import annotations

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(
    shutil.which("restic") is None, reason="restic-Binary nicht im PATH"
)

from backman.engine import ResticRunner, local_repo  # noqa: E402
from backman.engine.restic import ForgetPolicy  # noqa: E402
from backman.gui.backup_worker import BackupWorker  # noqa: E402


def test_worker_runs_retention_after_backup(qt_app, tmp_path):
    repo_path = tmp_path / "repo"
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a", encoding="utf-8")

    runner = ResticRunner(local_repo(repo_path), password="x")
    runner.init()
    # Bestehende zwei Snapshots vorlegen
    runner.backup([src])
    (src / "b.txt").write_text("b", encoding="utf-8")
    runner.backup([src])
    assert len(runner.snapshots()) == 2

    # Worker macht einen dritten Snapshot und wendet danach keep_last=1 an
    policy = ForgetPolicy(keep_last=1)
    worker = BackupWorker(runner, [src], retention=policy)
    summaries: list = []
    failures: list = []
    worker.finished_ok.connect(summaries.append)
    worker.failed.connect(failures.append)
    worker.run()

    assert failures == []
    assert len(summaries) == 1
    remaining = runner.snapshots()
    assert len(remaining) == 1
    assert remaining[0].id == summaries[0].snapshot_id


def test_worker_without_retention_keeps_all(qt_app, tmp_path):
    repo_path = tmp_path / "repo"
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.txt").write_text("x", encoding="utf-8")

    runner = ResticRunner(local_repo(repo_path), password="x")
    runner.init()
    runner.backup([src])
    assert len(runner.snapshots()) == 1

    worker = BackupWorker(runner, [src], retention=None)
    summaries: list = []
    worker.finished_ok.connect(summaries.append)
    worker.run()

    # 2 Snapshots: der alte + der neue. Retention=None → nichts entfernt.
    assert len(runner.snapshots()) == 2
    assert len(summaries) == 1
