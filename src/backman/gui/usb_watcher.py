"""Beobachtet typische Mount-Roots auf neu erscheinende Wechseldatenträger.

Mint, Ubuntu, GNOME und KDE mounten Wechseldatenträger unter
`/run/media/<user>/<label>` oder `/media/<user>/<label>`. Wir nutzen
`QFileSystemWatcher`, der jedes mal feuert, wenn unter diesen Pfaden
Inhalte erscheinen oder verschwinden.

Der Watcher emittiert `mount_appeared(str)` mit dem absoluten Pfad des
neuen Mount-Punkts. Der Aufrufer (MainWindow) entscheidet, ob darunter
ein Job-Ziel liegt und gibt die entsprechende Notification raus.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal

log = logging.getLogger(__name__)


def default_mount_roots() -> list[Path]:
    """Übliche Mount-Wurzeln auf modernen Linux-Desktops."""
    user = os.environ.get("USER", "")
    candidates: list[Path] = []
    if user:
        candidates.append(Path(f"/run/media/{user}"))
        candidates.append(Path(f"/media/{user}"))
    candidates.append(Path("/media"))
    return [p for p in candidates if p.exists() and p.is_dir()]


class UsbWatcher(QObject):
    """Sendet `mount_appeared(str)` für jeden neu auftauchenden Mount-Punkt."""

    mount_appeared = Signal(str)

    def __init__(self, mount_roots: list[Path] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._roots = [Path(p) for p in (mount_roots or default_mount_roots())]
        self._watcher = QFileSystemWatcher(self)
        self._known: dict[Path, set[str]] = {}

        for root in self._roots:
            if root.exists():
                self._watcher.addPath(str(root))
                self._known[root] = set(self._list_children(root))
                log.info("USB-Watcher: beobachte %s (initial: %d)", root, len(self._known[root]))

        self._watcher.directoryChanged.connect(self._on_dir_changed)

    @staticmethod
    def _list_children(root: Path) -> list[str]:
        try:
            return [c.name for c in root.iterdir()]
        except OSError:
            return []

    def _on_dir_changed(self, changed_root: str) -> None:
        root = Path(changed_root)
        current = set(self._list_children(root))
        prev = self._known.get(root, set())
        added = current - prev
        self._known[root] = current
        for name in added:
            full = root / name
            log.info("Neuer Mount: %s", full)
            self.mount_appeared.emit(str(full))

    def known_mounts(self) -> dict[Path, set[str]]:
        """Aktueller Schnappschuss der bekannten Einträge (für Tests)."""
        return {p: set(s) for p, s in self._known.items()}
