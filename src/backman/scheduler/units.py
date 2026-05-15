"""Generierung von systemd-User-Unit-Files für Back-Man-Jobs.

Eine Unit besteht aus zwei Dateien:
  - back-man-job-<id>.service  → einmaliger Backup-Aufruf via `back-man --run-job <id>`
  - back-man-job-<id>.timer    → OnCalendar-Trigger für die .service

Beide werden in `~/.config/systemd/user/` abgelegt.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from ..config import Job

log = logging.getLogger(__name__)


def units_dir() -> Path:
    """Pfad zu ~/.config/systemd/user/, XDG-konform."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "systemd" / "user"
    return Path.home() / ".config" / "systemd" / "user"


def job_unit_basename(job: Job) -> str:
    return f"back-man-job-{job.id}"


def job_service_path(job: Job) -> Path:
    return units_dir() / f"{job_unit_basename(job)}.service"


def job_timer_path(job: Job) -> Path:
    return units_dir() / f"{job_unit_basename(job)}.timer"


def _back_man_binary() -> str:
    """Pfad zum `back-man`-Executable im aktuellen venv (bzw. PATH)."""
    found = shutil.which("back-man")
    if found:
        return found
    # Fallback — wir geben einen sicheren Befehl raus, der zumindest debuggbar ist.
    return "back-man"


def render_service_unit(job: Job) -> str:
    binary = _back_man_binary()
    return (
        "[Unit]\n"
        f"Description=Back-Man Backup-Job: {job.name}\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={binary} --run-job {job.id}\n"
        # Keine Restart-Policy: bei Timern reicht 'oneshot'.
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def render_timer_unit(job: Job, on_calendar: str) -> str:
    return (
        "[Unit]\n"
        f"Description=Back-Man Timer: {job.name}\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar={on_calendar}\n"
        # Persistent=true: verpasste Läufe werden nachgeholt, sobald der User
        # sich anmeldet — wichtig für Desktops, die nachts nicht laufen.
        "Persistent=true\n"
        f"Unit={job_unit_basename(job)}.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def write_units(job: Job, on_calendar: str) -> tuple[Path, Path]:
    """Schreibt .service und .timer atomisch in units_dir().

    Gibt (service_path, timer_path) zurück. Der Aufrufer ist für
    `systemctl --user daemon-reload` und enable/start verantwortlich.
    """
    d = units_dir()
    d.mkdir(parents=True, exist_ok=True)

    sp = job_service_path(job)
    tp = job_timer_path(job)

    _write_atomic(sp, render_service_unit(job))
    _write_atomic(tp, render_timer_unit(job, on_calendar))
    log.info("Unit-Dateien geschrieben: %s, %s", sp.name, tp.name)
    return sp, tp


def remove_units(job: Job) -> tuple[bool, bool]:
    """Entfernt .service und .timer. Gibt (service_existed, timer_existed)."""
    sp = job_service_path(job)
    tp = job_timer_path(job)
    s_existed = sp.exists()
    t_existed = tp.exists()
    sp.unlink(missing_ok=True)
    tp.unlink(missing_ok=True)
    if s_existed or t_existed:
        log.info("Unit-Dateien entfernt: %s", job_unit_basename(job))
    return s_existed, t_existed


def _write_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
