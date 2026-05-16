# Back-Man

**Back-Man** ist ein grafischer Backup-Manager für den Linux-Desktop. Er nutzt
[restic](https://restic.net/) als Engine — damit gibt es Deduplizierung,
Verschlüsselung und inkrementelle Snapshots ohne Eigenbau — und legt eine
freundliche Qt-Oberfläche darüber. Gedacht ist Back-Man für Userdaten
(`$HOME`), nicht für System-Backups, und läuft ausschließlich als normaler
User ohne `sudo` oder `polkit`.

## Features

- **Jobs verwalten:** mehrere Backup-Jobs mit eigenen Quellen, Excludes,
  Tags und Retention-Regeln
- **Backup-Ziele:** lokale Pfade und externe Wechseldatenträger (mit
  automatischer Erkennung beim Anstecken)
- **Snapshots & Restore:** Snapshot-Liste pro Job, Dateien per Dialog
  wiederherstellen — entweder an den Originalort oder in ein Zielverzeichnis
- **Scheduler:** automatische Läufe via systemd User Timers
  (täglich/wöchentlich/Custom-OnCalendar), kein Cron, kein eigener Daemon
- **Retention:** restic-Forget-Policy pro Job konfigurierbar
  (`keep-last/daily/weekly/monthly/yearly`), optional mit Auto-Prune
- **Repo-Passwort:** sicher im Systemkeyring (Secret Service /
  GNOME-Keyring) statt in Klartextdateien
- **Tray-Icon & Desktop-Notifications:** unauffällig im Hintergrund,
  meldet Erfolg/Fehler via `libnotify`
- **Live-Log-Panel:** restic-Ausgabe direkt in der GUI, dazu rotierende
  Logdateien unter `~/.local/share/backman/logs/`

## Installation (Linux Mint / Ubuntu / Debian)

```bash
sudo apt install ./dist/back-man_0.1.0_all.deb
```

`apt` zieht `restic`, `libnotify-bin` und die übrigen Abhängigkeiten
automatisch nach. Nach der Installation findet sich Back-Man im
Anwendungsmenü unter *Systemwerkzeuge* / *Archivierung* oder lässt sich
vom Terminal aus per `back-man` starten.

**Voraussetzungen:** Linux Mint 21/22, Ubuntu 22.04+, Debian 12+ —
Python 3.10 oder neuer (Standard auf aktuellen Versionen).

Deinstallation:

```bash
sudo apt remove back-man
```

Konfiguration und Logs bleiben dabei in `~/.config/backman/` und
`~/.local/share/backman/` erhalten.

## Quick-Start

1. Back-Man starten (Menü oder `back-man` im Terminal).
2. Über *Neuer Job* eine erste Konfiguration anlegen:
   - **Name** und **Quell-Pfade** festlegen
   - **Ziel**: lokales Verzeichnis oder Wechseldatenträger wählen
   - **Repo-Passwort** setzen — wird im Keyring abgelegt
   - optional **Retention** und **Schedule** konfigurieren
3. *Jetzt sichern* drückt den ersten Lauf an. Beim ersten Mal initialisiert
   Back-Man das restic-Repo automatisch.
4. Snapshots & Restore über den Snapshot-Tab pro Job.

## Aus den Quellen bauen

### Entwicklung

```bash
git clone <repo-url> backupmanager
cd backupmanager
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/back-man            # GUI starten
.venv/bin/python -m pytest    # Tests laufen lassen
```

### .deb-Paket bauen

```bash
sudo apt install python3-venv python3-pip dpkg-dev fakeroot
bash packaging/build_deb.sh
# Ergebnis: dist/back-man_<VERSION>_all.deb
```

Das Build-Script erstellt unter `dist/stage-deb/` ein eigenständiges
Python-Venv unter `/opt/back-man/venv/`, rewritet Shebangs auf den
Zielpfad und packt alles mit `dpkg-deb`. Siehe
[`packaging/README.md`](packaging/README.md) für Details.

## Wo Back-Man Daten ablegt

| Pfad                                       | Inhalt                                |
|--------------------------------------------|---------------------------------------|
| `~/.config/backman/config.toml`            | Job-Konfiguration                     |
| `~/.local/share/backman/logs/`             | Rotierende Logdateien                 |
| `~/.local/state/backman/`                  | Laufzeit-State                        |
| `~/.config/systemd/user/backman-job-*.timer` | systemd-Timer pro Job (bei Schedule) |
| Systemkeyring                              | Repo-Passwörter (Schlüssel `backman`) |

Die restic-Repos selbst leben dort, wo das Job-Ziel hinzeigt
(z.B. `/mnt/backup-disk/restic-repo`).

## Stack

Python 3.10+, PySide6 (Qt6), Pydantic v2, restic ≥ 0.16, `keyring`,
systemd User Units.

## Lizenz

MIT — siehe [`LICENSE`](LICENSE).
