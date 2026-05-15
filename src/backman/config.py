"""Job-Konfiguration: Pydantic-Modelle und TOML-Persistenz."""

from __future__ import annotations

import logging
import os
import tomllib
import uuid
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel, Field, field_validator

from .engine.repo import Repository, local_repo

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


class Job(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str
    sources: list[str]
    target: Target
    tags: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)

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
