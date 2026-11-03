#!/usr/bin/env bash
# Build the Windows release on Linux through Wine: portable zip + single-file exe in release/.
# First run installs a private Windows Python into $WINEPREFIX (default ~/.cache/bb-wine).
set -euo pipefail
cd "$(dirname "$0")/../.."

export WINEPREFIX="${WINEPREFIX:-$HOME/.cache/bb-wine}" WINEDEBUG=-all WINEARCH=win64
PY='C:\Python312\python.exe'
PY_VERSION=3.12.10

if [ ! -f "$WINEPREFIX/drive_c/Python312/python.exe" ]; then
    mkdir -p "$WINEPREFIX"
    wineboot -i >/dev/null 2>&1
    installer="$HOME/.cache/python-$PY_VERSION-amd64.exe"
    [ -f "$installer" ] || wget -q -O "$installer" \
        "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-amd64.exe"
    wine "$installer" /quiet InstallAllUsers=0 'TargetDir=C:\Python312' Include_test=0 Include_doc=0 \
        Include_tcltk=0 Include_launcher=0 PrependPath=0
fi

# Qt >= 6.10 links the system ICU of Windows 10 1903+, which Wine does not provide; 6.9 bundles what it needs.
wine "$PY" -m pip install -q --disable-pip-version-check --no-warn-script-location \
    "PySide6-Essentials==6.9.3" "shiboken6==6.9.3" pyinstaller pillow hidapi \
    winrt-runtime winrt-Windows.Devices.Bluetooth winrt-Windows.Devices.Bluetooth.GenericAttributeProfile \
    winrt-Windows.Devices.Enumeration winrt-Windows.Devices.Radios winrt-Windows.Foundation \
    winrt-Windows.Foundation.Collections winrt-Windows.Storage.Streams

VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+?)\"', open('betterbluetooth/__init__.py').read())[1])")
NAME="BetterBluetooth-${VERSION}-windows-x64"
mkdir -p release
rm -rf build/windows dist/windows

wine "$PY" build.py
wine dist/windows/BetterBluetooth/BetterBluetooth.exe --self-test
(cd dist/windows && rm -f "../../release/${NAME}-portable.zip" && zip -qr "../../release/${NAME}-portable.zip" BetterBluetooth)

wine "$PY" build.py --onefile
wine dist/windows/BetterBluetooth.exe --self-test
cp dist/windows/BetterBluetooth.exe "release/${NAME}.exe"

ls -lh release/
