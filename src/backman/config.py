"""Job-Konfiguration: Pydantic-Modelle und TOML-Persistenz."""

from __future__ import annotations

import logging
import os
import re
import uuid
from enum import Enum
from pathlib import Path
from typing import Literal

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w
from pydantic import BaseModel, Field, field_validator

from .engine.repo import Repository, local_repo
from .engine.restic import ForgetPolicy

log = logging.getLogger(__name__)


class LocalTarget(BaseModel):
    kind: Literal["local"] = "local"
    path: str

    def to_repository(self) -> Repository:
        return local_repo(self.path)

    @property
    def repo_url(self) -> str:
        return self.to_repository().url


# Wenn in einer späteren Iteration SFTP dazukommt, einfach ergänzen und
# `Target = LocalTarget | SftpTarget` umstellen (Pydantic-Discriminated-Union).
Target = LocalTarget


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class RetentionPolicy(BaseModel):
    """keep-Werte für `restic forget`. 0 = nicht gesetzt."""

    keep_last: int = 0
    keep_daily: int = 0
    keep_weekly: int = 0
    keep_monthly: int = 0
    keep_yearly: int = 0

    def is_active(self) -> bool:
        return any(v > 0 for v in (
            self.keep_last,
            self.keep_daily,
            self.keep_weekly,
            self.keep_monthly,
            self.keep_yearly,
        ))

    def to_forget_policy(self) -> ForgetPolicy | None:
        if not self.is_active():
            return None
        return ForgetPolicy(
            keep_last=self.keep_last or None,
            keep_daily=self.keep_daily or None,
            keep_weekly=self.keep_weekly or None,
            keep_monthly=self.keep_monthly or None,
            keep_yearly=self.keep_yearly or None,
        )


class ScheduleKind(str, Enum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"


_DOW = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_HHMM = re.compile(r"^\d{2}:\d{2}$")


class Schedule(BaseModel):
    """Wann ein Job automatisch ausgeführt wird."""

    kind: ScheduleKind = ScheduleKind.MANUAL
    time: str = "03:00"        # HH:MM für DAILY/WEEKLY
    day_of_week: str = "Mon"   # für WEEKLY
    custom_on_calendar: str = ""

    @field_validator("time")
    @classmethod
    def _time_format(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("time muss HH:MM sein, z.B. '03:00'")
        hh, mm = (int(x) for x in v.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError("Ungültige Uhrzeit")
        return v

    @field_validator("day_of_week")
    @classmethod
    def _day_valid(cls, v: str) -> str:
        if v not in _DOW:
            raise ValueError(f"day_of_week muss aus {_DOW} sein")
        return v

    def to_on_calendar(self) -> str | None:
        """OnCalendar-Ausdruck für die systemd-Timer-Unit, None = kein Timer."""
        if self.kind is ScheduleKind.MANUAL:
            return None
        if self.kind is ScheduleKind.DAILY:
            return f"*-*-* {self.time}:00"
        if self.kind is ScheduleKind.WEEKLY:
            return f"{self.day_of_week} *-*-* {self.time}:00"
        if self.kind is ScheduleKind.CUSTOM:
            expr = self.custom_on_calendar.strip()
            return expr or None
        return None


class Job(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str
    sources: list[str]
    target: Target
    tags: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    retention: RetentionPolicy = Field(default_factory=RetentionPolicy)
    auto_prune: bool = False
    schedule: Schedule = Field(default_factory=Schedule)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Job-Name darf nicht leer sein")
        return v.strip()

    @field_validator("sources")
    @classmethod
    def _sources_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Mindestens eine Quelle ist erforderlich")
        return v


class AppConfig(BaseModel):
    jobs: list[Job] = Field(default_factory=list)

    def get_job(self, job_id: str) -> Job | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def upsert_job(self, job: Job) -> None:
        for i, existing in enumerate(self.jobs):
            if existing.id == job.id:
                self.jobs[i] = job
                return
        self.jobs.append(job)

    def remove_job(self, job_id: str) -> bool:
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j.id != job_id]
        return len(self.jobs) < before


def load_config(path: Path) -> AppConfig:
    """Lädt Config aus TOML-Datei. Leere AppConfig wenn Datei fehlt."""
    if not path.exists():
        log.info("Config %s existiert nicht, starte mit leerer Konfiguration", path)
        return AppConfig()
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Config {path} ist kein gültiges TOML: {exc}") from exc
    return AppConfig.model_validate(raw)


def save_config(config: AppConfig, path: Path) -> None:
    """Schreibt Config atomisch (temp-file + rename) in TOML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as fh:
        tomli_w.dump(payload, fh)
    os.replace(tmp, path)
    log.debug("Config nach %s geschrieben", path)
