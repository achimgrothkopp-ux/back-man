"""Dialog zum Anlegen/Bearbeiten eines Job. Nur lokale Ziele in M3."""

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
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import Job, LocalTarget


class JobEditorDialog(QDialog):
    """Dialog zum Erstellen oder Bearbeiten eines Backup-Jobs.

    Liefert den Job per `accepted_job()` zurück, wenn der User OK klickt.
    """

    def __init__(self, job: Job | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Job bearbeiten" if job else "Neuer Job")
        self.setModal(True)
        self.resize(560, 480)

        self._editing_id = job.id if job else None
        self._result: Job | None = None

        self._name_edit = QLineEdit(job.name if job else "")
        self._target_edit = QLineEdit(job.target.path if job else "")
        self._tags_edit = QLineEdit(", ".join(job.tags) if job else "")

        self._sources_list = QListWidget()
        if job:
            self._sources_list.addItems(job.sources)

        self._excludes_list = QListWidget()
        if job:
            self._excludes_list.addItems(job.excludes)

        self._build_layout()

    def _build_layout(self) -> None:
        form = QFormLayout()
        form.addRow("Name:", self._name_edit)

        target_row = QHBoxLayout()
        target_row.addWidget(self._target_edit)
        target_btn = QPushButton("Ordner wählen…")
        target_btn.clicked.connect(self._pick_target)
        target_row.addWidget(target_btn)
        form.addRow("Ziel-Verzeichnis:", target_row)

        form.addRow("Tags (komma-getrennt):", self._tags_edit)

        sources_box = self._build_path_list_box(
            "Quellen", self._sources_list, self._add_source, self._remove_selected_source
        )
        excludes_box = self._build_path_list_box(
            "Excludes (Pattern, z.B. *.tmp)",
            self._excludes_list,
            self._add_exclude,
            self._remove_selected_exclude,
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(sources_box)
        root.addWidget(excludes_box)
        root.addWidget(buttons)

    def _build_path_list_box(
        self,
        label: str,
        list_widget: QListWidget,
        add_handler,
        remove_handler,
    ) -> QWidget:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel(label))
        v.addWidget(list_widget, stretch=1)

        row = QHBoxLayout()
        add_btn = QPushButton("Hinzufügen…")
        add_btn.clicked.connect(add_handler)
        rm_btn = QPushButton("Entfernen")
        rm_btn.clicked.connect(remove_handler)
        row.addWidget(add_btn)
        row.addWidget(rm_btn)
        row.addStretch(1)
        v.addLayout(row)
        return container

    # ---- slots --------------------------------------------------------

    def _pick_target(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Backup-Ziel auswählen")
        if path:
            self._target_edit.setText(path)

    def _add_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Quell-Ordner auswählen")
        if path:
            self._sources_list.addItem(path)

    def _remove_selected_source(self) -> None:
        for item in self._sources_list.selectedItems():
            self._sources_list.takeItem(self._sources_list.row(item))

    def _add_exclude(self) -> None:
        # Einfache Pattern-Eingabe über LineEdit-Dialog
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, "Exclude", "Pattern (z.B. *.tmp, .cache):")
        if ok and text.strip():
            self._excludes_list.addItem(text.strip())

    def _remove_selected_exclude(self) -> None:
        for item in self._excludes_list.selectedItems():
            self._excludes_list.takeItem(self._excludes_list.row(item))

    def _collect_sources(self) -> list[str]:
        return [self._sources_list.item(i).text() for i in range(self._sources_list.count())]

    def _collect_excludes(self) -> list[str]:
        return [self._excludes_list.item(i).text() for i in range(self._excludes_list.count())]

    def _on_accept(self) -> None:
        try:
            job_kwargs = dict(
                name=self._name_edit.text(),
                sources=self._collect_sources(),
                target=LocalTarget(path=self._target_edit.text().strip()),
                tags=[t.strip() for t in self._tags_edit.text().split(",") if t.strip()],
                excludes=self._collect_excludes(),
            )
            if self._editing_id:
                job_kwargs["id"] = self._editing_id
            job = Job(**job_kwargs)
        except Exception as exc:  # ValidationError u.Ä.
            QMessageBox.warning(self, "Ungültige Eingabe", str(exc))
            return

        if not job.target.path:
            QMessageBox.warning(self, "Ungültige Eingabe", "Ziel-Verzeichnis fehlt.")
            return

        self._result = job
        self.accept()

    def accepted_job(self) -> Job | None:
        return self._result
