"""Prüft, ob restic im PATH verfügbar ist, und liest die Version aus."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)


class ResticNotFoundError(RuntimeError):
    """Restic-Binary konnte nicht im PATH gefunden werden."""


@dataclass(frozen=True)
class ResticInfo:
    path: str
    version: str


def find_restic(binary: str = "restic") -> ResticInfo:
    path = shutil.which(binary)
    if path is None:
        raise ResticNotFoundError(
            f"'{binary}' wurde nicht im PATH gefunden. "
            "Installiere restic (z.B. `sudo apt install restic`) und versuche es erneut."
        )

    try:
        result = subprocess.run(
            [path, "version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ResticNotFoundError(
            f"'{path} version' konnte nicht ausgeführt werden: {exc}"
        ) from exc

    version = result.stdout.strip().splitlines()[0] if result.stdout else "unbekannt"
    log.info("restic gefunden: %s (%s)", path, version)
    return ResticInfo(path=path, version=version)
