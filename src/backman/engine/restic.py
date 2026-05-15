"""Wrapper um die restic-CLI: init, backup, snapshots, forget, prune, restore, check."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .progress import ProgressEvent, SummaryEvent, parse_progress_lines
from .repo import Repository

log = logging.getLogger(__name__)

ProgressCallback = Callable[[ProgressEvent | SummaryEvent], None]


class ResticError(RuntimeError):
    """Allgemeiner restic-Fehler. `returncode` und `stderr` sind verfügbar."""

    def __init__(self, message: str, returncode: int = 0, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class WrongPasswordError(ResticError):
    """restic meldet wrong password / unable to open config."""


class RepoLockedError(ResticError):
    """Repo ist durch einen anderen Prozess gesperrt."""


@dataclass(frozen=True)
class Snapshot:
    id: str
    short_id: str
    time: str
    hostname: str
    username: str
    paths: tuple[str, ...]
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ForgetPolicy:
    keep_last: int | None = None
    keep_daily: int | None = None
    keep_weekly: int | None = None
    keep_monthly: int | None = None
    keep_yearly: int | None = None

    def to_args(self) -> list[str]:
        args: list[str] = []
        mapping = {
            "--keep-last": self.keep_last,
            "--keep-daily": self.keep_daily,
            "--keep-weekly": self.keep_weekly,
            "--keep-monthly": self.keep_monthly,
            "--keep-yearly": self.keep_yearly,
        }
        for flag, value in mapping.items():
            if value is not None and value > 0:
                args.extend([flag, str(value)])
        if not args:
            raise ValueError("ForgetPolicy hat keine keep-*-Werte gesetzt")
        return args


def _classify_error(returncode: int, stderr: str) -> ResticError:
    text = stderr.lower()
    if "wrong password" in text or "unable to open config" in text:
        return WrongPasswordError(
            f"Falsches Passwort oder beschädigtes Repo (rc={returncode})",
            returncode=returncode,
            stderr=stderr,
        )
    if "unable to create lock" in text or "repository is already locked" in text:
        return RepoLockedError(
            f"Repository ist gesperrt (rc={returncode})",
            returncode=returncode,
            stderr=stderr,
        )
    return ResticError(
        f"restic-Aufruf fehlgeschlagen (rc={returncode}): {stderr.strip()[:500]}",
        returncode=returncode,
        stderr=stderr,
    )


class ResticRunner:
    """Führt restic-Kommandos für ein konkretes Repository aus."""

    def __init__(
        self,
        repo: Repository,
        password: str,
        binary: str = "restic",
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.repo = repo
        self._password = password
        self.binary = binary
        self._extra_env = dict(extra_env or {})

    # ---- low-level ----------------------------------------------------

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["RESTIC_PASSWORD"] = self._password
        env["RESTIC_REPOSITORY"] = self.repo.url
        env.update(self._extra_env)
        return env

    def _run(self, args: list[str], *, timeout: float | None = None) -> str:
        cmd = [self.binary, *args]
        log.debug("restic-Aufruf: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                env=self._env(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise ResticError(f"restic-Binary nicht gefunden: {self.binary}") from exc

        if result.returncode != 0:
            raise _classify_error(result.returncode, result.stderr)
        return result.stdout

    # ---- public API ---------------------------------------------------

    def init(self) -> None:
        """Initialisiert das Repository. Wirft, falls schon vorhanden."""
        self._run(["init"])
        log.info("Repository initialisiert: %s", self.repo.url)

    def is_initialized(self) -> bool:
        """Prüft per `restic snapshots`, ob das Repo nutzbar ist."""
        try:
            self._run(["snapshots", "--json"], timeout=30)
            return True
        except WrongPasswordError:
            raise
        except ResticError:
            return False

    def snapshots(self) -> list[Snapshot]:
        stdout = self._run(["snapshots", "--json"], timeout=60)
        payload = json.loads(stdout or "[]")
        out: list[Snapshot] = []
        for s in payload:
            sid = str(s.get("id", ""))
            out.append(
                Snapshot(
                    id=sid,
                    short_id=str(s.get("short_id") or sid[:8]),
                    time=str(s.get("time", "")),
                    hostname=str(s.get("hostname", "")),
                    username=str(s.get("username", "")),
                    paths=tuple(s.get("paths") or ()),
                    tags=tuple(s.get("tags") or ()),
                )
            )
        return out

    def backup(
        self,
        sources: Iterable[Path | str],
        *,
        tags: Iterable[str] = (),
        excludes: Iterable[str] = (),
        on_event: ProgressCallback | None = None,
    ) -> SummaryEvent:
        """Führt ein Backup aus und liefert das SummaryEvent.

        Streamt restic-JSON-Events. `on_event` wird für jedes Event
        synchron aufgerufen (auch ProgressEvent).
        """
        src_list = [str(Path(s)) for s in sources]
        if not src_list:
            raise ValueError("Backup ohne Quellen ist nicht erlaubt")

        args = [self.binary, "backup", "--json"]
        for tag in tags:
            args.extend(["--tag", tag])
        for excl in excludes:
            args.extend(["--exclude", excl])
        args.extend(src_list)

        log.info("Starte Backup: %s", " ".join(args))
        proc = subprocess.Popen(
            args,
            env=self._env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None

        summary: SummaryEvent | None = None
        for event in parse_progress_lines(proc.stdout):
            if on_event is not None:
                on_event(event)
            if isinstance(event, SummaryEvent):
                summary = event

        stderr = proc.stderr.read() if proc.stderr else ""
        rc = proc.wait()
        if rc != 0:
            raise _classify_error(rc, stderr)
        if summary is None:
            raise ResticError(
                "restic backup beendet ohne summary-Event", returncode=rc, stderr=stderr
            )
        return summary

    def forget(self, policy: ForgetPolicy, *, prune: bool = False) -> None:
        args = ["forget", *policy.to_args()]
        if prune:
            args.append("--prune")
        self._run(args, timeout=None)

    def prune(self) -> None:
        self._run(["prune"], timeout=None)

    def check(self) -> bool:
        self._run(["check"], timeout=None)
        return True

    def restore(
        self,
        snapshot_id: str,
        target: Path | str,
        *,
        include: Iterable[str] = (),
    ) -> None:
        args = ["restore", snapshot_id, "--target", str(target)]
        for inc in include:
            args.extend(["--include", inc])
        self._run(args, timeout=None)
