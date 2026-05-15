"""Widget mit Snapshot-Tabelle und Verwaltungsbuttons.

Selbst hält keinen `ResticRunner` — der wird vom MainWindow injiziert,
weil das Passwort-/Init-Handling dort liegt. Das Widget bietet Callbacks:

  - `request_refresh`: User klickte „Laden / Aktualisieren"
  - `request_restore(Snapshot)`: User klickte „Wiederherstellen…"
  - `request_delete(Snapshot)`: User klickte „Löschen"
  - `request_check`: User klickte „Repo-Check"
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..engine import Snapshot


def _format_time(iso: str) -> str:
    if not iso:
        return ""
    try:
        return dt.datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso


class SnapshotsPanel(QWidget):
    request_refresh = Signal()
    request_restore = Signal(object)  # Snapshot
    request_delete = Signal(object)   # Snapshot
    request_check = Signal()

    COL_DATE = 0
    COL_TAGS = 1
    COL_ID = 2
    COL_PATHS = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshots: list[Snapshot] = []

        self._info_label = QLabel("Noch keine Snapshots geladen.")
        self._info_label.setWordWrap(True)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Zeitpunkt", "Tags", "ID", "Pfade"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.itemSelectionChanged.connect(self._update_button_state)

        self._refresh_btn = QPushButton("Laden / Aktualisieren")
        self._refresh_btn.clicked.connect(self.request_refresh.emit)

        self._restore_btn = QPushButton("Wiederherstellen…")
        self._restore_btn.clicked.connect(self._on_restore_clicked)
        self._restore_btn.setEnabled(False)

        self._delete_btn = QPushButton("Snapshot löschen")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        self._delete_btn.setEnabled(False)

        self._check_btn = QPushButton("Repo-Check")
        self._check_btn.clicked.connect(self.request_check.emit)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._refresh_btn)
        btn_row.addWidget(self._restore_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._check_btn)

        root = QVBoxLayout(self)
        root.addWidget(self._info_label)
        root.addWidget(self._table, stretch=1)
        root.addLayout(btn_row)

    # ---- public API --------------------------------------------------

    def set_snapshots(self, snapshots: Iterable[Snapshot]) -> None:
        self._snapshots = list(snapshots)
        self._table.setRowCount(0)
        for snap in self._snapshots:
            self._append_row(snap)
        if not self._snapshots:
            self._info_label.setText("Keine Snapshots vorhanden.")
        else:
            self._info_label.setText(f"{len(self._snapshots)} Snapshot(s).")
        self._update_button_state()

    def clear(self) -> None:
        self._snapshots = []
        self._table.setRowCount(0)
        self._info_label.setText("Noch keine Snapshots geladen.")
        self._update_button_state()

    def set_busy(self, busy: bool, message: str = "") -> None:
        """Während laufender Vorgänge Buttons sperren und Hinweis zeigen."""
        for btn in (self._refresh_btn, self._restore_btn, self._delete_btn, self._check_btn):
            btn.setEnabled(not busy)
        if busy and message:
            self._info_label.setText(message)
        elif not busy:
            self._update_button_state()

    def selected_snapshot(self) -> Snapshot | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._snapshots):
            return self._snapshots[idx]
        return None

    # ---- internal ----------------------------------------------------

    def _append_row(self, snap: Snapshot) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        items = [
            QTableWidgetItem(_format_time(snap.time)),
            QTableWidgetItem(", ".join(snap.tags)),
            QTableWidgetItem(snap.short_id),
            QTableWidgetItem(", ".join(snap.paths)),
        ]
        for col, item in enumerate(items):
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, col, item)

    def _update_button_state(self) -> None:
        snap = self.selected_snapshot()
        has_selection = snap is not None
        self._restore_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

    def _on_restore_clicked(self) -> None:
        snap = self.selected_snapshot()
        if snap is not None:
            self.request_restore.emit(snap)

    def _on_delete_clicked(self) -> None:
        snap = self.selected_snapshot()
        if snap is not None:
            self.request_delete.emit(snap)
