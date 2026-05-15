"""Dialog zum Anlegen/Bearbeiten eines Jobs.

Aufgeteilt in drei Tabs: Allgemein, Aufbewahrung, Zeitplan. Nur lokale
Ziele in M3, mit Retention- und Schedule-Konfiguration aus M5.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTime

from ..config import (
    Job,
    LocalTarget,
    RetentionPolicy,
    Schedule,
    ScheduleKind,
)


_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class JobEditorDialog(QDialog):
    """Dialog zum Erstellen oder Bearbeiten eines Backup-Jobs."""

    def __init__(self, job: Job | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Job bearbeiten" if job else "Neuer Job")
        self.setModal(True)
        self.resize(640, 620)

        self._editing_id = job.id if job else None
        self._result: Job | None = None

        # ---- Felder „Allgemein" -----------------------------------------
        self._name_edit = QLineEdit(job.name if job else "")
        self._target_edit = QLineEdit(job.target.path if job else "")
        self._tags_edit = QLineEdit(", ".join(job.tags) if job else "")
        self._sources_list = QListWidget()
        if job:
            self._sources_list.addItems(job.sources)
        self._excludes_list = QListWidget()
        if job:
            self._excludes_list.addItems(job.excludes)

        # ---- Felder „Aufbewahrung" --------------------------------------
        r = job.retention if job else RetentionPolicy()
        self._keep_last = self._make_spin(r.keep_last)
        self._keep_daily = self._make_spin(r.keep_daily)
        self._keep_weekly = self._make_spin(r.keep_weekly)
        self._keep_monthly = self._make_spin(r.keep_monthly)
        self._keep_yearly = self._make_spin(r.keep_yearly)
        self._auto_prune = QCheckBox(
            "Nach jedem Backup automatisch alte Snapshots löschen (forget + prune)"
        )
        self._auto_prune.setChecked(bool(job and job.auto_prune))

        # ---- Felder „Zeitplan" ------------------------------------------
        s = job.schedule if job else Schedule()
        self._schedule_kind = QComboBox()
        self._schedule_kind.addItem("Manuell (kein Timer)", ScheduleKind.MANUAL)
        self._schedule_kind.addItem("Täglich", ScheduleKind.DAILY)
        self._schedule_kind.addItem("Wöchentlich", ScheduleKind.WEEKLY)
        self._schedule_kind.addItem("Benutzerdefiniert (OnCalendar)", ScheduleKind.CUSTOM)
        idx = self._schedule_kind.findData(s.kind)
        self._schedule_kind.setCurrentIndex(idx if idx >= 0 else 0)
        self._schedule_kind.currentIndexChanged.connect(self._refresh_schedule_visibility)

        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        hh, mm = s.time.split(":") if ":" in s.time else ("03", "00")
        self._time_edit.setTime(QTime(int(hh), int(mm)))

        self._day_combo = QComboBox()
        self._day_combo.addItems(_DAYS)
        if s.day_of_week in _DAYS:
            self._day_combo.setCurrentIndex(_DAYS.index(s.day_of_week))

        self._custom_edit = QLineEdit(s.custom_on_calendar)
        self._custom_edit.setPlaceholderText("z.B. *-*-01 04:00:00")

        self._build_layout()
        self._refresh_schedule_visibility()

    # ---- Konstruktion ------------------------------------------------

    @staticmethod
    def _make_spin(value: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(0, 999)
        s.setValue(int(value))
        s.setSpecialValueText("—")  # 0 wird als "—" angezeigt
        return s

    def _build_layout(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "Allgemein")
        tabs.addTab(self._build_retention_tab(), "Aufbewahrung")
        tabs.addTab(self._build_schedule_tab(), "Zeitplan")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addWidget(buttons)

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)
        target_row = QHBoxLayout()
        target_row.addWidget(self._target_edit)
        target_btn = QPushButton("Ordner wählen…")
        target_btn.clicked.connect(self._pick_target)
        target_row.addWidget(target_btn)
        form.addRow("Ziel-Verzeichnis:", target_row)
        form.addRow("Tags (komma-getrennt):", self._tags_edit)
        layout.addLayout(form)

        layout.addWidget(self._build_path_list_box(
            "Quellen", self._sources_list, self._add_source, self._remove_selected_source
        ))
        layout.addWidget(self._build_path_list_box(
            "Excludes (Pattern, z.B. *.tmp)",
            self._excludes_list, self._add_exclude, self._remove_selected_exclude
        ))
        return tab

    def _build_retention_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        intro = QLabel(
            "Wie viele Snapshots sollen beim Aufräumen behalten werden? "
            "Werte auf 0 setzen, um eine Regel zu deaktivieren. Wenn alle "
            "Werte 0 sind, werden keine Snapshots automatisch entfernt."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.addRow("Letzte (--keep-last):", self._keep_last)
        form.addRow("Täglich (--keep-daily):", self._keep_daily)
        form.addRow("Wöchentlich (--keep-weekly):", self._keep_weekly)
        form.addRow("Monatlich (--keep-monthly):", self._keep_monthly)
        form.addRow("Jährlich (--keep-yearly):", self._keep_yearly)
        layout.addLayout(form)
        layout.addWidget(self._auto_prune)

        warn = QLabel(
            "<i>Auto-Prune ist standardmäßig aus, damit nicht versehentlich "
            "Snapshots gelöscht werden. Im Snapshots-Tab kannst du Snapshots "
            "weiterhin einzeln entfernen.</i>"
        )
        warn.setWordWrap(True)
        warn.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(warn)
        layout.addStretch(1)
        return tab

    def _build_schedule_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        intro = QLabel(
            "Automatische Backup-Läufe über systemd-User-Timer. Voraussetzung: "
            "Graphische Session läuft (der Keyring muss entsperrt sein, sonst "
            "kommt der Headless-Lauf nicht ans Passwort)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.addRow("Häufigkeit:", self._schedule_kind)
        self._time_row = form.addRow("Uhrzeit:", self._time_edit)  # rückgabewert None — wir merken uns über Helper
        self._day_row_label = QLabel("Wochentag:")
        form.addRow(self._day_row_label, self._day_combo)
        self._custom_row_label = QLabel("OnCalendar:")
        form.addRow(self._custom_row_label, self._custom_edit)
        layout.addLayout(form)

        hint = QLabel(
            "<i>Beispiel OnCalendar: <code>*-*-01 04:00:00</code> = jeden Monatsersten "
            "um 04:00 Uhr. Siehe <code>man systemd.time</code>.</i>"
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(hint)
        layout.addStretch(1)
        return tab

    def _build_path_list_box(
        self,
        label: str,
        list_widget: QListWidget,
        add_handler,
        remove_handler,
    ) -> QGroupBox:
        box = QGroupBox(label)
        v = QVBoxLayout(box)
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
        return box

    # ---- Sichtbarkeit Schedule-Felder --------------------------------

    def _current_schedule_kind(self) -> ScheduleKind:
        """QComboBox liefert das Payload als str zurück — coerzieren wir hier."""
        raw = self._schedule_kind.currentData()
        if isinstance(raw, ScheduleKind):
            return raw
        try:
            return ScheduleKind(raw)
        except (ValueError, TypeError):
            return ScheduleKind.MANUAL

    def _refresh_schedule_visibility(self) -> None:
        kind = self._current_schedule_kind()
        wants_time = kind in (ScheduleKind.DAILY, ScheduleKind.WEEKLY)
        wants_day = kind is ScheduleKind.WEEKLY
        wants_custom = kind is ScheduleKind.CUSTOM
        self._time_edit.setEnabled(wants_time)
        self._day_combo.setEnabled(wants_day)
        self._day_row_label.setEnabled(wants_day)
        self._custom_edit.setEnabled(wants_custom)
        self._custom_row_label.setEnabled(wants_custom)

    # ---- File-/Pattern-Picker ----------------------------------------

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
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, "Exclude", "Pattern (z.B. *.tmp, .cache):")
        if ok and text.strip():
            self._excludes_list.addItem(text.strip())

    def _remove_selected_exclude(self) -> None:
        for item in self._excludes_list.selectedItems():
            self._excludes_list.takeItem(self._excludes_list.row(item))

    # ---- Werte einsammeln --------------------------------------------

    def _collect_sources(self) -> list[str]:
        return [self._sources_list.item(i).text() for i in range(self._sources_list.count())]

    def _collect_excludes(self) -> list[str]:
        return [self._excludes_list.item(i).text() for i in range(self._excludes_list.count())]

    def _collect_retention(self) -> RetentionPolicy:
        return RetentionPolicy(
            keep_last=self._keep_last.value(),
            keep_daily=self._keep_daily.value(),
            keep_weekly=self._keep_weekly.value(),
            keep_monthly=self._keep_monthly.value(),
            keep_yearly=self._keep_yearly.value(),
        )

    def _collect_schedule(self) -> Schedule:
        kind = self._current_schedule_kind()
        t = self._time_edit.time()
        time_str = f"{t.hour():02d}:{t.minute():02d}"
        return Schedule(
            kind=kind,
            time=time_str,
            day_of_week=self._day_combo.currentText(),
            custom_on_calendar=self._custom_edit.text().strip(),
        )

    def _on_accept(self) -> None:
        try:
            job_kwargs = dict(
                name=self._name_edit.text(),
                sources=self._collect_sources(),
                target=LocalTarget(path=self._target_edit.text().strip()),
                tags=[t.strip() for t in self._tags_edit.text().split(",") if t.strip()],
                excludes=self._collect_excludes(),
                retention=self._collect_retention(),
                auto_prune=self._auto_prune.isChecked(),
                schedule=self._collect_schedule(),
            )
            if self._editing_id:
                job_kwargs["id"] = self._editing_id
            job = Job(**job_kwargs)
        except Exception as exc:  # Pydantic-Validierung
            QMessageBox.warning(self, "Ungültige Eingabe", str(exc))
            return

        if not job.target.path:
            QMessageBox.warning(self, "Ungültige Eingabe", "Ziel-Verzeichnis fehlt.")
            return

        self._result = job
        self.accept()

    def accepted_job(self) -> Job | None:
        return self._result
