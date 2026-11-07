"""Eden-style gamepad preview with brand/model-specific layouts and extra buttons."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from .eden_pro_geom import PRO_BODY, PRO_BODY_TOP, PRO_LEFT_HANDLE, PRO_LEFT_TRIGGER
from .gamepad_styles import GamepadStyle, detect_gamepad_style, shell_positions

_DESIGN_W = 440.0
_DESIGN_H = 320.0


@dataclass
class _Hit:
    code: str
    label: str
    x: float
    y: float
    r: float
    kind: str = "circle"  # circle | stick | dpad | pill | touch


_JC_ALIAS = {
    "JC_ZL": "BTN_TL2", "JC_L": "BTN_TL", "JC_ZR": "BTN_TR2", "JC_R": "BTN_TR",
    "JC_MINUS": "BTN_SELECT", "JC_PLUS": "BTN_START", "JC_HOME": "BTN_MODE",
    "JC_UP": "BTN_DPAD_UP", "JC_DOWN": "BTN_DPAD_DOWN",
    "JC_LEFT": "BTN_DPAD_LEFT", "JC_RIGHT": "BTN_DPAD_RIGHT",
    "JC_L_STICK": "BTN_THUMBL", "JC_R_STICK": "BTN_THUMBR",
    "JC_X": "BTN_NORTH", "JC_Y": "BTN_WEST", "JC_A": "BTN_EAST", "JC_B": "BTN_SOUTH",
    "JC_CAPTURE": "BTN_CAPTURE", "JC_SL": "BTN_EXTRA1", "JC_SR": "BTN_EXTRA2",
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
    left = []
    for i in range(0, len(coords), 2):
        left.append(center + QPointF(coords[i], coords[i + 1]))
    right = []
    for i in range(0, len(coords), 2):
        right.append(center + QPointF(-coords[i], coords[i + 1]))
    return QPolygonF(left + list(reversed(right)))


class EdenGamepad(QWidget):
    """Live pad preview: Eden shell + per-model face labels / extras."""

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
        self._tip = QLabel("按型号显示按键 · 点示意图改建，实体键高亮", self)
        self._tip.setWordWrap(True)
        self._tip.setProperty("role", "secondary")
        self._banner = QLabel(self)
        self._banner.setAlignment(Qt.AlignCenter)
        self._banner.hide()
        self._c_primary = QColor(204, 204, 204)
        self._c_button = QColor(35, 38, 41)
        self._c_button2 = QColor(26, 27, 30)
        self._c_outline = QColor(160, 160, 160)
        self._c_font = QColor(255, 255, 255)
        self._c_font2 = QColor(200, 200, 200)
        self._c_highlight = QColor(170, 0, 0)
        self._c_highlight2 = QColor(119, 0, 0)
        self._c_indicator = QColor(100, 255, 100)

    def _pos(self) -> dict[str, tuple[float, float]]:
        return shell_positions(self._style.shell)

    def _build_hits(self) -> list[_Hit]:
        st = self._style
        p = self._pos()
        hits: list[_Hit] = [
            _Hit("BTN_TL", st.shoulder_l, -90, -134, 22),
            _Hit("BTN_TR", st.shoulder_r, 90, -134, 22),
            _Hit("BTN_TL2", st.shoulder_l2, -210, -120, 22),
            _Hit("BTN_TR2", st.shoulder_r2, 210, -120, 22),
        ]
        if st.shell not in ("joycon_l", "joycon_r"):
            hits += [
                _Hit("BTN_THUMBL", "L3", *p["lstick"], 28, "stick"),
                _Hit("BTN_THUMBR", "R3", *p["rstick"], 28, "stick"),
            ]
        elif st.shell == "joycon_l":
            hits.append(_Hit("BTN_THUMBL", "L3", *p["lstick"], 28, "stick"))
        else:
            hits.append(_Hit("BTN_THUMBR", "R3", *p["lstick"], 28, "stick"))

        n, w, e, s = st.face_labels
        nc, wc, ec, sc = st.face_codes
        fx, fy = p["face"]
        d = 31.0
        if st.shell != "joycon_l" and any(st.face_labels):
            hits += [
                _Hit(ec, e or "A", fx + d, fy, 16),
                _Hit(sc, s or "B", fx, fy + d, 16),
                _Hit(nc, n or "X", fx, fy - d, 16),
                _Hit(wc, w or "Y", fx - d, fy, 16),
            ]
        dx, dy = p["dpad"]
        if st.shell != "joycon_r":
            hits += [
                _Hit("BTN_DPAD_UP", "↑", dx, dy - 22, 14, "dpad"),
                _Hit("BTN_DPAD_DOWN", "↓", dx, dy + 22, 14, "dpad"),
                _Hit("BTN_DPAD_LEFT", "←", dx - 22, dy, 14, "dpad"),
                _Hit("BTN_DPAD_RIGHT", "→", dx + 22, dy, 14, "dpad"),
            ]
        if st.select_label:
            hits.append(_Hit("BTN_SELECT", st.select_label, *p["select"], 12))
        if st.start_label:
            hits.append(_Hit("BTN_START", st.start_label, *p["start"], 12))
        if st.guide_label is not None:
            hits.append(_Hit("BTN_MODE", st.guide_label or "●", *p["guide"], 12))
        if st.has_capture:
            hits.append(_Hit("BTN_CAPTURE", "📷", *p["capture"], 12))
        if st.has_touchpad:
            tx, ty = p["touchpad"]
            hits.append(_Hit("BTN_TOUCHPAD", "触控板", tx, ty, 36, "touch"))
        # Extra paddles / M / C / Z along the bottom edge
        extras = list(st.extras)
        if extras:
            n_ex = len(extras)
            span = min(220.0, 36.0 * n_ex)
            start_x = -span / 2 + 18
            for i, (code, label) in enumerate(extras):
                if code in ("BTN_TOUCHPAD",) or (code in ("BTN_EXTRA1", "BTN_EXTRA2") and st.shell.startswith("joycon")):
                    # Already represented or drawn on rails for Joy-Con.
                    if st.shell.startswith("joycon"):
                        side = -70 if i == 0 else 70
                        hits.append(_Hit(code, label, side, 0, 14, "pill"))
                    continue
                hits.append(_Hit(code, label, start_x + i * (span / max(1, n_ex - 1) if n_ex > 1 else 0), 95, 14, "pill"))
        return hits

    def set_device_name(self, name: str | None) -> None:
        self._style = detect_gamepad_style(name)
        self._hits = self._build_hits()
        hint = self._style.model_hint or self._style.label
        extras = "、".join(lbl for _, lbl in self._style.extras[:4])
        extra_txt = f" · 扩展键 {extras}" if extras else ""
        self._tip.setText(f"型号：{hint}{extra_txt} · 点按键改键，实体键高亮")
        st = self._style
        self._c_primary = QColor(st.case)
        self._c_button = QColor(st.button)
        self._c_button2 = QColor(st.button_side)
        self._c_outline = QColor(st.case_edge).lighter(180)
        self._c_font = QColor(st.legend)
        self._c_font2 = QColor(st.legend_dim)
        self._c_highlight = QColor(st.pressed)
        self._c_highlight2 = QColor(st.accent)
        if st.id in ("switch", "gulikit", "iine"):
            self._c_primary = QColor(204, 204, 204)
            self._c_button = QColor(35, 38, 41)
            self._c_button2 = QColor(26, 27, 30)
            self._c_outline = QColor(160, 160, 160)
            self._c_font = QColor(255, 255, 255)
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
        return QPointF(self.width() / 2, pad + avail_h / 2), scale

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
            r = h.r * scale * (1.6 if h.kind == "touch" else 1.0)
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
        origin = QPointF(0, 0)
        self._draw_triggers(p, origin)
        self._draw_body(p, origin)
        self._draw_sticks(p, origin)
        self._draw_face(p, origin)
        self._draw_dpad(p, origin)
        self._draw_system(p, origin)
        self._draw_extras(p, origin)
        if self._style.brand_mark:
            p.setPen(QColor(self._style.accent))
            font = QFont(p.font())
            font.setPixelSize(11)
            font.setBold(True)
            p.setFont(font)
            p.drawText(QRectF(-50, 68, 100, 16), Qt.AlignCenter, self._style.brand_mark)

    def _btn_color(self, code: str) -> QColor:
        if code == self._armed or code in self._pressed:
            return self._c_highlight
        if code == self._hover:
            return QColor(self._c_button).lighter(130)
        return self._c_button

    def _shown(self, code: str, default: str) -> str:
        if code == self._armed:
            return default
        return self._maps.get(code) or default

    def _draw_legend(self, p: QPainter, rect: QRectF, code: str, default: str,
                     *, accent: str = "", base_px: int = 12) -> None:
        shown = self._shown(code, default)
        remapped = bool(self._maps.get(code)) and code != self._armed
        font = QFont(p.font())
        font.setBold(True)
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
        if self._style.shell.startswith("joycon"):
            return
        p.setPen(QPen(self._c_outline, 1.2))
        p.setBrush(self._c_primary)
        top = []
        for i in range(0, len(PRO_BODY_TOP), 2):
            top.append(c + QPointF(PRO_BODY_TOP[i], PRO_BODY_TOP[i + 1]))
        for i in range(len(PRO_BODY_TOP) - 2, -1, -2):
            top.append(c + QPointF(-PRO_BODY_TOP[i], PRO_BODY_TOP[i + 1]))
        p.drawPolygon(QPolygonF(top))
        for code, mirror, tx in (("BTN_TL", False, -90), ("BTN_TR", True, 90)):
            shift = 2.0 if code in self._pressed or code == self._armed else 0.0
            poly = _poly(c, PRO_LEFT_TRIGGER, mirror_x=mirror, y_shift=shift)
            p.setBrush(self._btn_color(code))
            p.drawPolygon(poly)
            label = next(h.label for h in self._hits if h.code == code)
            self._draw_legend(p, QRectF(tx - 22, -138 + shift, 44, 18), code, label, base_px=12)
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
        shell = self._style.shell
        if shell.startswith("joycon"):
            # Tall rounded rail
            path = QPainterPath()
            path.addRoundedRect(QRectF(-48, -130, 96, 260), 28, 28)
            p.drawPath(path)
            return
        p.drawPolygon(_poly(c, PRO_LEFT_HANDLE))
        p.drawPolygon(_poly(c, PRO_LEFT_HANDLE, mirror_x=True))
        p.drawPolygon(_mirror_body(c, PRO_BODY))
        pos = self._pos()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._c_outline, 1.5))
        lx, ly = pos["lstick"]
        rx, ry = pos["rstick"]
        p.drawEllipse(c + QPointF(lx, ly), 32, 32)
        p.drawEllipse(c + QPointF(rx, ry), 32, 32)
        if self._style.has_touchpad:
            tx, ty = pos["touchpad"]
            p.setBrush(QColor(self._style.plate))
            p.setPen(QPen(self._c_outline, 1.2))
            p.drawRoundedRect(QRectF(tx - 55, ty - 18, 110, 36), 10, 10)

    def _draw_sticks(self, p: QPainter, c: QPointF) -> None:
        pos = self._pos()
        sticks = []
        if self._style.shell == "joycon_l":
            sticks = [("BTN_THUMBL", QPointF(*pos["lstick"]), self._lx, self._ly)]
        elif self._style.shell == "joycon_r":
            sticks = [("BTN_THUMBR", QPointF(*pos["lstick"]), self._rx, self._ry)]
        else:
            sticks = [
                ("BTN_THUMBL", QPointF(*pos["lstick"]), self._lx, self._ly),
                ("BTN_THUMBR", QPointF(*pos["rstick"]), self._rx, self._ry),
            ]
        for code, base, sx, sy in sticks:
            offset = QPointF(sx * 11, sy * 11)
            center = c + base + offset
            pressed = code in self._pressed or code == self._armed
            p.setPen(QPen(self._c_outline, 1.2))
            p.setBrush(self._c_highlight if pressed else self._c_button)
            p.drawEllipse(center, 24, 24)
            p.setBrush(self._c_highlight2 if pressed else self._c_button2)
            p.drawEllipse(center, 17, 17)
            remapped = self._shown(code, "")
            if remapped and code in self._maps and code != self._armed:
                self._draw_legend(
                    p, QRectF(center.x() - 22, center.y() - 10, 44, 20), code, "L3", base_px=11)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(self._c_indicator)
                p.drawEllipse(center, 3.5, 3.5)

    def _draw_face(self, p: QPainter, c: QPointF) -> None:
        if self._style.shell == "joycon_l" or not any(self._style.face_labels):
            return
        fx, fy = self._pos()["face"]
        face = c + QPointF(fx, fy)
        d = 31.0
        st = self._style
        positions = [
            (st.face_codes[2], st.face_labels[2], face + QPointF(d, 0), st.face_colors[2]),
            (st.face_codes[3], st.face_labels[3], face + QPointF(0, d), st.face_colors[3]),
            (st.face_codes[0], st.face_labels[0], face + QPointF(0, -d), st.face_colors[0]),
            (st.face_codes[1], st.face_labels[1], face + QPointF(-d, 0), st.face_colors[1]),
        ]
        for code, label, pos, accent in positions:
            remapped = bool(self._maps.get(code)) and code != self._armed
            radius = 18 if remapped else 15
            p.setPen(QPen(self._c_outline, 1.2))
            p.setBrush(self._btn_color(code))
            p.drawEllipse(pos, radius, radius)
            if accent and not remapped and code not in self._pressed and code != self._armed:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(accent), 2.0))
                p.drawEllipse(pos, 11, 11)
            self._draw_legend(
                p, QRectF(pos.x() - 20, pos.y() - 12, 40, 24), code, label,
                accent=accent, base_px=15 if remapped else 13,
            )

    def _draw_dpad(self, p: QPainter, c: QPointF) -> None:
        if self._style.shell == "joycon_r":
            return
        dx, dy = self._pos()["dpad"]
        origin = c + QPointF(dx, dy)
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
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self._c_outline, 1.4))
        outline = QPolygonF([
            origin + QPointF(0, -36), origin + QPointF(36, 0),
            origin + QPointF(0, 36), origin + QPointF(-36, 0),
        ])
        p.drawPolygon(outline)

    def _draw_system(self, p: QPainter, c: QPointF) -> None:
        pos = self._pos()
        for code, key, plus in (("BTN_SELECT", "select", False), ("BTN_START", "start", True)):
            if not getattr(self._style, f"{'select' if code == 'BTN_SELECT' else 'start'}_label"):
                continue
            px, py = pos[key]
            p.setPen(QPen(self._c_outline, 1.2))
            p.setBrush(self._btn_color(code))
            p.drawEllipse(c + QPointF(px, py), 11, 11)
            remapped = bool(self._maps.get(code)) and code != self._armed
            if remapped:
                self._draw_legend(
                    p, QRectF(c.x() + px - 14, c.y() + py - 8, 28, 16),
                    code, "+" if plus else "−", base_px=10,
                )
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(self._c_font2)
                p.drawRect(QRectF(c.x() + px - 4.5, c.y() + py - 1.2, 9, 2.4))
                if plus:
                    p.drawRect(QRectF(c.x() + px - 1.2, c.y() + py - 4.5, 2.4, 9))
        gx, gy = pos["guide"]
        p.setPen(QPen(self._c_outline, 1.2))
        p.setBrush(self._btn_color("BTN_MODE"))
        p.drawEllipse(c + QPointF(gx, gy), 11, 11)
        label = self._style.guide_label or "●"
        remapped = bool(self._maps.get("BTN_MODE")) and self._armed != "BTN_MODE"
        if not remapped:
            p.setBrush(self._c_button2)
            p.drawEllipse(c + QPointF(gx, gy), 7, 7)
        self._draw_legend(
            p, QRectF(c.x() + gx - 16, c.y() + gy - 10, 32, 20), "BTN_MODE", label, base_px=10,
        )
        if self._style.has_capture:
            cx, cy = pos["capture"]
            p.setPen(QPen(self._c_outline, 1.2))
            p.setBrush(self._btn_color("BTN_CAPTURE"))
            p.drawRoundedRect(QRectF(cx - 12, cy - 8, 24, 16), 4, 4)
            self._draw_legend(
                p, QRectF(c.x() + cx - 14, c.y() + cy - 8, 28, 16), "BTN_CAPTURE", "📷", base_px=10,
            )
        if self._style.has_touchpad:
            tx, ty = pos["touchpad"]
            self._draw_legend(
                p, QRectF(tx - 40, ty - 10, 80, 20), "BTN_TOUCHPAD", "触控板", base_px=11,
            )

    def _draw_extras(self, p: QPainter, c: QPointF) -> None:
        for h in self._hits:
            if h.kind != "pill" and h.code not in {e[0] for e in self._style.extras}:
                continue
            if h.code in ("BTN_TOUCHPAD", "BTN_CAPTURE"):
                continue
            if h.kind not in ("pill", "circle"):
                continue
            # Only draw extras that sit on the bottom row / joycon rails
            if abs(h.y) < 70 and not self._style.shell.startswith("joycon"):
                continue
            p.setPen(QPen(self._c_outline, 1.1))
            p.setBrush(self._btn_color(h.code))
            rect = QRectF(h.x - 16, h.y - 10, 32, 20)
            p.drawRoundedRect(rect, 6, 6)
            self._draw_legend(p, rect, h.code, h.label, base_px=10)
