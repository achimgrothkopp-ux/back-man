"""GUI-Tests für SnapshotsPanel und RestoreDialog."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _make_snapshot(**overrides):
    from backman.engine import Snapshot

    defaults = dict(
        id="abcdef1234567890",
        short_id="abcdef12",
        time="2026-05-15T18:00:00+02:00",
        hostname="kali",
        username="achim",
        paths=("/home/achim/dokumente",),
        tags=("daily",),
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def test_snapshots_panel_empty_state(qt_app):
    from backman.gui.snapshots_panel import SnapshotsPanel

    panel = SnapshotsPanel()
    try:
        panel.set_snapshots([])
        assert panel.selected_snapshot() is None
        assert panel._table.rowCount() == 0
        assert "Keine Snapshots" in panel._info_label.text()
    finally:
        panel.deleteLater()


def test_snapshots_panel_populates_table(qt_app):
    from backman.gui.snapshots_panel import SnapshotsPanel

    panel = SnapshotsPanel()
    snaps = [
        _make_snapshot(short_id="aaaa1111", tags=("daily",)),
        _make_snapshot(short_id="bbbb2222", tags=("weekly", "important")),
    ]
    try:
        panel.set_snapshots(snaps)
        assert panel._table.rowCount() == 2
        # Spalte 1 ist Tags
        assert "important" in panel._table.item(1, 1).text()
        # Spalte 2 ist Short-ID
        assert panel._table.item(0, 2).text() == "aaaa1111"
    finally:
        panel.deleteLater()


def test_snapshots_panel_selection_emits_restore_signal(qt_app):
    from backman.gui.snapshots_panel import SnapshotsPanel

    panel = SnapshotsPanel()
    captured: list = []
    panel.request_restore.connect(captured.append)

    snap = _make_snapshot()
    panel.set_snapshots([snap])
    panel._table.selectRow(0)
    assert panel.selected_snapshot() is snap

    panel._on_restore_clicked()
    assert captured == [snap]


def test_snapshots_panel_delete_button_emits_signal(qt_app):
    from backman.gui.snapshots_panel import SnapshotsPanel

    panel = SnapshotsPanel()
    captured: list = []
    panel.request_delete.connect(captured.append)

    snap = _make_snapshot(short_id="zzzz9999")
    panel.set_snapshots([snap])
    panel._table.selectRow(0)
    panel._on_delete_clicked()
    assert captured == [snap]


def test_restore_dialog_target_required(qt_app):
    from backman.gui.restore_dialog import RestoreDialog

    dlg = RestoreDialog(_make_snapshot())
    try:
        # Leeres Target → _on_accept akzeptiert nicht
        dlg._on_accept()
        from PySide6.QtWidgets import QDialog

        assert dlg.result() != QDialog.DialogCode.Accepted
    finally:
        dlg.deleteLater()


def test_restore_dialog_collects_inputs(qt_app, tmp_path):
    from backman.gui.restore_dialog import RestoreDialog

    dlg = RestoreDialog(_make_snapshot())
    try:
        dlg._target_edit.setText(str(tmp_path))
        dlg._include_edit.setText("/home/achim")
        dlg._on_accept()
        assert dlg.target() == str(tmp_path)
        assert dlg.include() == "/home/achim"
    finally:
        dlg.deleteLater()


def test_engine_task_worker_emits_result(qt_app):
    from backman.gui.engine_task_worker import EngineTaskWorker

    results: list = []
    failures: list = []
    worker = EngineTaskWorker("test", lambda: 42)
    worker.finished_ok.connect(results.append)
    worker.failed.connect(failures.append)
    worker.run()
    assert results == [42]
    assert failures == []


def test_engine_task_worker_emits_failure(qt_app):
    from backman.gui.engine_task_worker import EngineTaskWorker

    results: list = []
    failures: list = []

    def boom():
        raise RuntimeError("kaputt")

    worker = EngineTaskWorker("test", boom)
    worker.finished_ok.connect(results.append)
    worker.failed.connect(failures.append)
    worker.run()
    assert results == []
    assert failures == ["kaputt"]


def test_main_window_has_snapshots_tab(qt_app, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    from backman.gui.main_window import MainWindow
    from backman.logging_setup import GuiLogQueue
    from backman.paths import get_paths

    paths = get_paths()
    paths.ensure()
    win = MainWindow(paths=paths, log_sink=GuiLogQueue())
    try:
        # Beide Tabs müssen vorhanden sein
        labels = {win._tabs.tabText(i) for i in range(win._tabs.count())}
        assert "Details" in labels
        assert "Snapshots" in labels
    finally:
        win.close()
