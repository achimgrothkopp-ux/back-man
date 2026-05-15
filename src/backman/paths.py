"""XDG-konforme Pfade für Konfiguration, State und Logs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import APP_NAME


def _xdg(env_var: str, default_subpath: str) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value)
    return Path.home() / default_subpath


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    state_dir: Path
    log_dir: Path
    config_file: Path

    def ensure(self) -> None:
        for d in (self.config_dir, self.data_dir, self.state_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


def get_paths() -> AppPaths:
    config_dir = _xdg("XDG_CONFIG_HOME", ".config") / APP_NAME
    data_dir = _xdg("XDG_DATA_HOME", ".local/share") / APP_NAME
    state_dir = _xdg("XDG_STATE_HOME", ".local/state") / APP_NAME
    log_dir = data_dir / "logs"
    return AppPaths(
        config_dir=config_dir,
        data_dir=data_dir,
        state_dir=state_dir,
        log_dir=log_dir,
        config_file=config_dir / "config.toml",
    )
