"""Tests für den USB-Watcher (QFileSystemWatcher-basiert)."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


def test_default_mount_roots_filters_nonexistent(monkeypatch, tmp_path):
    monkeypatch.setenv("USER", "tester")
    # Keine echten /run/media/tester etc. — sollte leer sein
    from backman.gui.usb_watcher import default_mount_roots

    roots = default_mount_roots()
    # /media existiert auf den meisten Systemen, aber wir prüfen nur, dass nur
    # vorhandene Verzeichnisse zurückkommen.
    for r in roots:
        assert r.exists() and r.is_dir()


def test_usb_watcher_emits_on_new_directory(qt_app, tmp_path):
    from backman.gui.usb_watcher import UsbWatcher

    root = tmp_path / "media_root"
    root.mkdir()
    captured: list[str] = []

    watcher = UsbWatcher(mount_roots=[root])
    watcher.mount_appeared.connect(captured.append)

    # Direkt das interne Handler triggern (kein echter fs-event nötig)
    (root / "USB_BACKUP").mkdir()
    watcher._on_dir_changed(str(root))

    assert len(captured) == 1
    assert captured[0] == str(root / "USB_BACKUP")


def test_usb_watcher_ignores_existing_entries(qt_app, tmp_path):
    from backman.gui.usb_watcher import UsbWatcher

    root = tmp_path / "media_root"
    root.mkdir()
    (root / "existing").mkdir()

    watcher = UsbWatcher(mount_roots=[root])
    captured: list[str] = []
    watcher.mount_appeared.connect(captured.append)

    # Kein Mount-Ereignis — der bestehende Eintrag ist bereits bekannt
    watcher._on_dir_changed(str(root))
    assert captured == []

    # Erst ein neuer Eintrag soll ein Signal auslösen
    (root / "USB_NEW").mkdir()
    watcher._on_dir_changed(str(root))
    assert captured == [str(root / "USB_NEW")]


def test_usb_watcher_handles_multiple_new_in_one_event(qt_app, tmp_path):
    from backman.gui.usb_watcher import UsbWatcher

    root = tmp_path / "media_root"
    root.mkdir()

    watcher = UsbWatcher(mount_roots=[root])
    captured: list[str] = []
    watcher.mount_appeared.connect(captured.append)

    (root / "A").mkdir()
    (root / "B").mkdir()
    watcher._on_dir_changed(str(root))

    assert sorted(captured) == [str(root / "A"), str(root / "B")]
