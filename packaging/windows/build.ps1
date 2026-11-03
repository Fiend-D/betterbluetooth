# Build the Windows release natively (PowerShell, Python 3.10+ on PATH):
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

python -m venv .venv-win
$py = ".\.venv-win\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install "PySide6-Essentials>=6.9" pyinstaller pillow hidapi `
    winrt-runtime winrt-Windows.Devices.Bluetooth winrt-Windows.Devices.Bluetooth.GenericAttributeProfile `
    winrt-Windows.Devices.Enumeration winrt-Windows.Devices.Radios winrt-Windows.Foundation `
    winrt-Windows.Foundation.Collections winrt-Windows.Storage.Streams

$version = (& $py -c "import betterbluetooth; print(betterbluetooth.__version__)").Trim()
$name = "BetterBluetooth-$version-windows-x64"
New-Item -ItemType Directory -Force release | Out-Null

& $py build.py
Compress-Archive -Force -Path dist\windows\BetterBluetooth -DestinationPath "release\$name-portable.zip"
& $py build.py --onefile
Copy-Item -Force dist\windows\BetterBluetooth.exe "release\$name.exe"
Get-ChildItem release
