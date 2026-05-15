"""Generischer QThread-Worker für synchrone ResticRunner-Aufrufe.

Verwendung: Restore, forget_snapshot, check — kurz: alles, was kein
Live-Progress liefert und nur Erfolg/Fehler interessiert.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

log = logging.getLogger(__name__)


class EngineTaskWorker(QObject):
    """Führt ein no-arg-Callable im QThread aus.

    `finished_ok(object)` trägt den Rückgabewert (oder None bei
    void-Aktionen). Aufrufer ignorieren das einfach, wenn nicht relevant.
    """

    finished_ok = Signal(object)
    failed = Signal(str)
    done = Signal()

    def __init__(self, name: str, action: Callable[[], Any]) -> None:
        super().__init__()
        self._name = name
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            log.info("Starte: %s", self._name)
            result = self._action()
            log.info("Fertig: %s", self._name)
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            log.exception("%s fehlgeschlagen", self._name)
            self.failed.emit(str(exc))
        finally:
            self.done.emit()
