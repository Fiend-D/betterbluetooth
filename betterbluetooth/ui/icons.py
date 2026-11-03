from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..models import DeviceKind

# Line icons on a 24x24 grid (Lucide-style geometry).
_PATHS: dict[str, str] = {
    "bluetooth": '<path d="M7 7l10 10-5 5V2l5 5L7 17"/>',
    "headphones": '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7'
                  'a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
    "headset": '<path d="M3 11h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Zm0 0a9 9 0 1 1 18 0m0 0'
               'v5a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3Z"/><path d="M21 16v2a4 4 0 0 1-4 4h-5"/>',
    "speaker": '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M12 6h.01"/>'
               '<circle cx="12" cy="14" r="4"/><path d="M12 14h.01"/>',
    "mouse": '<rect x="5" y="2" width="14" height="20" rx="7"/><path d="M12 6v4"/>',
    "keyboard": '<rect x="2" y="4" width="20" height="16" rx="2"/>'
                '<path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10"/>',
    "gamepad": '<path d="M6 11h4M8 9v4M15 12h.01M18 10h.01"/><path d="M17.32 5H6.68a4 4 0 0 0-3.98 3.59'
               'C2.6 9.42 2 14.46 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.41-1.41A2 2 0 0 1 9.83 16h4.34'
               'a2 2 0 0 1 1.41.59L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.55-.6-6.58-.69-7.26'
               'A4 4 0 0 0 17.32 5z"/>',
    "phone": '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/>',
    "computer": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M2 20h20"/>',
    "watch": '<circle cx="12" cy="12" r="6"/><path d="M12 10v2l1 1"/>'
             '<path d="m16.13 7.66-.81-4.05a2 2 0 0 0-2-1.61h-2.68a2 2 0 0 0-2 1.61l-.78 4.05"/>'
             '<path d="m7.88 16.36.8 4a2 2 0 0 0 2 1.61h2.72a2 2 0 0 0 2-1.61l.81-4.05"/>',
    "pen": '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 '
                '2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 '
                '1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 '
                '.33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0'
                '-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 '
                '1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 '
                '2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09'
                'a1.65 1.65 0 0 0-1.51 1z"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-2.64-6.36L21 8"/><path d="M21 3v5h-5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "back": '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    "more": '<circle cx="5" cy="12" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" '
            'fill="currentColor"/><circle cx="19" cy="12" r="1.2" fill="currentColor"/>',
    "pin": '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12'
           'a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8'
           'a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
    "pin-on": '<path d="M12 17v5"/><path fill="currentColor" d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 '
              '15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 '
              '0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
    "tray": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 15h20"/><path d="M15 18h3"/>',
    "tray-off": '<rect x="2" y="4" width="20" height="16" rx="2" opacity=".45"/><path d="M2 15h20" opacity=".45"/>'
                '<path d="M3 3l18 18"/>',
    "history": '<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "warning": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
               '<path d="M12 9v4M12 17h.01"/>',
    "error": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "success": '<circle cx="12" cy="12" r="10"/><path d="m8 12 3 3 5-6"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
}

KIND_ICON = {
    DeviceKind.HEADSET: "headset",
    DeviceKind.HEADPHONES: "headphones",
    DeviceKind.SPEAKER: "speaker",
    DeviceKind.MOUSE: "mouse",
    DeviceKind.KEYBOARD: "keyboard",
    DeviceKind.GAMEPAD: "gamepad",
    DeviceKind.PHONE: "phone",
    DeviceKind.COMPUTER: "computer",
    DeviceKind.WATCH: "watch",
    DeviceKind.PEN: "pen",
    DeviceKind.OTHER: "bluetooth",
}


def svg(name: str, color: str, stroke: float = 1.7) -> bytes:
    body = _PATHS[name].replace("currentColor", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode()


def render(painter: QPainter, name: str, rect: QRectF, color: QColor | str, stroke: float = 1.7) -> None:
    c = color.name() if isinstance(color, QColor) else color
    QSvgRenderer(QByteArray(svg(name, c, stroke))).render(painter, rect)


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, dpr: float, stroke: float) -> QPixmap:
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.transparent)
    px.setDevicePixelRatio(dpr)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, color, stroke))).render(p, QRectF(0, 0, size, size))
    p.end()
    return px


def pixmap(name: str, color: QColor | str, size: int = 16, dpr: float = 2.0, stroke: float = 1.7) -> QPixmap:
    c = color.name() if isinstance(color, QColor) else color
    return _pixmap(name, c, size, dpr, stroke)


def icon(name: str, color: QColor | str, size: int = 16, stroke: float = 1.7) -> QIcon:
    return QIcon(pixmap(name, color, size, 2.0, stroke))


APP_ICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#3DA5FF"/><stop offset="1" stop-color="#0056C6"/></linearGradient></defs>
<rect x="16" y="16" width="224" height="224" rx="56" fill="url(#g)"/>
<path d="M88 88L168 168L128 208V48L168 88L88 168" fill="none" stroke="#fff" stroke-width="18"
 stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def app_icon() -> QIcon:
    ic = QIcon()
    renderer = QSvgRenderer(QByteArray(APP_ICON_SVG))
    for size in (16, 24, 32, 48, 64, 128, 256):
        px = QPixmap(size, size)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        ic.addPixmap(px)
    return ic
