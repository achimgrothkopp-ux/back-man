"""Tests für die systemd-Unit-Generierung."""

from __future__ import annotations

from backman.config import Job, LocalTarget
from backman.scheduler import units


def _job(name="MyJob", job_id="abc123") -> Job:
    return Job(id=job_id, name=name, sources=["/x"], target=LocalTarget(path="/y"))


def test_unit_basename_includes_job_id():
    j = _job(job_id="deadbeef")
    assert units.job_unit_basename(j) == "back-man-job-deadbeef"


def test_unit_paths_under_units_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    j = _job(job_id="foo")
    sp = units.job_service_path(j)
    tp = units.job_timer_path(j)
    assert sp.parent == tmp_path / "cfg" / "systemd" / "user"
    assert sp.name == "back-man-job-foo.service"
    assert tp.name == "back-man-job-foo.timer"


def test_render_service_unit_contains_job_id():
    j = _job(job_id="thejob")
    text = units.render_service_unit(j)
    assert "Type=oneshot" in text
    assert "--run-job thejob" in text
    assert "back-man" in text  # mindestens als Befehlsname
    assert "WantedBy=default.target" in text


def test_render_timer_unit_oncalendar_and_persistent():
    j = _job()
    text = units.render_timer_unit(j, on_calendar="*-*-* 03:30:00")
    assert "OnCalendar=*-*-* 03:30:00" in text
    assert "Persistent=true" in text
    assert "WantedBy=timers.target" in text
    assert f"Unit={units.job_unit_basename(j)}.service" in text


def test_write_and_remove_units(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    j = _job(job_id="abc")
    sp, tp = units.write_units(j, on_calendar="daily")
    assert sp.exists()
    assert tp.exists()
    assert "OnCalendar=daily" in tp.read_text(encoding="utf-8")

    s_existed, t_existed = units.remove_units(j)
    assert s_existed is True and t_existed is True
    assert not sp.exists()
    assert not tp.exists()


def test_write_units_overwrites(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    j = _job(job_id="abc")
    units.write_units(j, on_calendar="daily")
    sp, tp = units.write_units(j, on_calendar="weekly")
    assert "OnCalendar=weekly" in tp.read_text(encoding="utf-8")
    assert "OnCalendar=daily" not in tp.read_text(encoding="utf-8")


def test_remove_units_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    j = _job(job_id="ghost")
    s_existed, t_existed = units.remove_units(j)
    assert s_existed is False
    assert t_existed is False
