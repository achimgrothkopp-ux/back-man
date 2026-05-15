"""Tests für den Passwort-Dialog und den Repo-neu-Erkennung im MainWindow."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_new_password_dialog_rejects_mismatch(qt_app):
    from backman.gui.password import _NewPasswordDialog

    dlg = _NewPasswordDialog("/tmp/x")
    dlg._pw1.setText("a")
    dlg._pw2.setText("b")
    dlg._on_accept()  # darf nicht akzeptieren
    # Dialog ist nicht visible (nicht show'd), aber der Error-Label-Text muss gesetzt sein
    assert dlg._error_label.text() != ""


def test_new_password_dialog_rejects_empty(qt_app):
    from backman.gui.password import _NewPasswordDialog

    dlg = _NewPasswordDialog("/tmp/x")
    dlg._pw1.setText("")
    dlg._pw2.setText("")
    dlg._on_accept()
    assert dlg._error_label.text() != ""


def test_new_password_dialog_accepts_matching(qt_app):
    from backman.gui.password import _NewPasswordDialog

    dlg = _NewPasswordDialog("/tmp/x")
    dlg._pw1.setText("geheim42")
    dlg._pw2.setText("geheim42")
    dlg._on_accept()
    from PySide6.QtWidgets import QDialog

    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.password() == "geheim42"


def test_repo_seems_new_when_no_config_file(tmp_path):
    from backman.config import LocalTarget
    from backman.gui.main_window import MainWindow

    target = LocalTarget(path=str(tmp_path / "leer"))
    assert MainWindow._repo_seems_new(target) is True


def test_repo_seems_new_false_when_config_exists(tmp_path):
    from backman.config import LocalTarget
    from backman.gui.main_window import MainWindow

    repo = tmp_path / "vorhanden"
    repo.mkdir()
    (repo / "config").write_text("dummy", encoding="utf-8")
    target = LocalTarget(path=str(repo))
    assert MainWindow._repo_seems_new(target) is False
