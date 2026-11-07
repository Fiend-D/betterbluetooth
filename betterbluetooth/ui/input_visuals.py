"""Painted keyboard / gamepad visuals with brand themes (keycap-quality sculpting)."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from .gamepad_styles import GamepadStyle, detect_gamepad_style
from .keyboard_styles import KeyboardStyle, detect_style


# ---- Gamepad: painted body matching keyboard keycap quality ----

@dataclass
class _PadBtn:
    code: str
    label: str
    x: float  # unit coords relative to body origin
    y: float
    w: float = 1.0
    h: float = 1.0
    kind: str = "circle"  # circle | round | pill | dpad | stick


_JC_ALIAS = {
    "JC_ZL": "BTN_TL2", "JC_L": "BTN_TL", "JC_ZR": "BTN_TR2", "JC_R": "BTN_TR",
    "JC_MINUS": "BTN_SELECT", "JC_PLUS": "BTN_START", "JC_HOME": "BTN_MODE",
    "JC_UP": "BTN_DPAD_UP", "JC_DOWN": "BTN_DPAD_DOWN",
    "JC_LEFT": "BTN_DPAD_LEFT", "JC_RIGHT": "BTN_DPAD_RIGHT",
    "JC_L_STICK": "BTN_THUMBL", "JC_R_STICK": "BTN_THUMBR",
    "JC_X": "BTN_NORTH", "JC_Y": "BTN_WEST", "JC_A": "BTN_EAST", "JC_B": "BTN_SOUTH",
}


def _build_pad_layout(style: GamepadStyle) -> list[_PadBtn]:
    """Build clickable controls in unit space (body ~14×8, shoulders above)."""
    st = style
    n, w, e, s = st.face_labels
    nc, wc, ec, sc = st.face_codes
    btns: list[_PadBtn] = []

    # Shoulders / triggers
    btns += [
        _PadBtn("BTN_TL2", st.shoulder_l2, 0.4, 0.15, 2.2, 0.7, "pill"),
        _PadBtn("BTN_TL", st.shoulder_l, 0.6, 0.95, 2.0, 0.65, "pill"),
        _PadBtn("BTN_TR2", st.shoulder_r2, 11.4, 0.15, 2.2, 0.7, "pill"),
        _PadBtn("BTN_TR", st.shoulder_r, 11.4, 0.95, 2.0, 0.65, "pill"),
    ]

    layout = st.layout
    # Left cluster: Xbox / Switch put stick high + dpad low; PS puts dpad high + stick low.
    if layout == "playstation":
        dpad_cx, dpad_cy = 3.2, 3.55
        lstick_cx, lstick_cy = 3.2, 6.1
        rstick_cx, rstick_cy = 8.4, 6.1
        face_cx, face_cy = 10.8, 3.9
    else:
        # xbox / switch / generic / 8bitdo
        lstick_cx, lstick_cy = 3.1, 3.5
        dpad_cx, dpad_cy = 3.1, 6.15
        rstick_cx, rstick_cy = 8.5, 6.15
        face_cx, face_cy = 10.9, 3.7

    # D-pad cross (four hit targets)
    d = 0.78
    btns += [
        _PadBtn("BTN_DPAD_UP", "↑", dpad_cx - d / 2, dpad_cy - 1.35, d, d, "dpad"),
        _PadBtn("BTN_DPAD_DOWN", "↓", dpad_cx - d / 2, dpad_cy + 0.55, d, d, "dpad"),
        _PadBtn("BTN_DPAD_LEFT", "←", dpad_cx - 1.35, dpad_cy - d / 2, d, d, "dpad"),
        _PadBtn("BTN_DPAD_RIGHT", "→", dpad_cx + 0.55, dpad_cy - d / 2, d, d, "dpad"),
    ]

    # Sticks (click = L3/R3)
    btns += [
        _PadBtn("BTN_THUMBL", "L3", lstick_cx - 1.05, lstick_cy - 1.05, 2.1, 2.1, "stick"),
        _PadBtn("BTN_THUMBR", "R3", rstick_cx - 1.05, rstick_cy - 1.05, 2.1, 2.1, "stick"),
    ]

    # Face diamond
    fr = 0.95
    btns += [
        _PadBtn(nc, n, face_cx - fr / 2, face_cy - 1.55, fr, fr, "circle"),
        _PadBtn(wc, w, face_cx - 1.55, face_cy - fr / 2, fr, fr, "circle"),
        _PadBtn(ec, e, face_cx + 0.55, face_cy - fr / 2, fr, fr, "circle"),
        _PadBtn(sc, s, face_cx - fr / 2, face_cy + 0.55, fr, fr, "circle"),
    ]

    # System cluster
    btns += [
        _PadBtn("BTN_SELECT", st.select_label, 5.4, 3.35, 1.35, 0.55, "pill"),
        _PadBtn("BTN_START", st.start_label, 7.25, 3.35, 1.35, 0.55, "pill"),
        _PadBtn("BTN_MODE", st.guide_label, 6.35, 4.35, 1.3, 1.3, "circle"),
    ]
    return btns


_PAD_UNIT_W = 14.0
_PAD_UNIT_H = 8.4


class VisualGamepad(QWidget):
    """Painted mainstream gamepad (Xbox / Switch / PS / generic); auto-matched by device name."""

    keyPicked = Signal(str)
    bindRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(300)
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
        pad = 8
        avail_w = max(1.0, self.width() - pad * 2)
        avail_h = max(1.0, self.height() - tip_h - pad * 2)
        unit = min(avail_w / (_PAD_UNIT_W + 0.6), avail_h / (_PAD_UNIT_H + 0.5))
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
        # Prefer smaller / face buttons over stick wells when overlapping.
        hits = []
        for btn in self._buttons:
            if self._btn_rect(btn, ox, oy, unit).contains(pos):
                hits.append(btn)
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

        body = QRectF(ox + unit * 0.15, oy + unit * 1.55,
                      unit * (_PAD_UNIT_W - 0.3), unit * 6.5)
        case_grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        case_grad.setColorAt(0.0, QColor(st.plate))
        case_grad.setColorAt(1.0, QColor(st.case))
        painter.setPen(QPen(QColor(st.case_edge), 1.6))
        painter.setBrush(case_grad)
        painter.drawRoundedRect(body, unit * 1.35, unit * 1.35)

        # Grip cutouts (subtle)
        grip = QColor(st.case_edge)
        grip.setAlpha(55)
        painter.setPen(Qt.NoPen)
        painter.setBrush(grip)
        painter.drawEllipse(QRectF(body.left() - unit * 0.15, body.bottom() - unit * 2.2, unit * 2.4, unit * 2.6))
        painter.drawEllipse(QRectF(body.right() - unit * 2.25, body.bottom() - unit * 2.2, unit * 2.4, unit * 2.6))

        if st.brand_mark or self._brand_label:
            painter.setPen(QColor(st.accent))
            font = QFont(painter.font())
            font.setPixelSize(max(8, int(unit * 0.28)))
            font.setBold(True)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
            painter.setFont(font)
            painter.drawText(
                QRectF(body.left() + unit * 0.4, body.bottom() - unit * 0.55, body.width() * 0.5, unit * 0.4),
                Qt.AlignLeft | Qt.AlignVCenter, st.brand_mark or self._brand_label,
            )

        for btn in self._buttons:
            self._paint_btn(painter, btn, ox, oy, unit, st)

    def _paint_btn(self, painter: QPainter, btn: _PadBtn, ox: float, oy: float,
                   unit: float, st: GamepadStyle) -> None:
        rect = self._btn_rect(btn, ox, oy, unit)
        code = btn.code
        pressed = code in self._pressed
        armed = code == self._armed
        hover = code == self._hover
        bound = self._maps.get(code, "")

        side = QColor(st.button_side)
        face = QColor(st.button_top)
        body = QColor(st.button)
        if armed:
            face = QColor(st.armed)
            body = QColor(st.armed).darker(125)
            side = QColor(st.armed).darker(150)
        elif pressed:
            face = QColor(st.pressed)
            body = QColor(st.pressed).darker(115)
            side = QColor(st.pressed).darker(140)
        elif bound:
            tint = QColor(st.accent)
            face = QColor(
                min(255, face.red() + tint.red() // 8),
                min(255, face.green() + tint.green() // 8),
                min(255, face.blue() + tint.blue() // 8),
            )
        elif hover:
            face = QColor(face).lighter(110)

        painter.setPen(Qt.NoPen)
        painter.setBrush(side)
        if btn.kind in ("circle", "stick"):
            painter.drawEllipse(rect)
            face_rect = rect.adjusted(unit * 0.06, unit * 0.05, -unit * 0.06, -unit * 0.12)
            if pressed and not armed:
                face_rect.translate(0, unit * 0.04)
            if btn.kind == "stick":
                # Outer well
                painter.setBrush(QColor(st.stick_well))
                painter.drawEllipse(rect)
                well = rect.adjusted(unit * 0.18, unit * 0.18, -unit * 0.18, -unit * 0.18)
                painter.setBrush(QColor(st.stick_cap))
                painter.drawEllipse(well)
                # Live stick indicator
                is_left = code == "BTN_THUMBL"
                sx = self._lx if is_left else self._rx
                sy = self._ly if is_left else self._ry
                cx = well.center().x() + sx * unit * 0.35
                cy = well.center().y() + sy * unit * 0.35
                painter.setBrush(QColor(st.accent if pressed else st.pressed))
                painter.drawEllipse(QRectF(cx - unit * 0.18, cy - unit * 0.18, unit * 0.36, unit * 0.36))
                legend = QColor(st.legend_dim)
                painter.setPen(legend)
                font = QFont(painter.font())
                font.setPixelSize(max(7, int(unit * 0.22)))
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignHCenter | Qt.AlignBottom, btn.label)
                if bound and not armed:
                    painter.setPen(QColor(st.accent))
                    font.setBold(True)
                    font.setPixelSize(max(8, int(unit * 0.26)))
                    painter.setFont(font)
                    painter.drawText(rect.adjusted(0, unit * 0.15, 0, 0), Qt.AlignHCenter | Qt.AlignTop, bound[:6])
                if armed:
                    painter.setBrush(Qt.NoBrush)
                    glow = QColor(st.armed)
                    glow.setAlpha(180)
                    painter.setPen(QPen(glow, 3.0))
                    painter.drawEllipse(rect.adjusted(-1.5, -1.5, 1.5, 1.5))
                return
            grad = QLinearGradient(face_rect.topLeft(), face_rect.bottomLeft())
            grad.setColorAt(0.0, face)
            grad.setColorAt(1.0, body)
            painter.setBrush(grad)
            painter.setPen(QPen(QColor(st.armed if armed else st.case_edge), 2.2 if armed else 0.8))
            painter.drawEllipse(face_rect)
        else:
            radius = max(2.0, unit * (0.28 if btn.kind == "pill" else 0.18))
            painter.drawRoundedRect(rect, radius, radius)
            face_rect = rect.adjusted(unit * 0.04, unit * 0.03, -unit * 0.04, -unit * 0.10)
            if pressed and not armed:
                face_rect.translate(0, unit * 0.03)
            grad = QLinearGradient(face_rect.topLeft(), face_rect.bottomLeft())
            grad.setColorAt(0.0, face)
            grad.setColorAt(1.0, body)
            painter.setBrush(grad)
            painter.setPen(QPen(QColor(st.armed if armed else st.case_edge), 2.2 if armed else 0.8))
            painter.drawRoundedRect(face_rect, radius * 0.85, radius * 0.85)

        legend = QColor(st.legend)
        if armed:
            legend = QColor("#111111")
        elif pressed:
            legend = QColor("#FFFFFF") if QColor(st.pressed).lightness() < 160 else QColor("#111111")
        painter.setPen(legend)
        font = QFont(painter.font())
        text_rect = face_rect.adjusted(1, 1, -1, -1)
        if bound and not armed:
            font.setPixelSize(max(6, int(unit * 0.20)))
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(st.legend_dim))
            painter.drawText(
                QRectF(text_rect.left(), text_rect.top(), text_rect.width(), text_rect.height() * 0.42),
                Qt.AlignHCenter | Qt.AlignBottom, btn.label,
            )
            font.setPixelSize(max(7, int(unit * 0.28)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(st.accent))
            painter.drawText(
                QRectF(text_rect.left(), text_rect.center().y() - 1, text_rect.width(), text_rect.height() * 0.55),
                Qt.AlignHCenter | Qt.AlignTop, bound[:6],
            )
        else:
            px = max(7, int(unit * (0.36 if len(btn.label) <= 2 else 0.22)))
            font.setPixelSize(px)
            font.setBold(len(btn.label) <= 2)
            painter.setFont(font)
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, btn.label)

        if armed:
            painter.setBrush(Qt.NoBrush)
            glow = QColor(st.armed)
            glow.setAlpha(180)
            painter.setPen(QPen(glow, 3.0))
            if btn.kind in ("circle", "stick"):
                painter.drawEllipse(rect.adjusted(-1.5, -1.5, 1.5, 1.5))
            else:
                painter.drawRoundedRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5), unit * 0.2, unit * 0.2)


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
