"""System-Tray-Icon für Back-Man.

Das Hauptfenster bleibt beim Schließen erhalten und wandert ins Tray —
so kann der Hintergrund-Watcher (USB-Auto-Erkennung) weiterlaufen.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QStyle, QSystemTrayIcon

log = logging.getLogger(__name__)


def is_tray_available() -> bool:
    """Manche Desktop-Umgebungen haben kein funktionierendes Tray."""
    return QSystemTrayIcon.isSystemTrayAvailable()


class TrayIcon(QObject):
    """Tray-Icon mit Menü 'Hauptfenster anzeigen' + 'Beenden'."""

    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, app_name: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app_name = app_name
        # Standard-Qt-Icon als Platzhalter, bis wir ein eigenes haben
        from PySide6.QtWidgets import QApplication

        style = QApplication.instance().style() if QApplication.instance() else None
        icon = style.standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon) if style else QIcon()

        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip(app_name)

        menu = QMenu()
        show_action = QAction("Hauptfenster anzeigen", self)
        show_action.triggered.connect(self.show_requested.emit)
        quit_action = QAction("Beenden", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._menu = menu

        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Doppelklick / Trigger holt das Fenster zurück
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_requested.emit()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def is_visible(self) -> bool:
        return self._tray.isVisible()
