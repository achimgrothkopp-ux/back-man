#!/usr/bin/env bash
# Baut ein .deb für Back-Man, das Wheels für Python 3.10–3.13 mitbringt.
# Das Venv wird *zur Installationszeit* im postinst auf dem Zielsystem
# mit dessen System-Python frisch angelegt — dadurch keine Python-
# Versions-Drift zwischen Build- und Zielmaschine (Mint 21=3.10,
# Mint 22=3.12, Debian 12=3.11, Kali rolling=3.13).
#
# Voraussetzungen auf dem Build-Rechner:
#   - python3 mit pip + venv
#   - dpkg-deb, fakeroot
#   - Internet (für `pip download` der Dependency-Wheels)
#   - apt install python3-venv python3-pip dpkg-dev fakeroot
#
# Nutzung:
#   bash packaging/build_deb.sh
#
# Ergebnis:
#   dist/back-man_<VERSION>_all.deb
set -euo pipefail

# --- Variablen ------------------------------------------------------
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PKG_NAME="back-man"
VERSION="$(grep -E '^version' "$ROOT/pyproject.toml" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
ARCH="all"
DEB_NAME="${PKG_NAME}_${VERSION}_${ARCH}.deb"

INSTALL_PREFIX="/opt/back-man"
STAGE="$ROOT/dist/stage-deb"
DIST="$ROOT/dist"

# Welche Python-Minor-Versionen sollen unterstützt werden?
# Override mit:  SUPPORTED_PY="3.10 3.12" bash packaging/build_deb.sh
SUPPORTED_PY="${SUPPORTED_PY:-3.10 3.11 3.12 3.13}"

echo "==> Back-Man $VERSION → $DEB_NAME"
echo "==> Ziel-Python-Versionen: $SUPPORTED_PY"

# --- Aufräumen ------------------------------------------------------
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN"

WHEEL_STAGE="$STAGE$INSTALL_PREFIX/wheels"
mkdir -p "$WHEEL_STAGE"

# --- Projekt-Wheel bauen --------------------------------------------
echo "==> Baue Projekt-Wheel"
python3 -m pip wheel \
    --no-deps \
    --wheel-dir "$WHEEL_STAGE" \
    "$ROOT" >/dev/null

# --- Requirements aus pyproject.toml extrahieren --------------------
REQ_FILE="$(mktemp)"
trap 'rm -f "$REQ_FILE"' EXIT

python3 - >"$REQ_FILE" <<EOF
import tomllib
with open("$ROOT/pyproject.toml", "rb") as f:
    d = tomllib.load(f)
for dep in d["project"]["dependencies"]:
    print(dep)
EOF

# --- Dependency-Wheels pro Ziel-Python sammeln ----------------------
echo "==> Sammle Dependency-Wheels"
for PYV in $SUPPORTED_PY; do
    PYV_NODOT="${PYV/./}"
    echo "    -> Python $PYV (cp${PYV_NODOT})"
    python3 -m pip download \
        --dest "$WHEEL_STAGE" \
        --only-binary=:all: \
        --python-version "$PYV" \
        --implementation cp \
        --abi "cp${PYV_NODOT}" \
        -r "$REQ_FILE" \
        >/dev/null
done

WHEEL_COUNT=$(find "$WHEEL_STAGE" -name '*.whl' | wc -l)
WHEEL_SIZE=$(du -sh "$WHEEL_STAGE" | cut -f1)
echo "==> $WHEEL_COUNT Wheels gesammelt ($WHEEL_SIZE)"

# --- DEBIAN/control -------------------------------------------------
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10), python3-venv, restic, libnotify-bin, libxcb-cursor0
Maintainer: Achim Grothkopp <achimgrothkopp@gmail.com>
Description: Qt-basierter Backup-Manager auf Basis von restic
 Back-Man ist ein grafischer Backup-Manager fuer Linux. Es nutzt restic
 fuer Deduplizierung und Verschluesselung und bietet Job-Verwaltung,
 Snapshot-Restore, Retention und systemd-Timer-Integration.
EOF

# --- postinst: Venv mit Ziel-Python anlegen + offline installieren --
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
PREFIX=/opt/back-man
VENV="$PREFIX/venv"

echo "Erstelle Back-Man Venv unter $VENV ..."
rm -rf "$VENV"
python3 -m venv "$VENV"

# Offline-Install aus mitgelieferten Wheels
"$VENV/bin/pip" install \
    --quiet \
    --disable-pip-version-check \
    --no-index \
    --find-links "$PREFIX/wheels" \
    back-man

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

# --- prerm / postrm -------------------------------------------------
cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/prerm"

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
case "$1" in
    purge|remove)
        rm -rf /opt/back-man/venv
        ;;
esac
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postrm"

# --- Wrapper unter /usr/local/bin/back-man --------------------------
mkdir -p "$STAGE/usr/local/bin"
cat > "$STAGE/usr/local/bin/back-man" <<EOF
#!/bin/sh
exec $INSTALL_PREFIX/venv/bin/back-man "\$@"
EOF
chmod 755 "$STAGE/usr/local/bin/back-man"

# --- .desktop-Datei -------------------------------------------------
mkdir -p "$STAGE/usr/share/applications"
cp "$ROOT/resources/back-man.desktop" "$STAGE/usr/share/applications/back-man.desktop"

# --- Größe für control ----------------------------------------------
SIZE_KB=$(du -sk "$STAGE$INSTALL_PREFIX" | cut -f1)
echo "Installed-Size: $SIZE_KB" >> "$STAGE/DEBIAN/control"

# --- .deb bauen -----------------------------------------------------
mkdir -p "$DIST"
echo "==> Baue $DIST/$DEB_NAME"
fakeroot dpkg-deb --build "$STAGE" "$DIST/$DEB_NAME"

rm -rf "$STAGE"

DEB_SIZE=$(du -h "$DIST/$DEB_NAME" | cut -f1)
echo
echo "==> Fertig: $DIST/$DEB_NAME ($DEB_SIZE)"
echo
echo "Installation auf Mint / Ubuntu / Debian:"
echo "  sudo apt install ./$DEB_NAME"
echo
echo "Hinweis: postinst baut bei jedem Install/Upgrade ein frisches Venv"
echo "mit dem System-Python und installiert offline aus /opt/back-man/wheels/."
echo
echo "Deinstallation:"
echo "  sudo apt remove $PKG_NAME"
