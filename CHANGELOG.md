# Changelog

Alle nennenswerten Änderungen an Back-Man stehen hier. Das Format orientiert
sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionsnummerierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [0.1.0] — 2026-05-16

Erste veröffentlichte Version. Funktional vollständig für den
Single-User-Desktop-Einsatz; Stabilität wird noch durch Praxis-Use
gehärtet.

### Hinzugefügt

- **Projekt-Grundgerüst:** XDG-konforme Pfade unter `~/.config/backman/`
  und `~/.local/share/backman/`, rotierende Datei-Logs plus
  GUI-Live-Queue, Restic-Verfügbarkeitscheck beim Start.
- **restic-Engine-Wrapper:** `ResticRunner` kapselt
  `init/backup/snapshots/forget/prune/restore/check` über `subprocess`.
  `backup()` streamt `--json`-Events live für die GUI-Progressbar.
  Fehler werden typisiert (`WrongPasswordError`, `RepoLockedError`,
  `RepoNotInitializedError`) anhand von Exit-Codes klassifiziert.
- **Keyring-Store:** Repo-Passwörter im Systemkeyring (Service-Name
  `backman`), Passwörter erreichen restic ausschließlich via Env-Var.
- **GUI (PySide6/Qt6):** Hauptfenster mit Job-Liste, Detail-/Snapshots-Tabs,
  Backup-Button und Live-Log-Dock. Job-Editor-Dialog (Allgemein / Aufbewahrung
  / Zeitplan) mit Pfad-Pickern. Jobs als TOML in
  `~/.config/backman/config.toml` persistiert (atomar via temp-file).
  Backup läuft in einem QThread; Engine-Events kommen via Qt-Signalen
  in die UI.
- **Snapshots & Restore:** Snapshots-Panel pro Job (Zeitpunkt, Tags,
  Short-ID, Pfade), Restore-Dialog mit Ziel an Originalort oder
  alternatives Verzeichnis, Snapshot-Löschen mit optional `--prune`,
  Repo-Check-Button.
- **Scheduler:** Pro Job werden `.service`- und `.timer`-Units nach
  `~/.config/systemd/user/` geschrieben; `systemctl --user` wrappt
  `daemon-reload/enable/disable/show`. `Persistent=true`, damit
  verpasste Läufe nachgeholt werden. Modi: manuell, täglich, wöchentlich,
  Custom-`OnCalendar`.
- **Retention:** `RetentionPolicy` pro Job
  (`keep_last/daily/weekly/monthly/yearly` + `auto_prune`-Flag). Bei
  erfolgreichem Backup läuft optional `forget` (+`prune`); Prune-Fehler
  sind nicht fatal, da die Daten bereits sicher im Repo liegen.
- **Headless-Modus:** `back-man --run-job <id>` lädt Config, zieht das
  Passwort ausschließlich aus dem Keyring (keine Prompts) und führt
  Backup + Retention aus. Aussagekräftige Exit-Codes (3–7) für systemd.
- **Notifications:** Desktop-Benachrichtigungen via `notify-send` für
  Backup-Erfolg/-Fehler, auch im Headless-Modus.
- **Tray-Icon:** System-Tray mit *Anzeigen* / *Beenden*. Schließen des
  Hauptfensters minimiert ins Tray, damit USB-Watcher und Timer im
  Hintergrund weiterlaufen.
- **USB-Watcher:** Beobachtet `/run/media/$USER` und `/media/$USER`
  via `QFileSystemWatcher`; benachrichtigt, sobald das Ziel-Verzeichnis
  eines Jobs auf einem neu eingehängten Datenträger verfügbar wird.
- **Verpackung:** `.desktop`-Datei und `packaging/build_deb.sh` bauen
  ein `.deb` mit gebündeltem Python-Venv unter `/opt/back-man/venv`.
  Reines `all`-Architektur-Paket, Abhängigkeiten: `python3 (>=3.10)`,
  `restic`, `libnotify-bin`, `libxcb-cursor0`.
- **Lizenz:** MIT.

### Stack

Python 3.10+, PySide6 ≥ 6.6, Pydantic ≥ 2.5, restic ≥ 0.16, `keyring`,
systemd User Units.

### Tests

105 Tests grün (Engine-Integration gegen echtes restic, GUI-Smoke
offscreen, Headless End-to-End, Scheduler-Units, Notifications,
USB-Watcher).
