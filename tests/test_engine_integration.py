"""End-to-End-Tests gegen ein echtes restic-Binary.

Wird automatisch übersprungen, wenn restic im PATH fehlt.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backman.engine import (
    ProgressEvent,
    ResticError,
    ResticRunner,
    SummaryEvent,
    WrongPasswordError,
    local_repo,
)
from backman.engine.restic import ForgetPolicy

pytestmark = pytest.mark.skipif(
    shutil.which("restic") is None, reason="restic-Binary nicht im PATH"
)


@pytest.fixture
def repo_path(tmp_path) -> Path:
    return tmp_path / "repo"


@pytest.fixture
def source_tree(tmp_path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.txt").write_text("Hallo Back-Man\n", encoding="utf-8")
    (src / "data.bin").write_bytes(b"\x00\x01\x02\x03" * 256)
    sub = src / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested\n", encoding="utf-8")
    return src


@pytest.fixture
def runner(repo_path) -> ResticRunner:
    repo = local_repo(repo_path)
    return ResticRunner(repo=repo, password="testpass")


def test_init_then_snapshots_empty(runner):
    runner.init()
    assert runner.snapshots() == []


def test_init_rejected_when_password_wrong(repo_path):
    good = ResticRunner(repo=local_repo(repo_path), password="right")
    good.init()
    bad = ResticRunner(repo=local_repo(repo_path), password="wrong")
    with pytest.raises(WrongPasswordError):
        bad.snapshots()


def test_backup_emits_progress_and_summary(runner, source_tree):
    runner.init()

    events: list = []
    summary = runner.backup([source_tree], tags=["test"], on_event=events.append)

    assert isinstance(summary, SummaryEvent)
    assert summary.snapshot_id
    assert summary.files_new >= 3  # hello.txt, data.bin, sub/nested.txt
    # mindestens das Summary-Event ist drin; ProgressEvents sind möglich
    assert any(isinstance(e, SummaryEvent) for e in events)
    assert all(isinstance(e, (ProgressEvent, SummaryEvent)) for e in events)


def test_snapshots_listed_after_backup(runner, source_tree):
    runner.init()
    summary = runner.backup([source_tree], tags=["mytag"])

    snaps = runner.snapshots()
    assert len(snaps) == 1
    s = snaps[0]
    assert s.id == summary.snapshot_id
    assert "mytag" in s.tags
    assert any(str(source_tree) in p for p in s.paths)


def test_restore_recreates_files(runner, source_tree, tmp_path):
    runner.init()
    summary = runner.backup([source_tree])

    restore_target = tmp_path / "restored"
    restore_target.mkdir()
    runner.restore(summary.snapshot_id, restore_target)

    # restic restored to <target>/<absolute-source-path>
    restored_file = restore_target / source_tree.relative_to(source_tree.anchor) / "hello.txt"
    assert restored_file.read_text(encoding="utf-8") == "Hallo Back-Man\n"


def test_forget_with_keep_last(runner, source_tree):
    runner.init()
    runner.backup([source_tree])
    # Eine zweite Quelle für einen zweiten Snapshot
    (source_tree / "second.txt").write_text("v2\n", encoding="utf-8")
    runner.backup([source_tree])

    assert len(runner.snapshots()) == 2
    runner.forget(ForgetPolicy(keep_last=1), prune=True)
    assert len(runner.snapshots()) == 1


def test_check_passes_on_fresh_repo(runner, source_tree):
    runner.init()
    runner.backup([source_tree])
    assert runner.check() is True


def test_init_fails_on_existing_repo(runner):
    runner.init()
    with pytest.raises(ResticError):
        runner.init()


def test_forget_policy_requires_at_least_one_keep():
    with pytest.raises(ValueError):
        ForgetPolicy().to_args()


def test_backup_without_sources_raises(runner):
    runner.init()
    with pytest.raises(ValueError):
        runner.backup([])
