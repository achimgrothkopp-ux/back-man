"""Gemeinsame Test-Fixtures."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qt_app():
    """Eine einzige QApplication für die gesamte Test-Session.

    Wir nutzen QApplication (nicht QCoreApplication), damit auch Tests, die
    Widgets erzeugen, dieselbe Instanz wiederverwenden — sonst crasht
    PySide6, wenn ein QCoreApplication zuerst angelegt wurde.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
