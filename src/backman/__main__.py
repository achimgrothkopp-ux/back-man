"""CLI-Entry-Point. Initialisiert Pfade, Logging und prüft restic."""

from __future__ import annotations

import logging
import sys

from . import APP_DISPLAY_NAME, __version__
from .logging_setup import setup_logging
from .paths import get_paths
from .restic_check import ResticNotFoundError, find_restic


def main(argv: list[str] | None = None) -> int:
    paths = get_paths()
    paths.ensure()

    setup_logging(paths.log_dir)
    log = logging.getLogger("backman")

    log.info("%s %s startet", APP_DISPLAY_NAME, __version__)
    log.info("Config: %s", paths.config_file)
    log.info("Logs:   %s", paths.log_dir)

    try:
        info = find_restic()
    except ResticNotFoundError as exc:
        log.error("%s", exc)
        return 2

    log.info("Bereit. Verwende %s", info.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
