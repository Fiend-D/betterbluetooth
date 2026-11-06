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
# Packaged builds must ship platform input deps; never tell end users to pip-install.
python -c "import os,sys; p='dist/linux/BetterBluetooth/_internal/evdev';
sys.exit(0 if os.path.isdir(p) else 'evdev missing from bundle')"

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
RUNTIME="${APPIMAGE_RUNTIME_FILE:-}"
if [ -z "$RUNTIME" ] && [ -f /runtime-x86_64 ]; then
    RUNTIME=/runtime-x86_64
fi
if [ -n "$RUNTIME" ]; then
    ARCH=x86_64 appimagetool --no-appstream --runtime-file "$RUNTIME" "$APPDIR" "$OUT/${NAME}.AppImage"
else
    ARCH=x86_64 appimagetool --no-appstream "$APPDIR" "$OUT/${NAME}.AppImage"
fi

# ---- tar.gz ----
STAGE=build/linux/$NAME
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$APP" "$STAGE/BetterBluetooth"
cp "$ICON" "$STAGE/betterbluetooth.png"
cp packaging/linux/install.sh "$STAGE/install.sh"
cp packaging/linux/setup-input-remap.sh "$STAGE/setup-input-remap.sh"
cp packaging/linux/99-betterbluetooth-uinput.rules "$STAGE/99-betterbluetooth-uinput.rules"
chmod +x "$STAGE/install.sh" "$STAGE/setup-input-remap.sh"
tar -C build/linux -czf "$OUT/${NAME}.tar.gz" "$NAME"

ls -lh "$OUT"
