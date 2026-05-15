"""GUI-Smoke-Tests mit offscreen Qt-Platform.

Setzt voraus, dass QT_QPA_PLATFORM=offscreen funktioniert (Standard auf
Linux mit PySide6 ohne Display).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backman.config import Job, LocalTarget  # noqa: E402
from backman.logging_setup import GuiLogQueue  # noqa: E402
from backman.paths import get_paths  # noqa: E402


def test_main_window_loads(qt_app, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    from backman.gui.main_window import MainWindow

    paths = get_paths()
    paths.ensure()
    sink = GuiLogQueue()
    win = MainWindow(paths=paths, log_sink=sink)
    try:
        assert "Back-Man" in win.windowTitle()
    finally:
        win.close()


def test_main_window_loads_existing_jobs(qt_app, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    from backman.config import AppConfig, save_config
    from backman.gui.main_window import MainWindow

    paths = get_paths()
    paths.ensure()

    job = Job(name="MeinJob", sources=["/tmp/quelle"], target=LocalTarget(path="/tmp/ziel"))
    save_config(AppConfig(jobs=[job]), paths.config_file)

    sink = GuiLogQueue()
    win = MainWindow(paths=paths, log_sink=sink)
    try:
        assert win._job_list.count() == 1
        assert win._job_list.item(0).text() == "MeinJob"
    finally:
        win.close()


def test_job_editor_roundtrip(qt_app):
    from backman.gui.job_editor import JobEditorDialog

    existing = Job(
        name="Foo",
        sources=["/a", "/b"],
        target=LocalTarget(path="/dest"),
        tags=["t1"],
        excludes=["*.tmp"],
    )
    dlg = JobEditorDialog(job=existing)
    try:
        assert dlg._name_edit.text() == "Foo"
        assert dlg._target_edit.text() == "/dest"
        assert dlg._collect_sources() == ["/a", "/b"]
        assert dlg._collect_excludes() == ["*.tmp"]
        # Tags-Feld zeigt das Eingabeformat
        assert "t1" in dlg._tags_edit.text()
    finally:
        dlg.deleteLater()


def test_backup_worker_importable(qt_app):
    """Stellt sicher, dass der Worker-Import keine Qt-Init-Probleme hat."""
    from backman.gui.backup_worker import BackupWorker

    assert BackupWorker is not None
