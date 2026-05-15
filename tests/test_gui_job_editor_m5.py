"""GUI-Tests für die in M5 erweiterten Job-Editor-Felder."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_editor_loads_retention_and_schedule_from_existing_job(qt_app):
    from backman.config import (
        Job,
        LocalTarget,
        RetentionPolicy,
        Schedule,
        ScheduleKind,
    )
    from backman.gui.job_editor import JobEditorDialog

    job = Job(
        name="Test",
        sources=["/x"],
        target=LocalTarget(path="/y"),
        retention=RetentionPolicy(keep_daily=5, keep_weekly=2),
        auto_prune=True,
        schedule=Schedule(kind=ScheduleKind.WEEKLY, day_of_week="Sat", time="22:30"),
    )

    dlg = JobEditorDialog(job=job)
    try:
        assert dlg._keep_daily.value() == 5
        assert dlg._keep_weekly.value() == 2
        assert dlg._auto_prune.isChecked() is True
        assert dlg._current_schedule_kind() is ScheduleKind.WEEKLY
        assert dlg._day_combo.currentText() == "Sat"
        t = dlg._time_edit.time()
        assert (t.hour(), t.minute()) == (22, 30)
    finally:
        dlg.deleteLater()


def test_editor_collects_new_fields(qt_app):
    from backman.config import ScheduleKind
    from backman.gui.job_editor import JobEditorDialog

    dlg = JobEditorDialog()
    try:
        dlg._name_edit.setText("Auto")
        dlg._target_edit.setText("/tmp/ziel")
        dlg._sources_list.addItem("/tmp/quelle")
        dlg._keep_daily.setValue(7)
        dlg._keep_weekly.setValue(4)
        dlg._auto_prune.setChecked(True)
        dlg._schedule_kind.setCurrentIndex(dlg._schedule_kind.findData(ScheduleKind.DAILY))
        from PySide6.QtCore import QTime

        dlg._time_edit.setTime(QTime(4, 0))

        dlg._on_accept()
        job = dlg.accepted_job()
        assert job is not None
        assert job.retention.keep_daily == 7
        assert job.retention.keep_weekly == 4
        assert job.auto_prune is True
        assert job.schedule.kind is ScheduleKind.DAILY
        assert job.schedule.time == "04:00"
        assert job.schedule.to_on_calendar() == "*-*-* 04:00:00"
    finally:
        dlg.deleteLater()


def test_editor_schedule_visibility_changes(qt_app):
    from backman.config import ScheduleKind
    from backman.gui.job_editor import JobEditorDialog

    dlg = JobEditorDialog()
    try:
        dlg._schedule_kind.setCurrentIndex(dlg._schedule_kind.findData(ScheduleKind.MANUAL))
        dlg._refresh_schedule_visibility()
        assert dlg._time_edit.isEnabled() is False
        assert dlg._day_combo.isEnabled() is False
        assert dlg._custom_edit.isEnabled() is False

        dlg._schedule_kind.setCurrentIndex(dlg._schedule_kind.findData(ScheduleKind.WEEKLY))
        dlg._refresh_schedule_visibility()
        assert dlg._time_edit.isEnabled() is True
        assert dlg._day_combo.isEnabled() is True
        assert dlg._custom_edit.isEnabled() is False

        dlg._schedule_kind.setCurrentIndex(dlg._schedule_kind.findData(ScheduleKind.CUSTOM))
        dlg._refresh_schedule_visibility()
        assert dlg._time_edit.isEnabled() is False
        assert dlg._day_combo.isEnabled() is False
        assert dlg._custom_edit.isEnabled() is True
    finally:
        dlg.deleteLater()
