"""Speichert restic-Repo-Passwörter im Systemkeyring (Secret Service)."""

from __future__ import annotations

import logging

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE_NAME = "back-man"

log = logging.getLogger(__name__)


class KeyringUnavailableError(RuntimeError):
    """Der Systemkeyring konnte nicht angesprochen werden."""


def get_password(repo_url: str) -> str | None:
    """Liest das Passwort für ein Repo aus dem Keyring. None wenn nicht gesetzt."""
    try:
        return keyring.get_password(SERVICE_NAME, repo_url)
    except KeyringError as exc:
        raise KeyringUnavailableError(f"Keyring nicht erreichbar: {exc}") from exc


def set_password(repo_url: str, password: str) -> None:
    """Speichert das Passwort für ein Repo im Keyring."""
    if not password:
        raise ValueError("Passwort darf nicht leer sein.")
    try:
        keyring.set_password(SERVICE_NAME, repo_url, password)
    except KeyringError as exc:
        raise KeyringUnavailableError(f"Keyring nicht erreichbar: {exc}") from exc
    log.info("Passwort für Repo %s im Keyring gespeichert", repo_url)


def delete_password(repo_url: str) -> bool:
    """Löscht ein Repo-Passwort aus dem Keyring. True wenn etwas gelöscht wurde."""
    try:
        keyring.delete_password(SERVICE_NAME, repo_url)
        log.info("Passwort für Repo %s gelöscht", repo_url)
        return True
    except PasswordDeleteError:
        return False
    except KeyringError as exc:
        raise KeyringUnavailableError(f"Keyring nicht erreichbar: {exc}") from exc
