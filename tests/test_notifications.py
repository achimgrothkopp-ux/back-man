"""Tests für notify-send-Wrapper."""

from __future__ import annotations

from backman import notifications


def test_notify_returns_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr(notifications.shutil, "which", lambda _x: None)
    assert notifications.notify("hi") is False


def test_notify_calls_subprocess(monkeypatch):
    monkeypatch.setattr(notifications.shutil, "which", lambda _x: "/usr/bin/notify-send")
    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(args)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(notifications.subprocess, "run", fake_run)

    ok = notifications.notify("Backup fertig", "Snapshot abc12345", urgency="normal")
    assert ok is True
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "notify-send"
    assert "Backup fertig" in cmd
    assert "Snapshot abc12345" in cmd
    assert "--urgency" in cmd and "normal" in cmd
    assert "--app-name" in cmd
    assert "Back-Man" in cmd


def test_notify_failure_uses_critical_urgency(monkeypatch):
    monkeypatch.setattr(notifications.shutil, "which", lambda _x: "/usr/bin/notify-send")
    captured: list[list[str]] = []
    monkeypatch.setattr(
        notifications.subprocess, "run", lambda args, **_kw: captured.append(args) or type("R", (), {"returncode": 0})()
    )

    notifications.notify_failure("Backup fehlgeschlagen")
    assert "critical" in captured[0]


def test_notify_with_invalid_urgency_falls_back_to_normal(monkeypatch):
    monkeypatch.setattr(notifications.shutil, "which", lambda _x: "/usr/bin/notify-send")
    captured: list[list[str]] = []
    monkeypatch.setattr(
        notifications.subprocess, "run", lambda args, **_kw: captured.append(args) or type("R", (), {"returncode": 0})()
    )
    notifications.notify("hi", urgency="bogus")
    assert "normal" in captured[0]
    assert "bogus" not in captured[0]


def test_notify_returns_false_on_subprocess_error(monkeypatch):
    monkeypatch.setattr(notifications.shutil, "which", lambda _x: "/usr/bin/notify-send")

    def boom(*_args, **_kwargs):
        raise OSError("missing")

    monkeypatch.setattr(notifications.subprocess, "run", boom)
    assert notifications.notify("x") is False
