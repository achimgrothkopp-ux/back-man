# Back-Man — Pakete und Installation

## Für End-User (Linux Mint, Ubuntu, Debian)

Das fertige `.deb` aus `dist/` installieren — keine Git-, Python- oder
Build-Kenntnisse nötig:

```bash
sudo apt install ./back-man_0.1.0_all.deb
```

`apt` zieht `restic`, `libnotify-bin` und alles andere als Abhängigkeiten
nach. Nach der Installation findet sich **Back-Man** im Anwendungsmenü
(Kategorie *Systemwerkzeuge* / *Archivierung*) oder lässt sich vom
Terminal aus per `back-man` starten.

**Voraussetzungen:** Linux Mint 21 / 22, Ubuntu 22.04+, Debian 12+
(alles mit Python 3.10 oder neuer; das ist Standard auf aktuellen
Mint- und Ubuntu-Versionen).

### Deinstallieren

```bash
sudo apt remove back-man
```

Konfiguration und Logs bleiben in `~/.config/backman/` und
`~/.local/share/backman/` erhalten.

---

## Für Entwickler / aus Quellen bauen

Das Paket wird auf einem beliebigen Debian-/Ubuntu-/Mint-System mit
einem Befehl gebaut:

```bash
# Build-Voraussetzungen einmalig:
sudo apt install python3-venv python3-pip dpkg-dev fakeroot

# Bauen:
bash packaging/build_deb.sh

# Ergebnis liegt in: dist/back-man_<VERSION>_all.deb
```

Das Script erstellt unter `dist/stage-deb/` einen sauberen
Verzeichnisbaum, baut darin ein dediziertes Python-Venv unter
`/opt/back-man/venv/`, rewritet alle Shebangs auf den Zielpfad und
verpackt das Ganze mit `dpkg-deb`. Größe: ~180 MB — vor allem PySide6
und Qt6.

### Was im Paket steckt

| Pfad                                     | Inhalt                              |
|------------------------------------------|--------------------------------------|
| `/opt/back-man/venv/`                    | Vollständiges Python-Venv inkl. PySide6 |
| `/usr/local/bin/back-man`                | Wrapper-Script (ruft das Venv-Binary) |
| `/usr/share/applications/back-man.desktop` | Eintrag fürs Anwendungsmenü        |

Abhängigkeiten aus dem `control`-File: `python3 (>= 3.10)`, `python3-venv`,
`restic`, `libnotify-bin`, `libxcb-cursor0`.
