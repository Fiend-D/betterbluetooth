"""Build a standalone executable with PyInstaller.

    python build.py            # one-folder build -> dist/<platform>/BetterBluetooth/
    python build.py --onefile  # single executable -> dist/<platform>/BetterBluetooth[.exe]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLATFORM = "windows" if sys.platform == "win32" else "linux"
BUILD = ROOT / "build" / PLATFORM
DIST = ROOT / "dist" / PLATFORM

UNUSED_QT = [
    "QtQml", "QtQuick", "QtQuickWidgets", "QtQuick3D", "QtQuickControls2", "QtWebEngineCore",
    "QtWebEngineWidgets", "QtWebChannel", "QtWebSockets", "QtMultimedia", "QtMultimediaWidgets",
    "Qt3DCore", "Qt3DRender", "QtCharts", "QtDataVisualization", "QtGraphs", "QtPdf", "QtPdfWidgets",
    "QtSql", "QtTest", "QtDesigner", "QtUiTools", "QtHelp", "QtOpenGL", "QtOpenGLWidgets",
    "QtPrintSupport", "QtXml", "QtConcurrent", "QtPositioning", "QtLocation", "QtSerialPort",
    "QtBluetooth", "QtNfc", "QtSensors", "QtSpatialAudio", "QtTextToSpeech", "QtRemoteObjects",
    "QtScxml", "QtStateMachine", "QtHttpServer",
]


def render_icon() -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    png = BUILD / "icon.png"
    try:
        from PySide6.QtCore import QByteArray, QRectF, Qt
        from PySide6.QtGui import QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        sys.path.insert(0, str(ROOT))
        from betterbluetooth.ui.icons import APP_ICON_SVG

        _app = QGuiApplication.instance() or QGuiApplication(["build", "-platform", "offscreen"])
        img = QImage(256, 256, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        QSvgRenderer(QByteArray(APP_ICON_SVG)).render(painter, QRectF(0, 0, 256, 256))
        painter.end()
        img.save(str(png))
    except Exception:
        # CI / headless hosts may lack libEGL; fall back to a solid PNG via Pillow.
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (256, 256), (0, 120, 212, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((48, 48, 208, 208), fill=(255, 255, 255, 230))
        draw.ellipse((88, 88, 168, 168), fill=(0, 120, 212, 255))
        img.save(png)

    if PLATFORM == "windows":
        from PIL import Image
        ico = BUILD / "icon.ico"
        Image.open(png).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return ico
    return png


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true")
    opts = parser.parse_args()

    import PyInstaller.__main__

    icon = render_icon()
    args = [
        str(ROOT / "betterbluetooth" / "__main__.py"),
        "--name", "BetterBluetooth",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(icon),
        "--paths", str(ROOT),
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        "--exclude-module", "tkinter",
        "--onefile" if opts.onefile else "--onedir",
    ]
    for mod in UNUSED_QT:
        args += ["--exclude-module", f"PySide6.{mod}"]
    if PLATFORM == "windows":
        args += ["--collect-all", "winrt", "--hidden-import", "hid",
                 "--hidden-import", "betterbluetooth.backends.windows",
                 "--hidden-import", "betterbluetooth.peripherals.hidpp",
                 "--hidden-import", "betterbluetooth.peripherals.switch",
                 "--hidden-import", "betterbluetooth.inputmap.windows_hook"]
    else:
        args += ["--collect-submodules", "dbus_fast", "--collect-all", "evdev",
                 "--hidden-import", "betterbluetooth.backends.bluez",
                 "--hidden-import", "betterbluetooth.peripherals.upower",
                 "--hidden-import", "betterbluetooth.inputmap.linux_evdev"]
    args += ["--hidden-import", "betterbluetooth.backends.mock",
             "--hidden-import", "betterbluetooth.peripherals.mock",
             "--hidden-import", "betterbluetooth.inputmap"]
    PyInstaller.__main__.run(args)
    # Avoid UnicodeEncodeError on Windows cp1252 consoles / CI logs.
    print(f"\nOutput: {DIST}")


if __name__ == "__main__":
    main()
