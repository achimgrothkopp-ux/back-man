"""Dünner Wrapper um `systemctl --user`."""

from __future__ import annotations

import datetime as dt
import logging
import shutil
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)


class SystemctlError(RuntimeError):
    """systemctl-Aufruf ist fehlgeschlagen."""


@dataclass(frozen=True)
class TimerStatus:
    enabled: bool          # ob die .timer-Unit installiert ist
    active: bool           # ob sie gerade läuft / armed ist
    next_run: dt.datetime | None
    last_run: dt.datetime | None
    last_result: str       # "success", "exit-code", "failed", "" wenn unbekannt


def is_systemctl_available() -> bool:
    return shutil.which("systemctl") is not None


def _run(args: list[str], *, check: bool = True, timeout: float = 30) -> str:
    if not is_systemctl_available():
        raise SystemctlError("systemctl ist nicht im PATH verfügbar")
    cmd = ["systemctl", "--user", *args]
    log.debug("systemctl: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise SystemctlError(
            f"systemctl {args[0]} fehlgeschlagen (rc={result.returncode}): "
            f"{result.stderr.strip()[:400]}"
        )
    return result.stdout


def daemon_reload() -> None:
    """systemctl --user daemon-reload — nach Unit-File-Änderungen aufrufen."""
    _run(["daemon-reload"])



def enable_timer(timer_unit: str, *, now: bool = True) -> None:
    """`systemctl --user enable [--now] <timer>`."""
    args = ["enable"]
    if now:
        args.append("--now")
    args.append(timer_unit)
    _run(args)


def disable_timer(timer_unit: str, *, now: bool = True) -> None:
    """`systemctl --user disable [--now] <timer>`. Fehlt die Unit, wird das ignoriert."""
    args = ["disable"]
    if now:
        args.append("--now")
    args.append(timer_unit)
    try:
        _run(args)
    except SystemctlError as exc:
        # Wenn die Unit nicht (mehr) existiert, ist disable kein echter Fehler.
        if "not loaded" in str(exc).lower() or "no such file" in str(exc).lower():
            log.debug("disable ignoriert: %s", exc)
            return
        raise


def _parse_usec(value: str) -> dt.datetime | None:
    """systemd liefert Mikrosekunden seit Epoch in `*USec` Properties.

    0 oder leer bedeutet 'unbekannt' / 'noch nie'.
    """
    value = value.strip()
    if not value or value == "0":
        return None
    try:
        usec = int(value)
    except ValueError:
        return None
    if usec <= 0:
        return None
    return dt.datetime.fromtimestamp(usec / 1_000_000)


def show_timer_status(timer_unit: str) -> TimerStatus:
    """Liest Timer-Status via `systemctl show`. Niemals raise — gibt Defaults."""
    if not is_systemctl_available():
        return TimerStatus(False, False, None, None, "")
    try:
        out = _run(
            [
                "show",
                timer_unit,
                "--property=UnitFileState,ActiveState,NextElapseUSecRealtime,LastTriggerUSec,Result",
            ],
            check=False,
        )
    except SystemctlError:
        return TimerStatus(False, False, None, None, "")

    props: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()

    enabled = props.get("UnitFileState", "") in ("enabled", "enabled-runtime", "static")
    active = props.get("ActiveState", "") == "active"
    next_run = _parse_usec(props.get("NextElapseUSecRealtime", ""))
    last_run = _parse_usec(props.get("LastTriggerUSec", ""))
    result = props.get("Result", "")

    return TimerStatus(
        enabled=enabled,
        active=active,
        next_run=next_run,
        last_run=last_run,
        last_result=result,
    )
