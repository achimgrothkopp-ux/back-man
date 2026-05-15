"""Desktop-Notifications via `notify-send`.

Dünner Wrapper, der bei fehlender Binary nicht crasht, sondern still
no-op-t. Wird sowohl im GUI- als auch im Headless-Modus benutzt.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger(__name__)

APP_NAME = "Back-Man"


def is_available() -> bool:
    return shutil.which("notify-send") is not None


def notify(
    summary: str,
    body: str = "",
    *,
    urgency: str = "normal",
    icon: str | None = None,
    timeout_ms: int | None = None,
) -> bool:
    """Sendet eine Desktop-Notification. Gibt True zurück, wenn ausgeliefert.

    `urgency`: 'low', 'normal' oder 'critical'.
    `timeout_ms`: None = vom System bestimmt.
    """
    if not is_available():
        log.debug("notify-send fehlt — Notification übersprungen: %s", summary)
        return False
    if urgency not in ("low", "normal", "critical"):
        urgency = "normal"

    args = ["notify-send", "--app-name", APP_NAME, "--urgency", urgency]
    if icon:
        args += ["--icon", icon]
    if timeout_ms is not None:
        args += ["--expire-time", str(int(timeout_ms))]
    args += [summary]
    if body:
        args += [body]

    try:
        subprocess.run(args, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("notify-send fehlgeschlagen: %s", exc)
        return False
    return True


def notify_success(summary: str, body: str = "") -> bool:
    return notify(summary, body, urgency="normal")


def notify_failure(summary: str, body: str = "") -> bool:
    return notify(summary, body, urgency="critical")
