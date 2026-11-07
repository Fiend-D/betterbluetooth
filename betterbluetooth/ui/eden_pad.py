"""Eden-style Pro Controller preview (geometry from Eden/yuzu configure_input_player_widget).

Drawing language matches Eden: light primary body, dark button faces, red highlight when
pressed, polygon shell + circular face buttons + arrow d-pad.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from .eden_pro_geom import PRO_BODY, PRO_BODY_TOP, PRO_LEFT_HANDLE, PRO_LEFT_TRIGGER
from .gamepad_styles import GamepadStyle, detect_gamepad_style

# Eden design canvas (approx extents of Pro body + triggers).
_DESIGN_W = 440.0
_DESIGN_H = 320.0


@dataclass
class _Hit:
    code: str
    label: str
    x: float  # Eden coords relative to center
    y: float
    r: float  # hit radius
    kind: str = "circle"  # circle | stick | dpad


_JC_ALIAS = {
    "JC_ZL": "BTN_TL2", "JC_L": "BTN_TL", "JC_ZR": "BTN_TR2", "JC_R": "BTN_TR",
    "JC_MINUS": "BTN_SELECT", "JC_PLUS": "BTN_START", "JC_HOME": "BTN_MODE",
    "JC_UP": "BTN_DPAD_UP", "JC_DOWN": "BTN_DPAD_DOWN",
    "JC_LEFT": "BTN_DPAD_LEFT", "JC_RIGHT": "BTN_DPAD_RIGHT",
    "JC_L_STICK": "BTN_THUMBL", "JC_R_STICK": "BTN_THUMBR",
    "JC_X": "BTN_NORTH", "JC_Y": "BTN_WEST", "JC_A": "BTN_EAST", "JC_B": "BTN_SOUTH",
}


def _poly(center: QPointF, coords: list[float], *, mirror_x: bool = False,
          y_shift: float = 0.0) -> QPolygonF:
    pts = []
    for i in range(0, len(coords), 2):
        x, y = coords[i], coords[i + 1] + y_shift
        if mirror_x:
            x = -x
        pts.append(center + QPointF(x, y))
    return QPolygonF(pts)


def _mirror_body(center: QPointF, coords: list[float]) -> QPolygonF:
    """Eden builds body as left half then mirrored right half (reversed)."""
    left = []
    for i in range(0, len(coords), 2):
        left.append(center + QPointF(coords[i], coords[i + 1]))
    right = []
    for i in range(0, len(coords), 2):
        right.append(center + QPointF(-coords[i], coords[i + 1]))
    return QPolygonF(left + list(reversed(right)))


class EdenGamepad(QWidget):
    """Live Pro-controller preview with Eden painting + brand face labels."""

    keyPicked = Signal(str)
    bindRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(320)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._style: GamepadStyle = detect_gamepad_style(None)
        self._pressed: set[str] = set()
        self._armed: str | None = None
        self._maps: dict[str, str] = {}
        self._hover: str | None = None
        self._lx = self._ly = self._rx = self._ry = 0.0
        self._hits = self._build_hits()
        self._tip = QLabel("Eden 风格示意图 · 点按键改键，按实体键会高亮", self)
        self._tip.setWordWrap(True)
        self._tip.setProperty("role", "secondary")
        self._banner = QLabel(self)
        self._banner.setAlignment(Qt.AlignCenter)
        self._banner.hide()
        # Eden palette (dark theme variant)
        self._c_primary = QColor(204, 204, 204)
        self._c_button = QColor(35, 38, 41)
        self._c_button2 = QColor(26, 27, 30)
        self._c_outline = QColor(160, 160, 160)
        self._c_font = QColor(255, 255, 255)
        self._c_font2 = QColor(200, 200, 200)
        self._c_highlight = QColor(170, 0, 0)
        self._c_highlight2 = QColor(119, 0, 0)
        self._c_indicator = QColor(100, 255, 100)

    def _build_hits(self) -> list[_Hit]:
        st = self._style
        n, w, e, s = st.face_labels
        nc, wc, ec, sc = st.face_codes
        face = QPointF(105, -56)
        d = 31.0
        return [
            _Hit("BTN_TL", st.shoulder_l, -90, -134, 22),
            _Hit("BTN_TR", st.shoulder_r, 90, -134, 22),
            _Hit("BTN_TL2", st.shoulder_l2, -210, -120, 22),
            _Hit("BTN_TR2", st.shoulder_r2, 210, -120, 22),
            _Hit("BTN_THUMBL", "L3", -111, -55, 28, "stick"),
            _Hit("BTN_THUMBR", "R3", 51, 0, 28, "stick"),
            _Hit(ec, e, face.x() + d, face.y(), 16),
            _Hit(sc, s, face.x(), face.y() + d, 16),
            _Hit(nc, n, face.x(), face.y() - d, 16),
            _Hit(wc, w, face.x() - d, face.y(), 16),
            _Hit("BTN_DPAD_UP", "↑", -61, -22, 14, "dpad"),
            _Hit("BTN_DPAD_DOWN", "↓", -61, 22, 14, "dpad"),
            _Hit("BTN_DPAD_LEFT", "←", -83, 0, 14, "dpad"),
            _Hit("BTN_DPAD_RIGHT", "→", -39, 0, 14, "dpad"),
            _Hit("BTN_SELECT", st.select_label, -50, -86, 12),
            _Hit("BTN_START", st.start_label, 50, -86, 12),
            _Hit("BTN_MODE", st.guide_label or "●", 29, -56, 12),
        ]

    def set_device_name(self, name: str | None) -> None:
        self._style = detect_gamepad_style(name)
        self._hits = self._build_hits()
        label = self._style.label if self._style.id != "generic" else "通用"
        self._tip.setText(f"样式：{label}（Eden 示意）· 点按键改键，实体键高亮测试")
        # Brand tint for body
        if self._style.id == "xbox":
            self._c_primary = QColor(45, 50, 45)
            self._c_button = QColor(28, 32, 28)
            self._c_highlight = QColor(16, 124, 16)
            self._c_highlight2 = QColor(10, 80, 10)
            self._c_outline = QColor(90, 100, 90)
            self._c_font = QColor(240, 245, 240)
        elif self._style.id == "playstation":
            self._c_primary = QColor(40, 40, 44)
            self._c_button = QColor(28, 28, 32)
            self._c_highlight = QColor(0, 112, 209)
            self._c_highlight2 = QColor(0, 70, 140)
            self._c_outline = QColor(120, 120, 128)
            self._c_font = QColor(245, 245, 247)
        elif self._style.id == "8bitdo":
            self._c_primary = QColor(240, 236, 224)
            self._c_button = QColor(42, 40, 36)
            self._c_highlight = QColor(200, 16, 46)
            self._c_highlight2 = QColor(140, 10, 30)
            self._c_outline = QColor(120, 110, 100)
            self._c_font = QColor(245, 242, 234)
            self._c_font2 = QColor(245, 242, 234)
        else:  # switch / generic — Eden dark
            self._c_primary = QColor(204, 204, 204)
            self._c_button = QColor(35, 38, 41)
            self._c_button2 = QColor(26, 27, 30)
            self._c_highlight = QColor(170, 0, 0)
            self._c_highlight2 = QColor(119, 0, 0)
            self._c_outline = QColor(160, 160, 160)
            self._c_font = QColor(255, 255, 255)
            if self._style.id == "switch":
                self._c_highlight = QColor(230, 0, 18)
                self._c_highlight2 = QColor(160, 0, 12)
        self.update()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._tip.setGeometry(8, self.height() - 22, self.width() - 16, 20)
        self._banner.setGeometry(12, 4, max(40, self.width() - 24), 28)

    def _xform(self) -> tuple[QPointF, float]:
        tip_h = 24
        pad = 8
        avail_w = max(1.0, self.width() - pad * 2)
        avail_h = max(1.0, self.height() - tip_h - pad * 2)
        scale = min(avail_w / _DESIGN_W, avail_h / _DESIGN_H)
        cx = self.width() / 2
        cy = pad + avail_h / 2
        return QPointF(cx, cy), scale

    def _to_widget(self, eden: QPointF, center: QPointF, scale: float) -> QPointF:
        return QPointF(center.x() + eden.x() * scale, center.y() + eden.y() * scale)

    def _canon(self, code: str) -> str:
        return _JC_ALIAS.get(code, code)

    def _hit(self, pos) -> str | None:
        center, scale = self._xform()
        best = None
        best_d = 1e9
        for h in self._hits:
            p = self._to_widget(QPointF(h.x, h.y), center, scale)
            dx, dy = pos.x() - p.x(), pos.y() - p.y()
            d2 = dx * dx + dy * dy
            r = h.r * scale
            if d2 <= r * r and d2 < best_d:
                best_d = d2
                best = h.code
        return best

    def mouseMoveEvent(self, e):  # noqa: N802
        code = self._hit(e.position() if hasattr(e, "position") else e.pos())
        if code != self._hover:
            self._hover = code
            self.update()

    def leaveEvent(self, e):  # noqa: N802
        self._hover = None
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            code = self._hit(e.position() if hasattr(e, "position") else e.pos())
            if code:
                self.bindRequested.emit(code)
                self.keyPicked.emit(code)
        super().mousePressEvent(e)

    def set_button(self, code: str, pressed: bool) -> None:
        code = self._canon(code)
        if pressed:
            self._pressed.add(code)
        else:
            self._pressed.discard(code)
        self.update()

    def set_stick(self, left: bool, x: float, y: float) -> None:
        if left:
            self._lx, self._ly = x, y
        else:
            self._rx, self._ry = x, y
        self.update()

    def set_stick_axis(self, axis: str, value: float) -> None:
        """axis: ABS_X / ABS_Y / ABS_RX / ABS_RY"""
        if axis == "ABS_X":
            self._lx = value
        elif axis == "ABS_Y":
            self._ly = value
        elif axis == "ABS_RX":
            self._rx = value
        elif axis == "ABS_RY":
            self._ry = value
        else:
            return
        self.update()

    def set_mappings(self, maps: dict[str, str]) -> None:
        self._maps = {self._canon(k): v for k, v in maps.items()}
        self.update()

    def set_armed(self, code: str | None) -> None:
        self._armed = self._canon(code) if code else None
        if self._armed:
            label = next((h.label for h in self._hits if h.code == self._armed), self._armed)
            self._banner.setText(f"改建中 · 源键 {label} — 请按下目标键")
            self._banner.setStyleSheet(
                f"background:{self._style.armed}; color:#111; border-radius:6px; "
                "font-weight:700; padding:4px 10px;"
            )
            self._banner.show()
            self._banner.raise_()
        else:
            self._banner.hide()
        self.update()

    def clear_pressed(self) -> None:
        self._pressed.clear()
        self._lx = self._ly = self._rx = self._ry = 0.0
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        center, scale = self._xform()
        p.translate(center)
        p.scale(scale, scale)
        # Draw in Eden coordinate space (origin = center).
        origin = QPointF(0, 0)
        self._draw_triggers(p, origin)
        self._draw_body(p, origin)
        self._draw_sticks(p, origin)
        self._draw_face(p, origin)
        self._draw_dpad(p, origin)
        self._draw_system(p, origin)
        # Brand
        if self._style.brand_mark:
            p.setPen(QColor(self._style.accent))
            font = QFont(p.font())
            font.setPixelSize(11)
            font.setBold(True)
            p.setFont(font)
            p.drawText(QRectF(-40, 70, 80, 16), Qt.AlignCenter, self._style.brand_mark)

    def _btn_color(self, code: str) -> QColor:
        if code == self._armed or code in self._pressed:
            return self._c_highlight
        if code == self._hover:
            return QColor(self._c_button).lighter(130)
        return self._c_button

    def _shown(self, code: str, default: str) -> str:
        """Remapped keys replace the original legend entirely (large, readable)."""
        if code == self._armed:
            return default
        return self._maps.get(code) or default

    def _draw_legend(self, p: QPainter, rect: QRectF, code: str, default: str,
                     *, accent: str = "", base_px: int = 12) -> None:
        shown = self._shown(code, default)
        remapped = bool(self._maps.get(code)) and code != self._armed
        font = QFont(p.font())
        font.setBold(True)
        # Fit longer key names like "Space" / "Enter" without going unreadably small.
        if len(shown) <= 2:
            font.setPixelSize(base_px + 2)
        elif len(shown) <= 4:
            font.setPixelSize(base_px)
        elif len(shown) <= 6:
            font.setPixelSize(max(9, base_px - 2))
        else:
            font.setPixelSize(max(8, base_px - 3))
            shown = shown[:8]
        p.setFont(font)
        if remapped:
            p.setPen(QColor(self._style.accent))
        elif accent and code not in self._pressed and code != self._armed:
            p.setPen(QColor(accent))
        else:
            p.setPen(self._c_font)
        p.drawText(rect, Qt.AlignCenter, shown)

    def _draw_triggers(self, p: QPainter, c: QPointF) -> None:
        p.setPen(QPen(self._c_outline, 1.2))
        # Body top ledge
        p.setBrush(self._c_primary)
        top = []
        for i in range(0, len(PRO_BODY_TOP), 2):
            top.append(c + QPointF(PRO_BODY_TOP[i], PRO_BODY_TOP[i + 1]))
        for i in range(len(PRO_BODY_TOP) - 2, -1, -2):
            top.append(c + QPointF(-PRO_BODY_TOP[i], PRO_BODY_TOP[i + 1]))
        p.drawPolygon(QPolygonF(top))
        # L / R shoulder polygons
        for code, mirror, tx in (("BTN_TL", False, -90), ("BTN_TR", True, 90)):
            shift = 2.0 if code in self._pressed or code == self._armed else 0.0
            poly = _poly(c, PRO_LEFT_TRIGGER, mirror_x=mirror, y_shift=shift)
            p.setBrush(self._btn_color(code))
            p.drawPolygon(poly)
            label = next(h.label for h in self._hits if h.code == code)
            self._draw_legend(p, QRectF(tx - 22, -138 + shift, 44, 18), code, label, base_px=12)
        # ZL / ZR — Eden side trigger rectangles approximated as rounded pills
        for code, x in (("BTN_TL2", -210), ("BTN_TR2", 210)):
            p.setBrush(self._btn_color(code))
            p.setPen(QPen(self._c_outline, 1.2))
            rect = QRectF(x - 28, -135, 56, 28)
            p.drawRoundedRect(rect, 8, 8)
            label = next(h.label for h in self._hits if h.code == code)
            self._draw_legend(p, rect, code, label, base_px=12)

    def _draw_body(self, p: QPainter, c: QPointF) -> None:
        p.setPen(QPen(self._c_outline, 1.4))
        p.setBrush(self._c_primary)
        p.drawPolygon(_poly(c, PRO_LEFT_HANDLE))
        p.drawPolygon(_poly(c, PRO_LEFT_HANDLE, mirror_x=True))
        p.drawPolygon(_mirror_body(c, PRO_BODY))
        # Stick wells (Eden transparent rings)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._c_outline, 1.5))
        p.drawEllipse(c + QPointF(-111, -55), 32, 32)
        p.drawEllipse(c + QPointF(51, 0), 32, 32)

    def _draw_sticks(self, p: QPainter, c: QPointF) -> None:
        for code, base, sx, sy in (
            ("BTN_THUMBL", QPointF(-111, -55), self._lx, self._ly),
            ("BTN_THUMBR", QPointF(51, 0), self._rx, self._ry),
        ):
            offset = QPointF(sx * 11, sy * 11)
            center = c + base + offset
            pressed = code in self._pressed or code == self._armed
            p.setPen(QPen(self._c_outline, 1.2))
            p.setBrush(self._c_highlight if pressed else self._c_button)
            p.drawEllipse(center, 24, 24)
            p.setBrush(self._c_highlight2 if pressed else self._c_button2)
            p.drawEllipse(center, 17, 17)
            # Live indicator / remapped legend
            remapped = self._shown(code, "")
            if remapped and code in self._maps and code != self._armed:
                self._draw_legend(
                    p, QRectF(center.x() - 22, center.y() - 10, 44, 20), code, "L3", base_px=11)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(self._c_indicator)
                p.drawEllipse(center, 3.5, 3.5)

    def _draw_face(self, p: QPainter, c: QPointF) -> None:
        face = c + QPointF(105, -56)
        d = 31.0
        st = self._style
        positions = [
            (st.face_codes[2], st.face_labels[2], face + QPointF(d, 0), st.face_colors[2]),   # east
            (st.face_codes[3], st.face_labels[3], face + QPointF(0, d), st.face_colors[3]),   # south
            (st.face_codes[0], st.face_labels[0], face + QPointF(0, -d), st.face_colors[0]),  # north
            (st.face_codes[1], st.face_labels[1], face + QPointF(-d, 0), st.face_colors[1]),  # west
        ]
        for code, label, pos, accent in positions:
            p.setPen(QPen(self._c_outline, 1.2))
            p.setBrush(self._btn_color(code))
            p.drawEllipse(pos, 15, 15)
            remapped = bool(self._maps.get(code)) and code != self._armed
            if accent and not remapped and code not in self._pressed and code != self._armed:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(accent), 2.0))
                p.drawEllipse(pos, 11, 11)
            self._draw_legend(
                p, QRectF(pos.x() - 16, pos.y() - 11, 32, 22), code, label,
                accent=accent, base_px=13,
            )

    def _draw_dpad(self, p: QPainter, c: QPointF) -> None:
        origin = c + QPointF(-61, 0)
        arms = [
            ("BTN_DPAD_UP", "↑", QPointF(0, -20), [(-10, -6), (-10, -22), (0, -34), (10, -22), (10, -6)]),
            ("BTN_DPAD_DOWN", "↓", QPointF(0, 20), [(-10, 6), (-10, 22), (0, 34), (10, 22), (10, 6)]),
            ("BTN_DPAD_LEFT", "←", QPointF(-20, 0), [(-6, -10), (-22, -10), (-34, 0), (-22, 10), (-6, 10)]),
            ("BTN_DPAD_RIGHT", "→", QPointF(20, 0), [(6, -10), (22, -10), (34, 0), (22, 10), (6, 10)]),
        ]
        for code, arrow, mid, shape in arms:
            poly = QPolygonF([origin + QPointF(x, y) for x, y in shape])
            p.setPen(QPen(self._c_highlight if code in self._pressed else self._c_button, 1.0))
            p.setBrush(self._btn_color(code))
            p.drawPolygon(poly)
            self._draw_legend(
                p, QRectF(origin.x() + mid.x() - 14, origin.y() + mid.y() - 9, 28, 18),
                code, arrow, base_px=11,
            )
        # Outline diamond
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._c_outline, 1.4))
        outline = QPolygonF([
            origin + QPointF(0, -36), origin + QPointF(36, 0),
            origin + QPointF(0, 36), origin + QPointF(-36, 0),
        ])
        p.drawPolygon(outline)

    def _draw_system(self, p: QPainter, c: QPointF) -> None:
        # Minus / Plus — remapped keys replace the glyph
        for code, pos, plus in (("BTN_SELECT", QPointF(-50, -86), False),
                                ("BTN_START", QPointF(50, -86), True)):
            p.setPen(QPen(self._c_outline, 1.2))
            p.setBrush(self._btn_color(code))
            p.drawEllipse(c + pos, 11, 11)
            remapped = bool(self._maps.get(code)) and code != self._armed
            if remapped:
                self._draw_legend(
                    p, QRectF(c.x() + pos.x() - 14, c.y() + pos.y() - 8, 28, 16),
                    code, "+" if plus else "−", base_px=10,
                )
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(self._c_font2)
                p.drawRect(QRectF(c.x() + pos.x() - 4.5, c.y() + pos.y() - 1.2, 9, 2.4))
                if plus:
                    p.drawRect(QRectF(c.x() + pos.x() - 1.2, c.y() + pos.y() - 4.5, 2.4, 9))
        # Home / guide
        p.setPen(QPen(self._c_outline, 1.2))
        p.setBrush(self._btn_color("BTN_MODE"))
        p.drawEllipse(c + QPointF(29, -56), 11, 11)
        label = self._style.guide_label or "●"
        remapped = bool(self._maps.get("BTN_MODE")) and self._armed != "BTN_MODE"
        if not remapped:
            p.setBrush(self._c_button2)
            p.drawEllipse(c + QPointF(29, -56), 7, 7)
        self._draw_legend(
            p, QRectF(c.x() + 13, c.y() - 66, 32, 20), "BTN_MODE", label, base_px=10,
        )
