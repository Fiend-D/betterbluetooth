"""Painted keyboard / gamepad visuals with brand themes (keycap-quality sculpting)."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from .gamepad_styles import GamepadStyle, detect_gamepad_style
from .keyboard_styles import KeyboardStyle, detect_style


# ---- Gamepad: sculpted shell + keycap-quality controls ----

@dataclass
class _PadBtn:
    code: str
    label: str
    x: float
    y: float
    w: float = 1.0
    h: float = 1.0
    kind: str = "circle"  # circle | pill | dpad | stick | guide
    face_ix: int = -1     # 0..3 for north/west/east/south color


_JC_ALIAS = {
    "JC_ZL": "BTN_TL2", "JC_L": "BTN_TL", "JC_ZR": "BTN_TR2", "JC_R": "BTN_TR",
    "JC_MINUS": "BTN_SELECT", "JC_PLUS": "BTN_START", "JC_HOME": "BTN_MODE",
    "JC_UP": "BTN_DPAD_UP", "JC_DOWN": "BTN_DPAD_DOWN",
    "JC_LEFT": "BTN_DPAD_LEFT", "JC_RIGHT": "BTN_DPAD_RIGHT",
    "JC_L_STICK": "BTN_THUMBL", "JC_R_STICK": "BTN_THUMBR",
    "JC_X": "BTN_NORTH", "JC_Y": "BTN_WEST", "JC_A": "BTN_EAST", "JC_B": "BTN_SOUTH",
}


def _build_pad_layout(style: GamepadStyle) -> list[_PadBtn]:
    """Click targets in unit space. Shell is painted separately as a real pad silhouette."""
    st = style
    n, w, e, s = st.face_labels
    nc, wc, ec, sc = st.face_codes
    layout = st.layout

    # Shoulders sit on the shell top ledge (not floating far above).
    btns: list[_PadBtn] = [
        _PadBtn("BTN_TL2", st.shoulder_l2, 1.15, 0.55, 2.35, 0.62, "pill"),
        _PadBtn("BTN_TL", st.shoulder_l, 1.35, 1.22, 2.15, 0.58, "pill"),
        _PadBtn("BTN_TR2", st.shoulder_r2, 10.5, 0.55, 2.35, 0.62, "pill"),
        _PadBtn("BTN_TR", st.shoulder_r, 10.5, 1.22, 2.15, 0.58, "pill"),
    ]

    if layout == "playstation":
        dpad_cx, dpad_cy = 3.35, 3.55
        lstick_cx, lstick_cy = 3.55, 6.35
        rstick_cx, rstick_cy = 8.55, 6.35
        face_cx, face_cy = 10.65, 3.85
    else:
        lstick_cx, lstick_cy = 3.35, 3.65
        dpad_cx, dpad_cy = 3.55, 6.45
        rstick_cx, rstick_cy = 8.55, 6.35
        face_cx, face_cy = 10.65, 3.75

    arm = 0.72
    btns += [
        _PadBtn("BTN_DPAD_UP", "↑", dpad_cx - arm / 2, dpad_cy - 1.22, arm, arm, "dpad"),
        _PadBtn("BTN_DPAD_DOWN", "↓", dpad_cx - arm / 2, dpad_cy + 0.50, arm, arm, "dpad"),
        _PadBtn("BTN_DPAD_LEFT", "←", dpad_cx - 1.22, dpad_cy - arm / 2, arm, arm, "dpad"),
        _PadBtn("BTN_DPAD_RIGHT", "→", dpad_cx + 0.50, dpad_cy - arm / 2, arm, arm, "dpad"),
    ]
    sw = 2.05
    btns += [
        _PadBtn("BTN_THUMBL", "L3", lstick_cx - sw / 2, lstick_cy - sw / 2, sw, sw, "stick"),
        _PadBtn("BTN_THUMBR", "R3", rstick_cx - sw / 2, rstick_cy - sw / 2, sw, sw, "stick"),
    ]
    fr = 0.92
    btns += [
        _PadBtn(nc, n, face_cx - fr / 2, face_cy - 1.48, fr, fr, "circle", 0),
        _PadBtn(wc, w, face_cx - 1.48, face_cy - fr / 2, fr, fr, "circle", 1),
        _PadBtn(ec, e, face_cx + 0.56, face_cy - fr / 2, fr, fr, "circle", 2),
        _PadBtn(sc, s, face_cx - fr / 2, face_cy + 0.56, fr, fr, "circle", 3),
    ]
    btns += [
        _PadBtn("BTN_SELECT", st.select_label, 5.55, 3.55, 1.2, 0.48, "pill"),
        _PadBtn("BTN_START", st.start_label, 7.25, 3.55, 1.2, 0.48, "pill"),
        _PadBtn("BTN_MODE", st.guide_label or "●", 6.45, 4.45, 1.1, 1.1, "guide"),
    ]
    return btns


_PAD_UNIT_W = 14.0
_PAD_UNIT_H = 8.6


def _shell_path(ox: float, oy: float, unit: float) -> QPainterPath:
    """Controller silhouette: wide top, flared grips, slight waist."""
    # Unit bounding box roughly (0.2, 1.35) → (13.8, 8.35)
    l, t = ox + unit * 0.25, oy + unit * 1.35
    r, b = ox + unit * 13.75, oy + unit * 8.35
    w, h = r - l, b - t
    path = QPainterPath()
    # Top ledge (where shoulders sit)
    path.moveTo(l + w * 0.18, t + h * 0.02)
    path.cubicTo(l + w * 0.28, t - h * 0.02, l + w * 0.72, t - h * 0.02, l + w * 0.82, t + h * 0.02)
    # Right shoulder corner → right grip
    path.cubicTo(l + w * 0.96, t + h * 0.08, l + w * 1.02, t + h * 0.28, l + w * 0.98, t + h * 0.48)
    path.cubicTo(l + w * 0.96, t + h * 0.72, l + w * 0.92, t + h * 0.95, l + w * 0.78, b)
    # Bottom between grips (inward waist)
    path.cubicTo(l + w * 0.68, b - h * 0.06, l + w * 0.58, b - h * 0.14, l + w * 0.50, b - h * 0.16)
    path.cubicTo(l + w * 0.42, b - h * 0.14, l + w * 0.32, b - h * 0.06, l + w * 0.22, b)
    # Left grip → left shoulder
    path.cubicTo(l + w * 0.08, t + h * 0.95, l + w * 0.04, t + h * 0.72, l + w * 0.02, t + h * 0.48)
    path.cubicTo(l - w * 0.02, t + h * 0.28, l + w * 0.04, t + h * 0.08, l + w * 0.18, t + h * 0.02)
    path.closeSubpath()
    return path


class VisualGamepad(QWidget):
    """Painted mainstream gamepad (Xbox / Switch / PS / generic); auto-matched by device name."""

    keyPicked = Signal(str)
    bindRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(320)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._style: GamepadStyle = detect_gamepad_style(None)
        self._buttons = _build_pad_layout(self._style)
        self._pressed: set[str] = set()
        self._armed: str | None = None
        self._maps: dict[str, str] = {}
        self._hover: str | None = None
        self._lx = self._ly = self._rx = self._ry = 0.0
        self._brand_label = ""
        self._tip = QLabel("点击按键选源 → 再按目标键完成改建；实体按键会高亮。", self)
        self._tip.setWordWrap(True)
        self._tip.setProperty("role", "secondary")
        self._banner = QLabel(self)
        self._banner.setAlignment(Qt.AlignCenter)
        self._banner.hide()

    def set_device_name(self, name: str | None) -> None:
        self._style = detect_gamepad_style(name)
        self._buttons = _build_pad_layout(self._style)
        self._brand_label = self._style.label if self._style.id != "generic" else ""
        if self._brand_label:
            self._tip.setText(f"样式：{self._brand_label} · 点按键改键，直接按实体键仅测试高亮")
        else:
            self._tip.setText("通用手柄布局 · 点按键改键，直接按实体键仅测试高亮")
        self.update()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._tip.setGeometry(8, self.height() - 22, self.width() - 16, 20)
        self._banner.setGeometry(12, 4, max(40, self.width() - 24), 28)

    def _layout_metrics(self) -> tuple[float, float, float]:
        tip_h = 24
        pad = 6
        avail_w = max(1.0, self.width() - pad * 2)
        avail_h = max(1.0, self.height() - tip_h - pad * 2)
        unit = min(avail_w / (_PAD_UNIT_W + 0.4), avail_h / (_PAD_UNIT_H + 0.3))
        board_w = unit * _PAD_UNIT_W
        board_h = unit * _PAD_UNIT_H
        ox = (self.width() - board_w) / 2
        oy = pad + max(0.0, (avail_h - board_h) / 2)
        if self._armed:
            oy = max(oy, 36.0)
        return ox, oy, unit

    def _btn_rect(self, btn: _PadBtn, ox: float, oy: float, unit: float) -> QRectF:
        return QRectF(ox + btn.x * unit, oy + btn.y * unit, btn.w * unit, btn.h * unit)

    def _canon(self, code: str) -> str:
        return _JC_ALIAS.get(code, code)

    def _hit(self, pos) -> str | None:
        ox, oy, unit = self._layout_metrics()
        hits = [b for b in self._buttons if self._btn_rect(b, ox, oy, unit).contains(pos)]
        if not hits:
            return None
        hits.sort(key=lambda b: b.w * b.h)
        return hits[0].code

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

    def set_mappings(self, maps: dict[str, str]) -> None:
        self._maps = {self._canon(k): v for k, v in maps.items()}
        self.update()

    def set_armed(self, code: str | None) -> None:
        self._armed = self._canon(code) if code else None
        if self._armed:
            label = next((b.label for b in self._buttons if b.code == self._armed), self._armed)
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
        st = self._style
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        ox, oy, unit = self._layout_metrics()

        shell = _shell_path(ox, oy, unit)
        # Drop shadow
        shadow = QPainterPath(shell)
        shadow.translate(0, unit * 0.08)
        painter.setPen(Qt.NoPen)
        sh = QColor(0, 0, 0, 55)
        painter.setBrush(sh)
        painter.drawPath(shadow)

        # Shell body with vertical bevel
        bounds = shell.boundingRect()
        case_grad = QLinearGradient(bounds.topLeft(), bounds.bottomLeft())
        case_grad.setColorAt(0.0, QColor(st.gloss))
        case_grad.setColorAt(0.18, QColor(st.plate))
        case_grad.setColorAt(1.0, QColor(st.case))
        painter.setBrush(case_grad)
        painter.setPen(QPen(QColor(st.case_edge), 1.8))
        painter.drawPath(shell)

        # Soft top-plate sheen
        sheen = QLinearGradient(bounds.left(), bounds.top(), bounds.left(), bounds.top() + unit * 1.8)
        c0 = QColor(255, 255, 255, 28)
        c1 = QColor(255, 255, 255, 0)
        sheen.setColorAt(0.0, c0)
        sheen.setColorAt(1.0, c1)
        painter.setBrush(sheen)
        painter.setPen(Qt.NoPen)
        painter.drawPath(shell)

        # Unified d-pad base (single cross under the four hit targets)
        dpad_btns = [b for b in self._buttons if b.kind == "dpad"]
        if dpad_btns:
            xs = [self._btn_rect(b, ox, oy, unit) for b in dpad_btns]
            cx = sum(r.center().x() for r in xs) / 4
            cy = sum(r.center().y() for r in xs) / 4
            arm = xs[0].width()
            self._paint_dpad_base(painter, cx, cy, arm, unit, st)

        if st.brand_mark or self._brand_label:
            painter.setPen(QColor(st.accent))
            font = QFont(painter.font())
            font.setPixelSize(max(8, int(unit * 0.26)))
            font.setBold(True)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 1.1)
            painter.setFont(font)
            painter.drawText(
                QRectF(bounds.left() + unit * 0.55, bounds.bottom() - unit * 0.85,
                       bounds.width() * 0.4, unit * 0.4),
                Qt.AlignLeft | Qt.AlignVCenter, st.brand_mark or self._brand_label,
            )

        for btn in self._buttons:
            if btn.kind == "dpad":
                self._paint_dpad_arm(painter, btn, ox, oy, unit, st)
            elif btn.kind == "stick":
                self._paint_stick(painter, btn, ox, oy, unit, st)
            else:
                self._paint_btn(painter, btn, ox, oy, unit, st)

    def _paint_dpad_base(self, painter: QPainter, cx: float, cy: float, arm: float,
                         unit: float, st: GamepadStyle) -> None:
        thick = arm * 0.98
        span = arm * 2.55
        path = QPainterPath()
        # Vertical bar
        path.addRoundedRect(QRectF(cx - thick / 2, cy - span / 2, thick, span), unit * 0.12, unit * 0.12)
        # Horizontal bar
        path.addRoundedRect(QRectF(cx - span / 2, cy - thick / 2, span, thick), unit * 0.12, unit * 0.12)
        side = QColor(st.button_side)
        painter.setPen(Qt.NoPen)
        painter.setBrush(side)
        painter.drawPath(path)
        face = QRectF(cx - span / 2 + unit * 0.04, cy - span / 2 + unit * 0.03,
                      span - unit * 0.08, span - unit * 0.12)
        # Clip-ish: redraw slightly inset cross for the face
        inset = QPainterPath()
        t2, s2 = thick - unit * 0.1, span - unit * 0.12
        inset.addRoundedRect(QRectF(cx - t2 / 2, cy - s2 / 2, t2, s2), unit * 0.1, unit * 0.1)
        inset.addRoundedRect(QRectF(cx - s2 / 2, cy - t2 / 2, s2, t2), unit * 0.1, unit * 0.1)
        grad = QLinearGradient(QPointF(cx, cy - s2 / 2), QPointF(cx, cy + s2 / 2))
        grad.setColorAt(0.0, QColor(st.dpad_top))
        grad.setColorAt(1.0, QColor(st.dpad))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(st.case_edge), 0.8))
        painter.drawPath(inset)

    def _paint_dpad_arm(self, painter: QPainter, btn: _PadBtn, ox: float, oy: float,
                        unit: float, st: GamepadStyle) -> None:
        rect = self._btn_rect(btn, ox, oy, unit)
        pressed = btn.code in self._pressed
        armed = btn.code == self._armed
        hover = btn.code == self._hover
        bound = self._maps.get(btn.code, "")
        if pressed or armed or hover:
            col = QColor(st.armed if armed else (st.pressed if pressed else st.accent))
            col.setAlpha(70 if hover and not pressed and not armed else 140)
            painter.setPen(Qt.NoPen)
            painter.setBrush(col)
            painter.drawRoundedRect(rect.adjusted(unit * 0.05, unit * 0.05, -unit * 0.05, -unit * 0.05),
                                    unit * 0.1, unit * 0.1)
        legend = QColor("#111111" if armed else st.legend)
        if QColor(st.dpad_top).lightness() < 140 and not armed:
            legend = QColor(st.legend)
        painter.setPen(legend)
        font = QFont(painter.font())
        font.setPixelSize(max(8, int(unit * 0.32)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, btn.label if not bound else bound[:4])
        if armed:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(st.armed), 2.4))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), unit * 0.1, unit * 0.1)

    def _paint_stick(self, painter: QPainter, btn: _PadBtn, ox: float, oy: float,
                     unit: float, st: GamepadStyle) -> None:
        rect = self._btn_rect(btn, ox, oy, unit)
        pressed = btn.code in self._pressed
        armed = btn.code == self._armed
        bound = self._maps.get(btn.code, "")
        # Well
        painter.setPen(QPen(QColor(st.case_edge), 1.0))
        painter.setBrush(QColor(st.stick_well))
        painter.drawEllipse(rect)
        ring = rect.adjusted(unit * 0.12, unit * 0.12, -unit * 0.12, -unit * 0.12)
        painter.setBrush(QColor(st.stick_ring))
        painter.drawEllipse(ring)
        # Cap
        is_left = btn.code == "BTN_THUMBL"
        sx = self._lx if is_left else self._rx
        sy = self._ly if is_left else self._ry
        travel = unit * 0.38
        cx = ring.center().x() + sx * travel
        cy = ring.center().y() + sy * travel
        cap_r = unit * 0.55
        cap = QRectF(cx - cap_r, cy - cap_r, cap_r * 2, cap_r * 2)
        side = QColor(st.button_side)
        painter.setPen(Qt.NoPen)
        painter.setBrush(side)
        painter.drawEllipse(cap.adjusted(unit * 0.02, unit * 0.04, -unit * 0.02, unit * 0.02))
        face = cap.adjusted(unit * 0.06, unit * 0.04, -unit * 0.06, -unit * 0.10)
        if pressed:
            face.translate(0, unit * 0.03)
        grad = QRadialGradient(face.center(), face.width() / 2)
        top = QColor(st.pressed if pressed else st.stick_cap).lighter(118)
        bot = QColor(st.pressed if pressed else st.stick_cap)
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bot)
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(st.armed if armed else st.case_edge), 2.0 if armed else 0.9))
        painter.drawEllipse(face)
        # Dimple
        dim = QRectF(face.center().x() - unit * 0.12, face.center().y() - unit * 0.12,
                     unit * 0.24, unit * 0.24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(st.accent if pressed or armed else st.legend_dim))
        painter.drawEllipse(dim)
        painter.setPen(QColor(st.legend_dim))
        font = QFont(painter.font())
        font.setPixelSize(max(7, int(unit * 0.20)))
        painter.setFont(font)
        painter.drawText(QRectF(rect.left(), rect.bottom() - unit * 0.35, rect.width(), unit * 0.32),
                         Qt.AlignCenter, bound[:5] if bound and not armed else btn.label)
        if armed:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(st.armed), 2.6))
            painter.drawEllipse(rect.adjusted(-1, -1, 1, 1))

    def _paint_btn(self, painter: QPainter, btn: _PadBtn, ox: float, oy: float,
                   unit: float, st: GamepadStyle) -> None:
        rect = self._btn_rect(btn, ox, oy, unit)
        pressed = btn.code in self._pressed
        armed = btn.code == self._armed
        hover = btn.code == self._hover
        bound = self._maps.get(btn.code, "")

        face_accent = ""
        if btn.face_ix >= 0 and btn.face_ix < len(st.face_colors):
            face_accent = st.face_colors[btn.face_ix]

        side = QColor(st.button_side)
        face = QColor(st.button_top)
        body = QColor(st.button)
        if face_accent and btn.kind in ("circle", "guide") and not armed and not pressed:
            # Keep dark/light shell, tint legend via accent ring instead of filling whole button.
            pass
        if armed:
            face = QColor(st.armed)
            body = QColor(st.armed).darker(125)
            side = QColor(st.armed).darker(150)
        elif pressed:
            face = QColor(st.pressed)
            body = QColor(st.pressed).darker(115)
            side = QColor(st.pressed).darker(140)
        elif hover:
            face = QColor(face).lighter(110)

        painter.setPen(Qt.NoPen)
        painter.setBrush(side)
        roundish = btn.kind in ("circle", "guide")
        if roundish:
            painter.drawEllipse(rect)
            face_rect = rect.adjusted(unit * 0.07, unit * 0.05, -unit * 0.07, -unit * 0.12)
        else:
            radius = max(2.0, unit * 0.26)
            painter.drawRoundedRect(rect, radius, radius)
            face_rect = rect.adjusted(unit * 0.04, unit * 0.03, -unit * 0.04, -unit * 0.10)
        if pressed and not armed:
            face_rect.translate(0, unit * 0.035)

        grad = QLinearGradient(face_rect.topLeft(), face_rect.bottomLeft())
        grad.setColorAt(0.0, face)
        grad.setColorAt(1.0, body)
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(st.armed if armed else st.case_edge), 2.2 if armed else 0.85))
        if roundish:
            painter.drawEllipse(face_rect)
            if face_accent and not armed:
                ring = QColor(face_accent)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(ring, max(1.6, unit * 0.07)))
                painter.drawEllipse(face_rect.adjusted(unit * 0.06, unit * 0.06, -unit * 0.06, -unit * 0.06))
        else:
            radius = max(2.0, unit * 0.22)
            painter.drawRoundedRect(face_rect, radius * 0.85, radius * 0.85)

        # Legend
        if face_accent and not armed and not pressed:
            legend = QColor(face_accent)
        else:
            legend = QColor(st.legend)
            if armed:
                legend = QColor("#111111")
            elif pressed:
                legend = QColor("#FFFFFF") if QColor(st.pressed).lightness() < 160 else QColor("#111111")
        painter.setPen(legend)
        font = QFont(painter.font())
        text_rect = face_rect.adjusted(1, 1, -1, -1)
        if bound and not armed:
            font.setPixelSize(max(6, int(unit * 0.18)))
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(st.legend_dim))
            painter.drawText(
                QRectF(text_rect.left(), text_rect.top(), text_rect.width(), text_rect.height() * 0.40),
                Qt.AlignHCenter | Qt.AlignBottom, btn.label or "·",
            )
            font.setPixelSize(max(7, int(unit * 0.26)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(st.accent))
            painter.drawText(
                QRectF(text_rect.left(), text_rect.center().y() - 1, text_rect.width(), text_rect.height() * 0.55),
                Qt.AlignHCenter | Qt.AlignTop, bound[:6],
            )
        else:
            px = max(7, int(unit * (0.38 if len(btn.label) <= 2 else 0.20)))
            font.setPixelSize(px)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, btn.label)

        if armed:
            painter.setBrush(Qt.NoBrush)
            glow = QColor(st.armed)
            glow.setAlpha(190)
            painter.setPen(QPen(glow, 2.8))
            if roundish:
                painter.drawEllipse(rect.adjusted(-1.5, -1.5, 1.5, 1.5))
            else:
                painter.drawRoundedRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5), unit * 0.22, unit * 0.22)


# ---- Keyboard: painted 108-key full layout with brand themes ----

@dataclass
class _KeyGeom:
    code: str
    label: str
    x: float          # unit x
    y: float          # unit y
    w: float = 1.0
    h: float = 1.0
    mod: bool = False  # darker modifier / system keycap


def _build_108() -> list[_KeyGeom]:
    """ANSI full-size (~104/108) layout in keycap units."""
    keys: list[_KeyGeom] = []
    g = 0.2  # cluster gap

    def add(code: str, label: str, x: float, y: float, w: float = 1.0, h: float = 1.0, mod: bool = False):
        keys.append(_KeyGeom(code, label, x, y, w, h, mod))

    # Row −1 — media (brings ANSI 104 up to a common “108” full board)
    y = 0.0
    kx = 15.5 + g + 3 + g
    add("KEY_MUTE", "Mute", kx, y, mod=True)
    add("KEY_VOLUMEDOWN", "Vol−", kx + 1, y, mod=True)
    add("KEY_VOLUMEUP", "Vol+", kx + 2, y, mod=True)
    add("KEY_PLAYPAUSE", "▶", kx + 3, y, mod=True)

    # Row 0 — function
    y = 1.15
    add("KEY_ESC", "Esc", 0, y, mod=True)
    x = 2.0
    for i, lab in enumerate(["F1", "F2", "F3", "F4"]):
        add(f"KEY_F{i + 1}", lab, x + i, y, mod=True)
    x = 6.5
    for i, lab in enumerate(["F5", "F6", "F7", "F8"]):
        add(f"KEY_F{i + 5}", lab, x + i, y, mod=True)
    x = 11.0
    for i, lab in enumerate(["F9", "F10", "F11", "F12"]):
        add(f"KEY_F{i + 9}", lab, x + i, y, mod=True)
    nx = 15.5 + g
    add("KEY_SYSRQ", "PrtSc", nx, y, mod=True)
    add("KEY_SCROLLLOCK", "ScrLk", nx + 1, y, mod=True)
    add("KEY_PAUSE", "Pause", nx + 2, y, mod=True)

    # Row 1 — numbers
    y = 2.4
    row1 = [
        ("KEY_GRAVE", "`", 1), ("KEY_1", "1", 1), ("KEY_2", "2", 1), ("KEY_3", "3", 1),
        ("KEY_4", "4", 1), ("KEY_5", "5", 1), ("KEY_6", "6", 1), ("KEY_7", "7", 1),
        ("KEY_8", "8", 1), ("KEY_9", "9", 1), ("KEY_0", "0", 1), ("KEY_MINUS", "-", 1),
        ("KEY_EQUAL", "=", 1), ("KEY_BACKSPACE", "⌫", 2),
    ]
    x = 0.0
    for code, lab, w in row1:
        add(code, lab, x, y, w, mod=(code == "KEY_BACKSPACE"))
        x += w
    nx = 15.5 + g
    add("KEY_INSERT", "Ins", nx, y, mod=True)
    add("KEY_HOME", "Home", nx + 1, y, mod=True)
    add("KEY_PAGEUP", "PgUp", nx + 2, y, mod=True)
    kx = nx + 3 + g
    add("KEY_NUMLOCK", "Num", kx, y, mod=True)
    add("KEY_KPSLASH", "/", kx + 1, y, mod=True)
    add("KEY_KPASTERISK", "*", kx + 2, y, mod=True)
    add("KEY_KPMINUS", "-", kx + 3, y, mod=True)

    # Row 2 — QWERTY
    y = 3.4
    row2 = [
        ("KEY_TAB", "Tab", 1.5, True),
        ("KEY_Q", "Q", 1, False), ("KEY_W", "W", 1, False), ("KEY_E", "E", 1, False),
        ("KEY_R", "R", 1, False), ("KEY_T", "T", 1, False), ("KEY_Y", "Y", 1, False),
        ("KEY_U", "U", 1, False), ("KEY_I", "I", 1, False), ("KEY_O", "O", 1, False),
        ("KEY_P", "P", 1, False), ("KEY_LEFTBRACE", "[", 1, False), ("KEY_RIGHTBRACE", "]", 1, False),
        ("KEY_BACKSLASH", "\\", 1.5, True),
    ]
    x = 0.0
    for code, lab, w, mod in row2:
        add(code, lab, x, y, w, mod=mod)
        x += w
    nx = 15.5 + g
    add("KEY_DELETE", "Del", nx, y, mod=True)
    add("KEY_END", "End", nx + 1, y, mod=True)
    add("KEY_PAGEDOWN", "PgDn", nx + 2, y, mod=True)
    kx = nx + 3 + g
    add("KEY_KP7", "7", kx, y)
    add("KEY_KP8", "8", kx + 1, y)
    add("KEY_KP9", "9", kx + 2, y)
    add("KEY_KPPLUS", "+", kx + 3, y, h=2.0, mod=True)

    # Row 3 — home
    y = 4.4
    row3 = [
        ("KEY_CAPSLOCK", "Caps", 1.75, True),
        ("KEY_A", "A", 1, False), ("KEY_S", "S", 1, False), ("KEY_D", "D", 1, False),
        ("KEY_F", "F", 1, False), ("KEY_G", "G", 1, False), ("KEY_H", "H", 1, False),
        ("KEY_J", "J", 1, False), ("KEY_K", "K", 1, False), ("KEY_L", "L", 1, False),
        ("KEY_SEMICOLON", ";", 1, False), ("KEY_APOSTROPHE", "'", 1, False),
        ("KEY_ENTER", "Enter", 2.25, True),
    ]
    x = 0.0
    for code, lab, w, mod in row3:
        add(code, lab, x, y, w, mod=mod)
        x += w
    kx = 15.5 + g + 3 + g
    add("KEY_KP4", "4", kx, y)
    add("KEY_KP5", "5", kx + 1, y)
    add("KEY_KP6", "6", kx + 2, y)

    # Row 4 — shift
    y = 5.4
    row4 = [
        ("KEY_LEFTSHIFT", "Shift", 2.25, True),
        ("KEY_Z", "Z", 1, False), ("KEY_X", "X", 1, False), ("KEY_C", "C", 1, False),
        ("KEY_V", "V", 1, False), ("KEY_B", "B", 1, False), ("KEY_N", "N", 1, False),
        ("KEY_M", "M", 1, False), ("KEY_COMMA", ",", 1, False), ("KEY_DOT", ".", 1, False),
        ("KEY_SLASH", "/", 1, False), ("KEY_RIGHTSHIFT", "Shift", 2.75, True),
    ]
    x = 0.0
    for code, lab, w, mod in row4:
        add(code, lab, x, y, w, mod=mod)
        x += w
    nx = 15.5 + g
    add("KEY_UP", "↑", nx + 1, y)
    kx = nx + 3 + g
    add("KEY_KP1", "1", kx, y)
    add("KEY_KP2", "2", kx + 1, y)
    add("KEY_KP3", "3", kx + 2, y)
    add("KEY_KPENTER", "Ent", kx + 3, y, h=2.0, mod=True)

    # Row 5 — bottom
    y = 6.4
    row5 = [
        ("KEY_LEFTCTRL", "Ctrl", 1.25, True),
        ("KEY_LEFTMETA", "Win", 1.25, True),
        ("KEY_LEFTALT", "Alt", 1.25, True),
        ("KEY_SPACE", "", 6.25, False),
        ("KEY_RIGHTALT", "Alt", 1.25, True),
        ("KEY_RIGHTMETA", "Win", 1.25, True),
        ("KEY_COMPOSE", "Menu", 1.25, True),
        ("KEY_RIGHTCTRL", "Ctrl", 1.25, True),
    ]
    x = 0.0
    for code, lab, w, mod in row5:
        add(code, lab, x, y, w, mod=mod)
        x += w
    nx = 15.5 + g
    add("KEY_LEFT", "←", nx, y)
    add("KEY_DOWN", "↓", nx + 1, y)
    add("KEY_RIGHT", "→", nx + 2, y)
    kx = nx + 3 + g
    add("KEY_KP0", "0", kx, y, w=2.0)
    add("KEY_KPDOT", ".", kx + 2, y)

    return keys


_KB_108 = _build_108()
_KB_UNIT_W = max(k.x + k.w for k in _KB_108) + 0.2
_KB_UNIT_H = max(k.y + k.h for k in _KB_108)


class VisualKeyboard(QWidget):
    """Painted 108-key full keyboard; click a key to start remapping."""

    keyPicked = Signal(str)
    bindRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._style: KeyboardStyle = detect_style(None)
        self._pressed: set[str] = set()
        self._armed: str | None = None
        self._maps: dict[str, str] = {}
        self._hover: str | None = None
        self._brand_label = ""
        self._tip = QLabel("点击键帽选择源键 → 再按目标键完成改建；未改建时按键仅高亮测试。", self)
        self._tip.setWordWrap(True)
        self._tip.setProperty("role", "secondary")
        self._tip.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._banner = QLabel(self)
        self._banner.setAlignment(Qt.AlignCenter)
        self._banner.hide()

    def set_device_name(self, name: str | None) -> None:
        self._style = detect_style(name)
        self._brand_label = self._style.label if self._style.id != "default" else ""
        if self._brand_label:
            self._tip.setText(f"样式：{self._brand_label} · 点键帽改键，直接按键仅测试高亮")
        else:
            self._tip.setText("通用 108 全键盘 · 点键帽改键，直接按键仅测试高亮")
        self.update()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._tip.setGeometry(8, self.height() - 22, self.width() - 16, 20)
        self._banner.setGeometry(12, 4, max(40, self.width() - 24), 28)

    def _layout_metrics(self) -> tuple[float, float, float, float]:
        """Return (origin_x, origin_y, unit_px, gap_px)."""
        tip_h = 24
        pad = 10
        avail_w = max(1.0, self.width() - pad * 2)
        avail_h = max(1.0, self.height() - tip_h - pad * 2)
        # Gaps between keycaps ~0.08u
        unit = min(avail_w / (_KB_UNIT_W + 0.5), avail_h / (_KB_UNIT_H + 0.4))
        board_w = unit * _KB_UNIT_W
        board_h = unit * _KB_UNIT_H
        ox = (self.width() - board_w) / 2
        oy = pad + max(0.0, (avail_h - board_h) / 2)
        return ox, oy, unit, unit * 0.08

    def _key_rect(self, key: _KeyGeom, ox: float, oy: float, unit: float, gap: float) -> QRectF:
        return QRectF(
            ox + key.x * unit + gap * 0.5,
            oy + key.y * unit + gap * 0.5,
            key.w * unit - gap,
            key.h * unit - gap,
        )

    def _hit(self, pos) -> str | None:
        ox, oy, unit, gap = self._layout_metrics()
        for key in _KB_108:
            if self._key_rect(key, ox, oy, unit, gap).contains(pos):
                return key.code
        return None

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
        super().mousePressEvent(e)

    def set_key_state(self, code: str, pressed: bool) -> None:
        aliases = {"KEY_MENU": "KEY_COMPOSE", "KEY_APP": "KEY_COMPOSE", "KEY_CONTEXT": "KEY_COMPOSE"}
        code = aliases.get(code, code)
        if pressed:
            self._pressed.add(code)
        else:
            self._pressed.discard(code)
        self.update()

    def set_mappings(self, maps: dict[str, str]) -> None:
        self._maps = dict(maps)
        self.update()

    def set_armed(self, code: str | None) -> None:
        self._armed = code
        if code:
            label = next((k.label for k in _KB_108 if k.code == code), code)
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
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        st = self._style
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        ox, oy, unit, gap = self._layout_metrics()
        # Leave room for the remap banner when armed.
        if self._armed:
            oy = max(oy, 36.0)
        board = QRectF(ox - unit * 0.35, oy - unit * 0.35,
                       unit * _KB_UNIT_W + unit * 0.7, unit * _KB_UNIT_H + unit * 0.7)

        # Case body with subtle bevel
        case_grad = QLinearGradient(board.topLeft(), board.bottomLeft())
        case_grad.setColorAt(0.0, QColor(st.plate))
        case_grad.setColorAt(1.0, QColor(st.case))
        painter.setPen(QPen(QColor(st.case_edge), 1.5))
        painter.setBrush(case_grad)
        painter.drawRoundedRect(board, unit * 0.35, unit * 0.35)

        # Brand badge
        mark = st.brand_mark or self._brand_label
        if mark:
            painter.setPen(QColor(st.accent))
            font = QFont(painter.font())
            font.setPixelSize(max(8, int(unit * 0.32)))
            font.setBold(True)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
            painter.setFont(font)
            painter.drawText(
                QRectF(board.left() + unit * 0.4, board.bottom() - unit * 0.55, board.width() * 0.4, unit * 0.4),
                Qt.AlignLeft | Qt.AlignVCenter, mark,
            )

        radius = max(2.0, unit * 0.14)
        for key in _KB_108:
            rect = self._key_rect(key, ox, oy, unit, gap)
            pressed = key.code in self._pressed
            armed = key.code == self._armed
            hover = key.code == self._hover
            bound = self._maps.get(key.code, "")

            # Keycap base (side) then top face inset for sculpted look
            side = QColor(st.mod_keycap_top if key.mod else st.keycap_side)
            face = QColor(st.mod_keycap_top if key.mod else st.keycap_top)
            body = QColor(st.mod_keycap if key.mod else st.keycap)
            if armed:
                face = QColor(st.armed)
                body = QColor(st.armed).darker(125)
                side = QColor(st.armed).darker(150)
            elif pressed:
                face = QColor(st.pressed)
                body = QColor(st.pressed).darker(115)
                side = QColor(st.pressed).darker(140)
            elif bound:
                # Remapped keys: tint with accent so they don't look like plain test keys.
                face = QColor(st.keycap_top if not key.mod else st.mod_keycap_top)
                tint = QColor(st.accent)
                tint.setAlpha(55)
                face = QColor(
                    min(255, face.red() + tint.red() // 6),
                    min(255, face.green() + tint.green() // 6),
                    min(255, face.blue() + tint.blue() // 6),
                )
            elif hover:
                face = QColor(face).lighter(108)

            painter.setPen(Qt.NoPen)
            painter.setBrush(side)
            painter.drawRoundedRect(rect, radius, radius)

            face_rect = rect.adjusted(unit * 0.04, unit * 0.03, -unit * 0.04, -unit * 0.12)
            if pressed and not armed:
                face_rect.translate(0, unit * 0.04)
            grad = QLinearGradient(face_rect.topLeft(), face_rect.bottomLeft())
            grad.setColorAt(0.0, face)
            grad.setColorAt(1.0, body)
            painter.setBrush(grad)
            painter.setPen(QPen(QColor(st.armed if armed else st.case_edge), 2.4 if armed else 0.8))
            painter.drawRoundedRect(face_rect, radius * 0.85, radius * 0.85)

            # Legend — remapped keys show destination prominently
            legend = QColor(st.mod_legend if key.mod else st.legend)
            if armed:
                legend = QColor("#111111")
            elif pressed:
                legend = QColor("#FFFFFF") if QColor(st.pressed).lightness() < 160 else QColor("#111111")
            painter.setPen(legend)
            font = QFont(painter.font())
            text_rect = face_rect.adjusted(2, 1, -2, -1)
            if key.code == "KEY_SPACE" and not bound and not armed:
                pass
            elif bound and not armed:
                font.setPixelSize(max(6, int(unit * 0.22)))
                font.setBold(False)
                painter.setFont(font)
                painter.setPen(QColor(st.legend_dim if not key.mod else st.mod_legend))
                painter.drawText(
                    QRectF(text_rect.left(), text_rect.top(), text_rect.width(), text_rect.height() * 0.42),
                    Qt.AlignHCenter | Qt.AlignBottom,
                    key.label or "Space",
                )
                font.setPixelSize(max(8, int(unit * 0.34)))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(st.accent))
                painter.drawText(
                    QRectF(text_rect.left(), text_rect.center().y() - 2, text_rect.width(), text_rect.height() * 0.55),
                    Qt.AlignHCenter | Qt.AlignTop,
                    bound[:8],
                )
            else:
                px = max(7, int(unit * (0.40 if armed else (0.36 if len(key.label) <= 2 else 0.28))))
                font.setPixelSize(px)
                font.setBold(True if armed else len(key.label) <= 2)
                painter.setFont(font)
                painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, key.label)

            if armed:
                # Outer glow ring
                painter.setBrush(Qt.NoBrush)
                glow = QColor(st.armed)
                glow.setAlpha(180)
                painter.setPen(QPen(glow, 3.0))
                painter.drawRoundedRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 1, radius + 1)
