import pytest

from backman.config import AppConfig, Job, LocalTarget, load_config, save_config


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
