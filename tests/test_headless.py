"""Tests für den Headless-Modus (back-man --run-job <id>)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backman import keyring_store
from backman.config import AppConfig, Job, LocalTarget, RetentionPolicy, save_config
from backman.headless import (
    EXIT_JOB_NOT_FOUND,
    EXIT_OK,
    EXIT_PASSWORD_MISSING,
    EXIT_USAGE,
    main,
    run_job_headless,
)


pytestmark = pytest.mark.skipif(
    shutil.which("restic") is None, reason="restic-Binary nicht im PATH"
)


@pytest.fixture
def xdg_isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def in_memory_keyring(monkeypatch):
    """Hängt ein In-Memory-Keyring ein, sodass Tests nicht den echten
    Secret Service anfassen."""
    import keyring as kr
    from keyring.backend import KeyringBackend
    from keyring.errors import PasswordDeleteError

    class Mem(KeyringBackend):
        priority = 1

        def __init__(self) -> None:
            self.store: dict[tuple[str, str], str] = {}

        def get_password(self, service, username):
            return self.store.get((service, username))

        def set_password(self, service, username, password):
            self.store[(service, username)] = password

        def delete_password(self, service, username):
            try:
                del self.store[(service, username)]
            except KeyError:
                raise PasswordDeleteError("not found")

    previous = kr.get_keyring()
    backend = Mem()
    kr.set_keyring(backend)
    try:
        yield backend
    finally:
        kr.set_keyring(previous)


def test_main_usage_without_args():
    assert main([]) == EXIT_USAGE


def test_main_usage_unknown_flag():
    assert main(["--foo"]) == EXIT_USAGE


def test_run_job_missing_id(xdg_isolated, in_memory_keyring):
    save_config(AppConfig(), Path(xdg_isolated) / "cfg" / "backman" / "config.toml")
    assert run_job_headless("nope") == EXIT_JOB_NOT_FOUND


def test_run_job_missing_password(xdg_isolated, in_memory_keyring, tmp_path):
    job = Job(name="P", sources=[str(tmp_path / "src")], target=LocalTarget(path=str(tmp_path / "repo")))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.txt").write_text("x", encoding="utf-8")
    cfg_path = Path(xdg_isolated) / "cfg" / "backman" / "config.toml"
    save_config(AppConfig(jobs=[job]), cfg_path)
    # Kein Keyring-Eintrag → EXIT_PASSWORD_MISSING
    assert run_job_headless(job.id) == EXIT_PASSWORD_MISSING


def test_run_job_full_success(xdg_isolated, in_memory_keyring, tmp_path):
    # Pre-init repo
    from backman.engine import ResticRunner, local_repo
    repo_path = tmp_path / "repo"
    src_path = tmp_path / "src"
    src_path.mkdir()
    (src_path / "file.txt").write_text("data", encoding="utf-8")
    ResticRunner(local_repo(repo_path), password="pw").init()

    job = Job(
        name="Auto",
        sources=[str(src_path)],
        target=LocalTarget(path=str(repo_path)),
    )
    cfg_path = Path(xdg_isolated) / "cfg" / "backman" / "config.toml"
    save_config(AppConfig(jobs=[job]), cfg_path)

    # Passwort in Keyring legen
    keyring_store.set_password(job.target.repo_url, "pw")

    assert run_job_headless(job.id) == EXIT_OK

    # Snapshot muss existieren
    snaps = ResticRunner(local_repo(repo_path), password="pw").snapshots()
    assert len(snaps) == 1


def test_run_job_with_retention(xdg_isolated, in_memory_keyring, tmp_path):
    from backman.engine import ResticRunner, local_repo
    repo_path = tmp_path / "repo"
    src_path = tmp_path / "src"
    src_path.mkdir()
    (src_path / "a.txt").write_text("a", encoding="utf-8")
    runner = ResticRunner(local_repo(repo_path), password="pw")
    runner.init()
    # Zwei vorhandene Snapshots
    runner.backup([src_path])
    (src_path / "b.txt").write_text("b", encoding="utf-8")
    runner.backup([src_path])
    assert len(runner.snapshots()) == 2

    job = Job(
        name="Auto",
        sources=[str(src_path)],
        target=LocalTarget(path=str(repo_path)),
        retention=RetentionPolicy(keep_last=1),
        auto_prune=True,
    )
    cfg_path = Path(xdg_isolated) / "cfg" / "backman" / "config.toml"
    save_config(AppConfig(jobs=[job]), cfg_path)
    keyring_store.set_password(job.target.repo_url, "pw")

    assert run_job_headless(job.id) == EXIT_OK

    # Nach dem Lauf existiert genau 1 Snapshot (keep_last=1) — der gerade neue.
    final = runner.snapshots()
    assert len(final) == 1
