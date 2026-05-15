"""CLI-Entry-Point.

Ohne Argumente: startet die GUI.
Mit `--run-job <ID>`: führt den Job headless aus (für systemd-Timer).
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--run-job":
        from .headless import main as headless_main

        return headless_main(args)
    from .gui.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
