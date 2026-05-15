"""Headless-Backup-Lauf für systemd-Timer-Aufrufe.

Aufruf: `back-man --run-job <ID>`. Liest Passwort ausschließlich aus dem
Keyring (kein interaktiver Prompt), führt das Backup aus und optional
Retention/Prune, schreibt alles ins Logfile und beendet sich mit einem
aussagekräftigen Exit-Code.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from . import APP_DISPLAY_NAME, __version__, keyring_store
from .config import Job, load_config
from .engine import ResticRunner, WrongPasswordError
from .logging_setup import setup_logging
from .paths import get_paths
from .restic_check import ResticNotFoundError, find_restic


# Exit-Codes
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_RESTIC_MISSING = 3
EXIT_JOB_NOT_FOUND = 4
EXIT_PASSWORD_MISSING = 5
EXIT_WRONG_PASSWORD = 6
EXIT_BACKUP_FAILED = 7


def run_job_headless(job_id: str) -> int:
    paths = get_paths()
    paths.ensure()
    setup_logging(paths.log_dir)
    log = logging.getLogger("backman.headless")

    log.info("%s %s — Headless-Lauf für Job %s", APP_DISPLAY_NAME, __version__, job_id)

    try:
        info = find_restic()
        log.info("restic: %s", info.version)
    except ResticNotFoundError as exc:
        log.error("restic fehlt: %s", exc)
        return EXIT_RESTIC_MISSING

    config = load_config(paths.config_file)
    job = config.get_job(job_id)
    if job is None:
        log.error("Job mit ID '%s' nicht in Config gefunden", job_id)
        return EXIT_JOB_NOT_FOUND

    repo_url = job.target.repo_url

    try:
        password = keyring_store.get_password(repo_url)
    except keyring_store.KeyringUnavailableError as exc:
        log.error(
            "Keyring nicht erreichbar (entsperrte graphische Session "
            "erforderlich): %s",
            exc,
        )
        return EXIT_PASSWORD_MISSING

    if not password:
        log.error(
            "Kein Passwort im Keyring für Repo %s. Bitte einmal interaktiv "
            "via GUI ausführen, damit das Passwort gespeichert wird.",
            repo_url,
        )
        return EXIT_PASSWORD_MISSING

    runner = ResticRunner(job.target.to_repository(), password=password)
    sources = [Path(s) for s in job.sources]

    try:
        log.info("Starte Backup '%s' (%d Quellen)", job.name, len(sources))
        summary = runner.backup(
            sources,
            tags=job.tags,
            excludes=job.excludes,
        )
    except WrongPasswordError as exc:
        log.error("Falsches Passwort für %s: %s", repo_url, exc)
        return EXIT_WRONG_PASSWORD
    except Exception as exc:  # noqa: BLE001
        log.exception("Backup fehlgeschlagen: %s", exc)
        return EXIT_BACKUP_FAILED

    log.info(
        "Backup OK: snapshot=%s, neu=%d, geändert=%d, +%d Bytes",
        summary.snapshot_id[:8],
        summary.files_new,
        summary.files_changed,
        summary.data_added,
    )

    # Optional: Retention
    if job.auto_prune and job.retention.is_active():
        policy = job.retention.to_forget_policy()
        try:
            log.info("Wende Retention an: %s", policy)
            runner.forget(policy, prune=True)
            log.info("Retention/Prune erfolgreich")
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "Retention/Prune fehlgeschlagen — Backup selbst ist OK: %s", exc
            )
            # Backup war erfolgreich, also kein non-zero Exit.

    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or len(argv) < 2 or argv[0] != "--run-job":
        print("Usage: back-man --run-job <JOB_ID>", file=sys.stderr)
        return EXIT_USAGE
    return run_job_headless(argv[1])


if __name__ == "__main__":
    sys.exit(main())
