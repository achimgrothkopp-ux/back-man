"""End-to-End-Tests gegen ein echtes restic-Binary.

Wird automatisch übersprungen, wenn restic im PATH fehlt.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backman.engine import (
    ProgressEvent,
    RepoNotInitializedError,
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


def test_is_initialized_false_for_missing_repo(tmp_path):
    """Repo gibt's gar nicht — is_initialized() muss False liefern,
    NICHT WrongPasswordError werfen (das war ein realer Bug, siehe
    GUI-Report 2026-05-15)."""
    runner = ResticRunner(local_repo(tmp_path / "kein-repo"), password="x")
    assert runner.is_initialized() is False


def test_snapshots_on_missing_repo_raises_not_initialized(tmp_path):
    runner = ResticRunner(local_repo(tmp_path / "ghost"), password="x")
    with pytest.raises(RepoNotInitializedError):
        runner.snapshots()


def test_wrong_password_still_distinct_from_missing(tmp_path):
    repo = tmp_path / "repo"
    ResticRunner(local_repo(repo), password="right").init()
    bad = ResticRunner(local_repo(repo), password="wrong")
    with pytest.raises(WrongPasswordError):
        bad.is_initialized()


def test_forget_snapshot_removes_only_that_snapshot(runner, source_tree):
    runner.init()
    first = runner.backup([source_tree])
    (source_tree / "another.txt").write_text("v2", encoding="utf-8")
    second = runner.backup([source_tree])
    assert len({first.snapshot_id, second.snapshot_id}) == 2

    runner.forget_snapshot(first.snapshot_id, prune=True)
    remaining = runner.snapshots()
    assert len(remaining) == 1
    assert remaining[0].id == second.snapshot_id


def test_forget_snapshot_rejects_empty_id(runner):
    with pytest.raises(ValueError):
        runner.forget_snapshot("")


def test_unlock_is_noop_on_unlocked_repo(runner, source_tree):
    """unlock() darf auf einem nicht gesperrten Repo problemlos durchlaufen."""
    runner.init()
    runner.backup([source_tree])
    runner.unlock()  # keine stale locks → kein Fehler
    runner.unlock(remove_all=True)
    # Repo weiterhin nutzbar
    assert len(runner.snapshots()) == 1
