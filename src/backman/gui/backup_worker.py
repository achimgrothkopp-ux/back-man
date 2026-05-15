"""QThread-Worker, der ResticRunner.backup() ausführt und Events emittiert."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..engine import ProgressEvent, ResticRunner, SummaryEvent
from ..engine.restic import ForgetPolicy

log = logging.getLogger(__name__)


class BackupWorker(QObject):
    """Wird auf einen QThread verschoben und über `run`-Signal gestartet.

    Sendet:
      - progress(ProgressEvent) während des Laufs
      - finished_ok(SummaryEvent) bei Erfolg
      - failed(str) bei Fehler
      - done() unabhängig vom Ausgang am Ende (Aufräumen)

    Wenn `retention` gesetzt ist, läuft nach einem erfolgreichen Backup
    automatisch `forget --prune` mit dieser Policy. Ein Fehler dabei wird
    nur geloggt, das Backup bleibt erfolgreich (`finished_ok` wird trotzdem
    emittiert) — die Snapshot-Daten sind ja sicher im Repo.
    """

    progress = Signal(object)        # ProgressEvent
    finished_ok = Signal(object)     # SummaryEvent
    failed = Signal(str)
    done = Signal()

    def __init__(
        self,
        runner: ResticRunner,
        sources: list[Path],
        tags: list[str] | None = None,
        excludes: list[str] | None = None,
        retention: ForgetPolicy | None = None,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._sources = sources
        self._tags = list(tags or [])
        self._excludes = list(excludes or [])
        self._retention = retention

    @Slot()
    def run(self) -> None:
        try:
            summary = self._runner.backup(
                self._sources,
                tags=self._tags,
                excludes=self._excludes,
                on_event=self._emit_event,
            )
            if self._retention is not None:
                try:
                    log.info("Wende Retention an: %s", self._retention)
                    self._runner.forget(self._retention, prune=True)
                except Exception:
                    log.exception(
                        "Retention/Prune fehlgeschlagen — Backup selbst war erfolgreich"
                    )
            self.finished_ok.emit(summary)
        except Exception as exc:  # noqa: BLE001
            log.exception("Backup fehlgeschlagen")
            self.failed.emit(str(exc))
        finally:
            self.done.emit()

    def _emit_event(self, event: ProgressEvent | SummaryEvent) -> None:
        if isinstance(event, ProgressEvent):
            self.progress.emit(event)
