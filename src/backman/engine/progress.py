"""Parser für die JSON-Events von `restic backup --json`.

restic gibt zeilenweise JSON-Objekte aus. Die wichtigsten message_types:

- `status`: Live-Fortschritt (percent_done, files_done, bytes_done, total_*,
  current_files, seconds_elapsed)
- `summary`: einmaliges Endergebnis (snapshot_id, files_new/changed,
  data_added, total_duration, ...)
- `error`: Fehler-Item (item, error)
- `verbose_status`: pro Datei (action, item, ...)

Wir mappen das auf zwei typisierte Events; alles andere wird übersprungen.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable, Iterator

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProgressEvent:
    percent_done: float
    total_files: int
    files_done: int
    total_bytes: int
    bytes_done: int
    seconds_elapsed: float
    current_files: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SummaryEvent:
    snapshot_id: str
    files_new: int
    files_changed: int
    files_unmodified: int
    data_added: int
    total_bytes_processed: int
    total_duration: float


def parse_progress_lines(
    lines: Iterable[str],
) -> Iterator[ProgressEvent | SummaryEvent]:
    """Konsumiert restic-JSON-Zeilen und liefert typisierte Events."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            log.debug("Nicht-JSON-Zeile von restic übersprungen: %r", line[:200])
            continue

        mtype = obj.get("message_type")
        if mtype == "status":
            yield ProgressEvent(
                percent_done=float(obj.get("percent_done", 0.0)),
                total_files=int(obj.get("total_files", 0)),
                files_done=int(obj.get("files_done", 0)),
                total_bytes=int(obj.get("total_bytes", 0)),
                bytes_done=int(obj.get("bytes_done", 0)),
                seconds_elapsed=float(obj.get("seconds_elapsed", 0.0)),
                current_files=tuple(obj.get("current_files") or ()),
            )
        elif mtype == "summary":
            yield SummaryEvent(
                snapshot_id=str(obj.get("snapshot_id", "")),
                files_new=int(obj.get("files_new", 0)),
                files_changed=int(obj.get("files_changed", 0)),
                files_unmodified=int(obj.get("files_unmodified", 0)),
                data_added=int(obj.get("data_added", 0)),
                total_bytes_processed=int(obj.get("total_bytes_processed", 0)),
                total_duration=float(obj.get("total_duration", 0.0)),
            )
        elif mtype == "error":
            log.warning("restic error: %s", obj.get("error", obj))
        # verbose_status, initial_message, ... ignorieren wir bewusst.
