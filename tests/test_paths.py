from pathlib import Path

from backupmanager.paths import APP_NAME, get_paths


def test_get_paths_uses_xdg_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    paths = get_paths()

    assert paths.config_dir == tmp_path / "cfg" / APP_NAME
    assert paths.data_dir == tmp_path / "data" / APP_NAME
    assert paths.state_dir == tmp_path / "state" / APP_NAME
    assert paths.log_dir == paths.data_dir / "logs"
    assert paths.config_file == paths.config_dir / "config.toml"


def test_ensure_creates_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    paths = get_paths()
    paths.ensure()

    for d in (paths.config_dir, paths.data_dir, paths.state_dir, paths.log_dir):
        assert Path(d).is_dir()


def test_get_paths_defaults_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = get_paths()

    assert paths.config_dir == tmp_path / ".config" / APP_NAME
    assert paths.data_dir == tmp_path / ".local" / "share" / APP_NAME
