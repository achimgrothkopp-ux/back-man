import subprocess
from unittest import mock

import pytest

from backman import restic_check
from backman.restic_check import ResticNotFoundError, find_restic


def test_find_restic_raises_when_missing(monkeypatch):
    monkeypatch.setattr(restic_check.shutil, "which", lambda _name: None)
    with pytest.raises(ResticNotFoundError):
        find_restic()


def test_find_restic_returns_version(monkeypatch):
    monkeypatch.setattr(restic_check.shutil, "which", lambda _name: "/usr/bin/restic")

    fake_result = mock.Mock()
    fake_result.stdout = "restic 0.16.4 compiled with go1.21\n"

    def fake_run(*_args, **_kwargs):
        return fake_result

    monkeypatch.setattr(restic_check.subprocess, "run", fake_run)

    info = find_restic()
    assert info.path == "/usr/bin/restic"
    assert info.version.startswith("restic 0.16.4")


def test_find_restic_wraps_subprocess_errors(monkeypatch):
    monkeypatch.setattr(restic_check.shutil, "which", lambda _name: "/usr/bin/restic")

    def boom(*_args, **_kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=["restic", "version"])

    monkeypatch.setattr(restic_check.subprocess, "run", boom)

    with pytest.raises(ResticNotFoundError):
        find_restic()
