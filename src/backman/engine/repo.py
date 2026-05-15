"""Repository-Modell und Helper für restic-Backend-URLs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class BackendKind(str, Enum):
    LOCAL = "local"
    SFTP = "sftp"


@dataclass(frozen=True)
class Repository:
    """Beschreibt ein restic-Repository ohne das Passwort.

    `url` ist die restic-Repository-URL (z.B. "/mnt/backup" oder
    "sftp:user@host:/srv/restic"). NFS- und SMB-Ziele werden vor dem Aufruf
    in einen lokalen Mount-Pfad aufgelöst und kommen hier als LOCAL an.
    """

    url: str
    kind: BackendKind = BackendKind.LOCAL
    label: str = ""


def local_repo(path: Path | str, label: str = "") -> Repository:
    """Erzeugt ein Repository auf einem lokalen Pfad oder Mount-Pfad."""
    abspath = str(Path(path).expanduser().resolve())
    return Repository(url=abspath, kind=BackendKind.LOCAL, label=label or abspath)


def sftp_repo(user: str, host: str, path: str, label: str = "") -> Repository:
    """Erzeugt ein Repository über SFTP, Format `sftp:user@host:/pfad`."""
    if not user or not host or not path:
        raise ValueError("user, host und path müssen gesetzt sein")
    if not path.startswith("/"):
        raise ValueError("path muss absolut sein (mit / beginnen)")
    url = f"sftp:{user}@{host}:{path}"
    return Repository(url=url, kind=BackendKind.SFTP, label=label or f"{host}:{path}")
