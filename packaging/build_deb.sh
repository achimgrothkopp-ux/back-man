#!/usr/bin/env bash
# Baut ein .deb für Back-Man, das ein eigenständiges Python-Venv unter
# /opt/back-man/venv mitbringt. Funktioniert auf Linux Mint 21+/22 und
# Ubuntu/Debian aller Versionen mit Python 3.10+.
#
# Voraussetzungen auf dem Build-Rechner:
#   - python3 (>=3.10) mit venv-Modul
#   - dpkg-deb, fakeroot
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
ARCH="all"  # pure Python
DEB_NAME="${PKG_NAME}_${VERSION}_${ARCH}.deb"

INSTALL_PREFIX="/opt/back-man"
STAGE="$ROOT/dist/stage-deb"
DIST="$ROOT/dist"

echo "==> Back-Man $VERSION → $DEB_NAME"

# --- Aufräumen ------------------------------------------------------
rm -rf "$STAGE"
mkdir -p "$STAGE"

# --- DEBIAN/control -------------------------------------------------
mkdir -p "$STAGE/DEBIAN"
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

# --- Postinst (icon cache, daemon-reload) ---------------------------
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# Desktop-Datenbank refreshen (best effort)
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/prerm"

# --- Venv unter /opt/back-man/venv bauen ----------------------------
APP_DIR="$STAGE$INSTALL_PREFIX"
mkdir -p "$APP_DIR"
echo "==> Erstelle Venv in $APP_DIR/venv (mit System-Site-Packages aus)"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install "$ROOT" --quiet

# Sicherstellen, dass die Shebangs auf den Zielpfad zeigen.
# venv legt sie als /full/path/zum/build/.../bin/python ab — wir
# rewriten sie auf /opt/back-man/venv/bin/python.
echo "==> Rewriting shebangs auf $INSTALL_PREFIX/venv"
TARGET_PY="$INSTALL_PREFIX/venv/bin/python"
BUILD_PY="$APP_DIR/venv/bin/python"
# replace im pyvenv.cfg und in den Scripts unter venv/bin/
sed -i "s|$APP_DIR/venv|$INSTALL_PREFIX/venv|g" "$APP_DIR/venv/pyvenv.cfg"
for f in "$APP_DIR/venv/bin/"*; do
    # nur Textdateien anpacken
    if head -n1 "$f" 2>/dev/null | grep -q "^#!"; then
        sed -i "1s|.*|#!$TARGET_PY|" "$f"
    fi
done
# Symlinks unter venv/bin/python/python3 → eigene python-Binary korrekt halten
# (venv legt Symlinks an, die auf das Build-Python zeigen — wir wollen es weiterhin
# auf System-Python an Zielpfad → dpkg-Symlinks bleiben relativ zur venv).

# --- /usr/local/bin/back-man-Wrapper --------------------------------
mkdir -p "$STAGE/usr/local/bin"
cat > "$STAGE/usr/local/bin/back-man" <<EOF
#!/bin/sh
exec $INSTALL_PREFIX/venv/bin/back-man "\$@"
EOF
chmod 755 "$STAGE/usr/local/bin/back-man"

# --- .desktop-Datei -------------------------------------------------
mkdir -p "$STAGE/usr/share/applications"
cp "$ROOT/resources/back-man.desktop" "$STAGE/usr/share/applications/back-man.desktop"

# --- Größe für control --------------------------------------------------
SIZE_KB=$(du -sk "$APP_DIR" | cut -f1)
echo "Installed-Size: $SIZE_KB" >> "$STAGE/DEBIAN/control"

# --- .deb bauen -----------------------------------------------------
mkdir -p "$DIST"
echo "==> Baue $DIST/$DEB_NAME"
fakeroot dpkg-deb --build "$STAGE" "$DIST/$DEB_NAME"

# --- Aufräumen ------------------------------------------------------
rm -rf "$STAGE"

echo
echo "==> Fertig: $DIST/$DEB_NAME"
echo
echo "Installation auf Mint / Ubuntu / Debian:"
echo "  sudo apt install ./$DEB_NAME"
echo
echo "Deinstallation:"
echo "  sudo apt remove $PKG_NAME"
