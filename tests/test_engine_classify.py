"""Reine Unit-Tests für die Fehlerklassifikation (kein restic-Binary nötig)."""

from __future__ import annotations

from backman.engine.restic import (
    RepoLockedError,
    RepoNotInitializedError,
    ResticError,
    WrongPasswordError,
    _classify_error,
)


def test_locked_by_exit_code():
    err = _classify_error(11, "")
    assert isinstance(err, RepoLockedError)
    assert err.returncode == 11


def test_locked_by_stderr_text():
    err = _classify_error(1, "unable to create lock in backend: repository is already locked")
    assert isinstance(err, RepoLockedError)


def test_wrong_password_by_exit_code():
    assert isinstance(_classify_error(12, ""), WrongPasswordError)


def test_not_initialized_by_exit_code():
    assert isinstance(_classify_error(10, ""), RepoNotInitializedError)


def test_unknown_falls_back_to_generic():
    err = _classify_error(1, "boom")
    assert isinstance(err, ResticError)
    assert not isinstance(err, (RepoLockedError, WrongPasswordError, RepoNotInitializedError))
