import pytest

from backman.config import (
    AppConfig,
    Job,
    LocalTarget,
    RetentionPolicy,
    Schedule,
    ScheduleKind,
    load_config,
    save_config,
)


def _job(name="Daily", source="/home/u/docs", target_path="/mnt/backup"):
    return Job(
        name=name,
        sources=[source],
        target=LocalTarget(path=target_path),
    )


def test_job_validates_empty_name():
    with pytest.raises(ValueError):
        Job(name="   ", sources=["/x"], target=LocalTarget(path="/y"))


def test_job_validates_empty_sources():
    with pytest.raises(ValueError):
        Job(name="x", sources=[], target=LocalTarget(path="/y"))


def test_local_target_repo_url(tmp_path):
    target = LocalTarget(path=str(tmp_path / "backup"))
    assert target.repo_url == str(tmp_path / "backup")


def test_upsert_and_remove():
    cfg = AppConfig()
    j = _job(name="A")
    cfg.upsert_job(j)
    assert cfg.get_job(j.id) is j

    # Update mit gleicher ID ersetzt
    updated = Job(id=j.id, name="A2", sources=["/y"], target=LocalTarget(path="/z"))
    cfg.upsert_job(updated)
    assert cfg.get_job(j.id).name == "A2"
    assert len(cfg.jobs) == 1

    assert cfg.remove_job(j.id) is True
    assert cfg.get_job(j.id) is None
    assert cfg.remove_job(j.id) is False


def test_roundtrip_to_toml(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = AppConfig(jobs=[_job("J1", "/a", "/b"), _job("J2", "/c", "/d")])
    save_config(cfg, cfg_path)

    loaded = load_config(cfg_path)
    assert [j.name for j in loaded.jobs] == ["J1", "J2"]
    assert loaded.jobs[0].target.path == "/b"


def test_load_missing_file_returns_empty(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.jobs == []


def test_load_invalid_toml_raises(tmp_path):
    f = tmp_path / "broken.toml"
    f.write_text("this is = not [valid", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(f)


def test_save_is_atomic_no_tmp_leftover(tmp_path):
    cfg_path = tmp_path / "c.toml"
    save_config(AppConfig(jobs=[_job()]), cfg_path)
    assert cfg_path.exists()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


# ---- Retention -----------------------------------------------------


def test_retention_inactive_by_default():
    r = RetentionPolicy()
    assert r.is_active() is False
    assert r.to_forget_policy() is None


def test_retention_to_forget_policy_drops_zeros():
    r = RetentionPolicy(keep_daily=7, keep_weekly=4, keep_yearly=0)
    fp = r.to_forget_policy()
    args = fp.to_args()
    assert "--keep-daily" in args and "7" in args
    assert "--keep-weekly" in args and "4" in args
    assert "--keep-yearly" not in args


# ---- Schedule ------------------------------------------------------


def test_schedule_manual_returns_none():
    s = Schedule(kind=ScheduleKind.MANUAL)
    assert s.to_on_calendar() is None


def test_schedule_daily_oncalendar():
    s = Schedule(kind=ScheduleKind.DAILY, time="03:30")
    assert s.to_on_calendar() == "*-*-* 03:30:00"


def test_schedule_weekly_oncalendar():
    s = Schedule(kind=ScheduleKind.WEEKLY, day_of_week="Sun", time="21:15")
    assert s.to_on_calendar() == "Sun *-*-* 21:15:00"


def test_schedule_custom_passthrough():
    s = Schedule(kind=ScheduleKind.CUSTOM, custom_on_calendar="*-*-01 04:00:00")
    assert s.to_on_calendar() == "*-*-01 04:00:00"


def test_schedule_custom_empty_returns_none():
    s = Schedule(kind=ScheduleKind.CUSTOM, custom_on_calendar="   ")
    assert s.to_on_calendar() is None


def test_schedule_rejects_bad_time():
    with pytest.raises(ValueError):
        Schedule(kind=ScheduleKind.DAILY, time="3:30")
    with pytest.raises(ValueError):
        Schedule(kind=ScheduleKind.DAILY, time="25:00")


def test_schedule_rejects_bad_day():
    with pytest.raises(ValueError):
        Schedule(kind=ScheduleKind.WEEKLY, day_of_week="Funday")


def test_job_defaults_include_retention_and_schedule():
    j = _job()
    assert j.retention.is_active() is False
    assert j.schedule.kind is ScheduleKind.MANUAL
    assert j.auto_prune is False


def test_old_config_still_loads_with_defaults(tmp_path):
    """Backward-Compat: TOMLs ohne retention/schedule müssen weiter laden."""
    cfg_path = tmp_path / "old.toml"
    cfg_path.write_text(
        """\
[[jobs]]
id = "abc"
name = "Old"
sources = ["/x"]
tags = []
excludes = []

[jobs.target]
kind = "local"
path = "/y"
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert len(cfg.jobs) == 1
    assert cfg.jobs[0].schedule.kind is ScheduleKind.MANUAL
    assert cfg.jobs[0].retention.is_active() is False
    assert cfg.jobs[0].auto_prune is False


def test_full_roundtrip_with_retention_and_schedule(tmp_path):
    cfg_path = tmp_path / "c.toml"
    j = Job(
        name="Full",
        sources=["/src"],
        target=LocalTarget(path="/dst"),
        retention=RetentionPolicy(keep_daily=7, keep_weekly=4, keep_monthly=6),
        auto_prune=True,
        schedule=Schedule(kind=ScheduleKind.DAILY, time="04:15"),
    )
    save_config(AppConfig(jobs=[j]), cfg_path)

    loaded = load_config(cfg_path)
    j2 = loaded.jobs[0]
    assert j2.retention.keep_daily == 7
    assert j2.auto_prune is True
    assert j2.schedule.kind is ScheduleKind.DAILY
    assert j2.schedule.time == "04:15"
    assert j2.schedule.to_on_calendar() == "*-*-* 04:15:00"
