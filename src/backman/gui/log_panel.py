"""Live-Log-Panel als QDockWidget. Pollt die GuiLogQueue per QTimer."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDockWidget, QPlainTextEdit

from ..logging_setup import GuiLogQueue


class LogDock(QDockWidget):
    """DockWidget mit autoscrollendem Log-Stream."""

    POLL_INTERVAL_MS = 250
    MAX_BLOCKS = 5000

    def __init__(self, sink: GuiLogQueue, parent=None) -> None:
        super().__init__("Log", parent)
        self._sink = sink

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(self.MAX_BLOCKS)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._view.setFont(font)
        self.setWidget(self._view)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(self.POLL_INTERVAL_MS)

    def _drain(self) -> None:
        for line in self._sink.drain():
            self._view.appendPlainText(line)
