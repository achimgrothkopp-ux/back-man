"""Logging-Setup: rotierende Datei + In-Memory-Queue für GUI-Live-Anzeige."""

from __future__ import annotations

import logging
import logging.handlers
import queue
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class GuiLogQueue:
    """Threadsicherer Ringpuffer für Log-Records, den die GUI pollen kann."""

    def __init__(self, maxsize: int = 5000) -> None:
        self._queue: queue.Queue[str] = queue.Queue(maxsize=maxsize)

    def put(self, message: str) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
        self._queue.put_nowait(message)

    def drain(self) -> list[str]:
        out: list[str] = []
        while True:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out


class _QueueHandler(logging.Handler):
    def __init__(self, sink: GuiLogQueue) -> None:
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.sink.put(self.format(record))
        except Exception:
            self.handleError(record)


def setup_logging(log_dir: Path, level: int = logging.INFO) -> GuiLogQueue:
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / "backupmanager.log"

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        logfile, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)

    gui_sink = GuiLogQueue()
    queue_handler = _QueueHandler(gui_sink)
    queue_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Vermeide doppelte Handler bei mehrfachem Setup (z.B. Tests).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.addHandler(queue_handler)

    return gui_sink
