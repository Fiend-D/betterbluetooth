#!/usr/bin/env bash
# Install Better Bluetooth for the current user (no root needed).
#   ./install.sh            install
#   ./install.sh --uninstall
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
TARGET="$PREFIX/betterbluetooth/app"
DESKTOP="$PREFIX/applications/betterbluetooth.desktop"
ICON="$PREFIX/icons/hicolor/256x256/apps/betterbluetooth.png"
BIN="$HOME/.local/bin/betterbluetooth"

if [ "${1:-}" = "--uninstall" ]; then
    pkill -f "$TARGET/BetterBluetooth" 2>/dev/null || true
    rm -rf "$TARGET" "$DESKTOP" "$ICON" "$BIN"
    rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/betterbluetooth.desktop"
    echo "已卸载（设置与电量历史保留在 ~/.config/betterbluetooth 与 ~/.local/share/betterbluetooth）"
    exit 0
fi

pkill -f "$TARGET/BetterBluetooth" 2>/dev/null || true
rm -rf "$TARGET"
mkdir -p "$TARGET" "$(dirname "$DESKTOP")" "$(dirname "$ICON")" "$(dirname "$BIN")"
cp -a "$HERE/BetterBluetooth/." "$TARGET/"
cp "$HERE/betterbluetooth.png" "$ICON"
ln -sf "$TARGET/BetterBluetooth" "$BIN"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Better Bluetooth
Comment=蓝牙设备管理与电量显示
Exec=$TARGET/BetterBluetooth
Icon=betterbluetooth
Categories=Utility;Settings;HardwareSettings;
StartupNotify=false
EOF

command -v update-desktop-database >/dev/null && update-desktop-database "$(dirname "$DESKTOP")" || true
echo "已安装到 $TARGET"
echo "可从应用菜单启动 Better Bluetooth，或运行：betterbluetooth"
