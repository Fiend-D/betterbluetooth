#!/usr/bin/env bash
# Runs inside the build container: PyInstaller build -> AppImage + tar.gz in release/.
set -euo pipefail
cd /src

VERSION=$(python -c "import betterbluetooth; print(betterbluetooth.__version__)")
NAME="BetterBluetooth-${VERSION}-linux-x86_64"
OUT=/src/release
mkdir -p "$OUT"

python build.py

APP=dist/linux/BetterBluetooth
ICON=build/linux/icon.png

"$APP/BetterBluetooth" --self-test

# Font stack must match the host's fontconfig configuration; every desktop ships it.
rm -f "$APP"/_internal/libfontconfig.so* "$APP"/_internal/libfreetype.so*

# ---- AppImage ----
APPDIR=build/linux/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$APP" "$APPDIR/usr/lib/betterbluetooth"
cp "$ICON" "$APPDIR/betterbluetooth.png"
cp "$ICON" "$APPDIR/usr/share/icons/hicolor/256x256/apps/betterbluetooth.png"
cat > "$APPDIR/betterbluetooth.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Better Bluetooth
Comment=Bluetooth device manager with battery tray icons
Exec=BetterBluetooth
Icon=betterbluetooth
Categories=Utility;Settings;HardwareSettings;
StartupNotify=false
EOF
cp "$APPDIR/betterbluetooth.desktop" "$APPDIR/usr/share/applications/"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/betterbluetooth/BetterBluetooth" "$@"
EOF
chmod +x "$APPDIR/AppRun"
ARCH=x86_64 appimagetool --no-appstream "$APPDIR" "$OUT/${NAME}.AppImage"

# ---- tar.gz ----
STAGE=build/linux/$NAME
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$APP" "$STAGE/BetterBluetooth"
cp "$ICON" "$STAGE/betterbluetooth.png"
cp packaging/linux/install.sh "$STAGE/install.sh"
chmod +x "$STAGE/install.sh"
tar -C build/linux -czf "$OUT/${NAME}.tar.gz" "$NAME"

ls -lh "$OUT"
