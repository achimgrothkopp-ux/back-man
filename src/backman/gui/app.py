"""QApplication-Bootstrap. Wird von `back-man` aufgerufen."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_DISPLAY_NAME, __version__
from ..logging_setup import setup_logging
from ..paths import get_paths
from ..restic_check import ResticNotFoundError, find_restic
from .main_window import MainWindow

log = logging.getLogger(__name__)


def run() -> int:
    paths = get_paths()
    paths.ensure()
    log_sink = setup_logging(paths.log_dir)
    log.info("%s %s startet (GUI)", APP_DISPLAY_NAME, __version__)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)

    try:
        info = find_restic()
        log.info("restic: %s", info.version)
    except ResticNotFoundError as exc:
        QMessageBox.critical(None, f"{APP_DISPLAY_NAME}: restic fehlt", str(exc))
        return 2

    window = MainWindow(paths=paths, log_sink=log_sink)
    window.show()
    return app.exec()
