"""Passwort-Beschaffung für ein Repo: Keyring → Dialog → Keyring."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .. import keyring_store

log = logging.getLogger(__name__)


def get_or_prompt_password(repo_url: str, parent: QWidget | None = None) -> str | None:
    """Liefert ein Passwort für ein bestehendes Repo, fragt nötigenfalls den User.

    Reihenfolge:
      1. Keyring abfragen
      2. Wenn leer: QInputDialog (verstecktes Passwort)
      3. Eingabe in Keyring speichern (sodass künftige Läufe stumm sind)

    Gibt None zurück, wenn der User den Dialog abbricht.
    """
    existing = keyring_store.get_password(repo_url)
    if existing:
        log.debug("Passwort für %s aus Keyring", repo_url)
        return existing

    text, ok = QInputDialog.getText(
        parent,
        "Repository-Passwort",
        f"Passwort für Repository\n{repo_url}\neingeben:",
        QLineEdit.EchoMode.Password,
    )
    if not ok or not text:
        return None
    _store_password(repo_url, text)
    return text


def prompt_new_password(repo_url: str, parent: QWidget | None = None) -> str | None:
    """Dialog für ein neu anzulegendes Repo: zwei Passwortfelder mit Vergleich.

    Gibt None bei Abbruch zurück, sonst das gewählte Passwort (und
    speichert es bereits im Keyring).
    """
    dialog = _NewPasswordDialog(repo_url, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    pw = dialog.password()
    if not pw:
        return None
    _store_password(repo_url, pw)
    return pw


def forget_password(repo_url: str) -> None:
    """Entfernt ein Passwort aus dem Keyring (z.B. nach WrongPasswordError)."""
    try:
        keyring_store.delete_password(repo_url)
    except keyring_store.KeyringUnavailableError as exc:
        log.warning("Passwort konnte nicht aus Keyring entfernt werden: %s", exc)


def _store_password(repo_url: str, password: str) -> None:
    try:
        keyring_store.set_password(repo_url, password)
    except keyring_store.KeyringUnavailableError as exc:
        log.warning("Passwort konnte nicht im Keyring abgelegt werden: %s", exc)


class _NewPasswordDialog(QDialog):
    """Eigene Dialogklasse, weil QInputDialog nur ein Feld hat."""

    def __init__(self, repo_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Neues Repository — Passwort wählen")
        self.setModal(True)

        intro = QLabel(
            "Das Repository\n"
            f"<code>{repo_url}</code>\n"
            "existiert noch nicht. Wähle ein Passwort. <b>Wichtig:</b> "
            "restic verschlüsselt damit alle Daten — ohne dieses Passwort "
            "ist das Backup nicht wiederherstellbar."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)

        self._pw1 = QLineEdit()
        self._pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw2 = QLineEdit()
        self._pw2.setEchoMode(QLineEdit.EchoMode.Password)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #c00;")
        self._error_label.setVisible(False)

        form = QFormLayout()
        form.addRow("Passwort:", self._pw1)
        form.addRow("Wiederholen:", self._pw2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addLayout(form)
        root.addWidget(self._error_label)
        root.addWidget(buttons)

    def _on_accept(self) -> None:
        p1, p2 = self._pw1.text(), self._pw2.text()
        if not p1:
            self._show_error("Passwort darf nicht leer sein.")
            return
        if p1 != p2:
            self._show_error("Die beiden Passwörter stimmen nicht überein.")
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.setVisible(True)

    def password(self) -> str:
        return self._pw1.text()
