from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import icons

TRAY_STYLES: list[tuple[str, str]] = [
    ("number", "数字"),
    ("badge", "徽章"),
    ("battery", "横向电池"),
    ("vbattery", "竖向电池"),
    ("segments", "分段"),
    ("ring", "圆环图标"),
    ("pie", "饼图"),
    ("glyph_bar", "图标电量条"),
]

_SIZES = (16, 20, 22, 24, 32, 48, 64)


@dataclass(frozen=True)
class TrayColors:
    fg: QColor
    main: QColor
    track: QColor


def level_color(level: int, threshold: int, dark_bar: bool) -> QColor:
    if level <= threshold:
        return QColor("#FF6B6B" if dark_bar else "#C42B1C")
    if level <= 50:
        return QColor("#FFC83D" if dark_bar else "#B86E00")
    return QColor("#6CCB5F" if dark_bar else "#0F7B0F")


def colors_for(level: int, threshold: int, dark_bar: bool, colored: bool, charging: bool) -> TrayColors:
    fg = QColor("#FFFFFF") if dark_bar else QColor("#1B1B1B")
    if charging:
        main = QColor("#6CCB5F" if dark_bar else "#0F7B0F")
    elif colored or level <= threshold:
        main = level_color(level, threshold, dark_bar)
    else:
        main = QColor(fg)
    track = QColor(fg)
    track.setAlpha(80)
    return TrayColors(fg, main, track)


def _font(px: float) -> QFont:
    f = QFont()
    f.setFamilies(["Segoe UI Variable Display", "Segoe UI", "Ubuntu", "Cantarell", "DejaVu Sans", "sans-serif"])
    f.setPixelSize(max(1, int(px)))
    f.setWeight(QFont.Bold)
    return f


def _fit_text(p: QPainter, text: str, rect: QRectF, max_px: float) -> None:
    px = max_px
    while px > 5:
        p.setFont(_font(px))
        fm = p.fontMetrics()
        if fm.horizontalAdvance(text) <= rect.width() and fm.capHeight() <= rect.height():
            break
        px -= 0.5
    p.drawText(rect, Qt.AlignCenter, text)


def _contrast(c: QColor) -> QColor:
    lum = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
    return QColor("#111111") if lum > 0.6 else QColor("#FFFFFF")


def _paint_number(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    text = str(level)
    p.setPen(c.main)
    _fit_text(p, text, QRectF(0, -s * 0.06, s, s * 0.84), s * (0.78 if len(text) < 3 else 0.6))
    bar_h = max(1.5, s * 0.1)
    y = s - bar_h - s * 0.02
    p.setPen(Qt.NoPen)
    p.setBrush(c.track)
    p.drawRoundedRect(QRectF(s * 0.08, y, s * 0.84, bar_h), bar_h / 2, bar_h / 2)
    p.setBrush(c.main)
    p.drawRoundedRect(QRectF(s * 0.08, y, max(bar_h, s * 0.84 * level / 100), bar_h), bar_h / 2, bar_h / 2)


def _paint_badge(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c.main)
    p.drawEllipse(QRectF(0.5, 0.5, s - 1, s - 1))
    p.setPen(_contrast(c.main))
    text = str(level)
    _fit_text(p, text, QRectF(s * 0.1, s * 0.12, s * 0.8, s * 0.76), s * (0.62 if len(text) < 3 else 0.46))


def _paint_battery(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    stroke = max(1.0, s / 16)
    body = QRectF(s * 0.04 + stroke / 2, s * 0.22, s * 0.84, s * 0.56)
    p.setPen(QPen(c.fg, stroke))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, s * 0.1, s * 0.1)
    p.setPen(Qt.NoPen)
    p.setBrush(c.fg)
    p.drawRoundedRect(QRectF(body.right() + stroke, s * 0.38, s * 0.07, s * 0.24), s * 0.03, s * 0.03)
    inner = body.adjusted(stroke * 1.6, stroke * 1.6, -stroke * 1.6, -stroke * 1.6)
    fill = QColor(c.main)
    fill.setAlpha(120)
    p.setBrush(fill)
    p.drawRoundedRect(QRectF(inner.x(), inner.y(), inner.width() * level / 100, inner.height()),
                      s * 0.05, s * 0.05)
    p.setPen(c.fg)
    _fit_text(p, str(level), inner.adjusted(-stroke, -stroke * 2, stroke, stroke * 2), s * 0.5)


def _paint_vbattery(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    stroke = max(1.0, s / 14)
    body = QRectF(s * 0.26, s * 0.14, s * 0.48, s * 0.82)
    p.setPen(QPen(c.fg, stroke))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, s * 0.08, s * 0.08)
    p.setPen(Qt.NoPen)
    p.setBrush(c.fg)
    p.drawRoundedRect(QRectF(s * 0.38, s * 0.03, s * 0.24, s * 0.08), s * 0.02, s * 0.02)
    inner = body.adjusted(stroke * 1.7, stroke * 1.7, -stroke * 1.7, -stroke * 1.7)
    h = inner.height() * level / 100
    p.setBrush(c.main)
    p.drawRoundedRect(QRectF(inner.x(), inner.bottom() - h, inner.width(), h), s * 0.04, s * 0.04)


def _paint_segments(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    count = 5
    filled = 0 if level <= 0 else min(count, (level + 19) // 20)
    gap = max(1.0, s * 0.06)
    w = (s * 0.92 - gap * (count - 1)) / count
    for i in range(count):
        h = s * (0.3 + 0.6 * (i + 1) / count)
        rect = QRectF(s * 0.04 + i * (w + gap), s * 0.95 - h, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(c.main if i < filled else c.track)
        p.drawRoundedRect(rect, w * 0.25, w * 0.25)


def _paint_ring(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    width = max(1.6, s * 0.11)
    r = QRectF(width / 2 + 0.5, width / 2 + 0.5, s - width - 1, s - width - 1)
    pen = QPen(c.track, width)
    p.setPen(pen)
    p.drawEllipse(r)
    pen = QPen(c.main, width)
    pen.setCapStyle(Qt.RoundCap if level < 100 else Qt.FlatCap)
    p.setPen(pen)
    p.drawArc(r, 90 * 16, int(-360 * 16 * level / 100))
    g = s * 0.5
    icons.render(p, kind, QRectF((s - g) / 2, (s - g) / 2, g, g), c.fg, stroke=2.2)


def _paint_pie(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    stroke = max(1.0, s / 16)
    r = QRectF(stroke / 2 + 0.5, stroke / 2 + 0.5, s - stroke - 1, s - stroke - 1)
    p.setPen(QPen(c.fg, stroke))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(r)
    inner = r.adjusted(stroke * 1.5, stroke * 1.5, -stroke * 1.5, -stroke * 1.5)
    p.setPen(Qt.NoPen)
    p.setBrush(c.main)
    if level >= 100:
        p.drawEllipse(inner)
    else:
        p.drawPie(inner, 90 * 16, int(-360 * 16 * level / 100))


def _paint_glyph_bar(p: QPainter, s: float, level: int, kind: str, c: TrayColors) -> None:
    g = s * 0.7
    icons.render(p, kind, QRectF((s - g) / 2, 0, g, g), c.fg, stroke=2.2)
    bar_h = max(2.0, s * 0.14)
    y = s - bar_h - s * 0.02
    p.setPen(Qt.NoPen)
    p.setBrush(c.track)
    p.drawRoundedRect(QRectF(s * 0.06, y, s * 0.88, bar_h), bar_h / 2, bar_h / 2)
    p.setBrush(c.main)
    p.drawRoundedRect(QRectF(s * 0.06, y, max(bar_h, s * 0.88 * level / 100), bar_h), bar_h / 2, bar_h / 2)


def _paint_bolt(p: QPainter, s: float, c: TrayColors) -> None:
    """Small charging badge in the top-right corner."""
    r = s * 0.2
    center = QPointF(s - r - 0.5, r + 0.5)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#6CCB5F"))
    p.drawEllipse(center, r, r)
    bolt = QPainterPath()
    k = r / 10
    pts = [(1, -7), (-4, 1), (0, 1), (-1, 7), (4, -1), (0, -1)]
    bolt.moveTo(center + QPointF(pts[0][0] * k, pts[0][1] * k))
    for x, y in pts[1:]:
        bolt.lineTo(center + QPointF(x * k, y * k))
    bolt.closeSubpath()
    p.setBrush(QColor("#0B3D0B"))
    p.drawPath(bolt)


_PAINTERS = {
    "number": _paint_number,
    "badge": _paint_badge,
    "battery": _paint_battery,
    "vbattery": _paint_vbattery,
    "segments": _paint_segments,
    "ring": _paint_ring,
    "pie": _paint_pie,
    "glyph_bar": _paint_glyph_bar,
}


def render_pixmap(style: str, level: int, kind_icon: str, dark_bar: bool, threshold: int,
                  colored: bool, charging: bool, size: int) -> QPixmap:
    painter_fn = _PAINTERS.get(style, _paint_number)
    c = colors_for(level, threshold, dark_bar, colored, charging)
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    painter_fn(p, float(size), level, kind_icon, c)
    if charging and size >= 20 and style not in ("number", "badge", "battery"):
        _paint_bolt(p, float(size), c)
    p.end()
    return px


def render_tray_icon(style: str, level: int, kind_icon: str, dark_bar: bool, threshold: int,
                     colored: bool = False, charging: bool = False) -> QIcon:
    ic = QIcon()
    for size in _SIZES:
        ic.addPixmap(render_pixmap(style, level, kind_icon, dark_bar, threshold, colored, charging, size))
    return ic


def render_main_icon(dark_bar: bool) -> QIcon:
    fg = "#FFFFFF" if dark_bar else "#1B1B1B"
    ic = QIcon()
    for size in _SIZES:
        ic.addPixmap(icons.pixmap("bluetooth", fg, size, 1.0, stroke=2.2))
    return ic
