#!/usr/bin/env bash
# Grant this user permission for system-wide key remapping (evdev + uinput).
set -euo pipefail

USER_NAME="${SUDO_USER:-$USER}"
echo "为用户 $USER_NAME 配置系统级改键权限…"

if ! getent group input >/dev/null; then
    groupadd input
fi
usermod -aG input "$USER_NAME"

RULE_SRC="$(cd "$(dirname "$0")" && pwd)/99-betterbluetooth-uinput.rules"
RULE_DST=/etc/udev/rules.d/99-betterbluetooth-uinput.rules
install -m 644 "$RULE_SRC" "$RULE_DST"
udevadm control --reload-rules
udevadm trigger --name-match=uinput || true
# Ensure node permissions apply immediately when possible.
if [ -e /dev/uinput ]; then
    chgrp input /dev/uinput || true
    chmod 0660 /dev/uinput || true
fi

echo
echo "完成。请注销并重新登录（或重启）后再打开 Better Bluetooth。"
echo "验证：ls -l /dev/uinput   应类似  crw-rw---- root input"
echo "      groups             应包含 input"
