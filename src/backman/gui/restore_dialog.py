"""Dialog für die Wiederherstellung eines Snapshots."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..engine import Snapshot


class RestoreDialog(QDialog):
    """Sammelt Ziel-Ordner und optionalen Include-Pfad für ein Restore.

    Erfolg liefert `target()` und `include()`.
    """

    def __init__(self, snapshot: Snapshot, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Snapshot wiederherstellen")
        self.setModal(True)
        self.resize(560, 280)

        self._snapshot = snapshot
        self._target_edit = QLineEdit()
        self._include_edit = QLineEdit()

        info = QLabel(
            f"<b>Snapshot:</b> {snapshot.short_id}<br>"
            f"<b>Zeitpunkt:</b> {snapshot.time}<br>"
            f"<b>Host:</b> {snapshot.hostname}<br>"
            f"<b>Quellen:</b><br>&nbsp;&nbsp;"
            + "<br>&nbsp;&nbsp;".join(snapshot.paths or ["—"])
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        target_row = QHBoxLayout()
        target_row.addWidget(self._target_edit)
        pick_btn = QPushButton("Wählen…")
        pick_btn.clicked.connect(self._pick_target)
        target_row.addWidget(pick_btn)

        form = QFormLayout()
        form.addRow("Ziel-Verzeichnis:", target_row)
        form.addRow("Nur Pfad (optional):", self._include_edit)

        hint = QLabel(
            "<i>Hinweis: Die Original-Pfadhierarchie wird unter dem Ziel "
            "rekonstruiert (z.B. /backup/restore/home/user/...). "
            "Lasse 'Nur Pfad' leer, um alles wiederherzustellen.</i>"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(info)
        root.addLayout(form)
        root.addWidget(hint)
        root.addStretch(1)
        root.addWidget(buttons)

    def _pick_target(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Restore-Ziel auswählen")
        if path:
            self._target_edit.setText(path)

    def _on_accept(self) -> None:
        if not self._target_edit.text().strip():
            # Kein Ziel → ablehnen
            self._target_edit.setFocus()
            return
        self.accept()

    def target(self) -> str:
        return self._target_edit.text().strip()

    def include(self) -> str:
        return self._include_edit.text().strip()
