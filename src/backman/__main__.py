"""CLI-Entry-Point — startet die GUI."""

from __future__ import annotations

import sys

from .gui.app import run


def main(argv: list[str] | None = None) -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
