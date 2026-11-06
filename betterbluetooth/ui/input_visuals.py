"""Eden-style visual keyboard / gamepad: central device art + surrounding bind chips."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from . import theme
from .keyboard_styles import KeyboardStyle, detect_style


class BindChip(QFrame):
    """Small Eden-like mapping box: title + current binding; click to rebind."""

    clicked = Signal(str)  # source code

    def __init__(self, code: str, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.code = code
        self._title = title
        self._bound = ""
        self._armed = False
        self._lit = 0.0
        self._anim = QPropertyAnimation(self, b"lit", self)
        self._anim.setDuration(100)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self.setMinimumWidth(72)
        self.setToolTip(f"{title}（{code}）— 点击后按下要映射到的键")

    def _get_lit(self) -> float:
        return self._lit

    def _set_lit(self, v: float) -> None:
        self._lit = v
        self.update()

    lit = Property(float, _get_lit, _set_lit)

    def set_bound(self, text: str) -> None:
        self._bound = text
        self.update()

    def set_armed(self, on: bool) -> None:
        self._armed = on
        self.update()

    def set_pressed(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._lit)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.code)
        super().mousePressEvent(e)

    def paintEvent(self, _e):  # noqa: N802
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(p.card)
        if self._lit > 0.01:
            acc = QColor(p.accent)
            acc.setAlpha(int(30 + 140 * self._lit))
            bg = acc
        painter.setBrush(bg)
        border = QColor(p.accent) if self._armed else QColor(p.border)
        painter.setPen(QPen(border, 2 if self._armed else 1))
        painter.drawRoundedRect(r, 5, 5)
        painter.setPen(QColor(p.secondary))
        font = QFont(painter.font())
        font.setPixelSize(9)
        painter.setFont(font)
        painter.drawText(QRectF(r.left(), r.top() + 2, r.width(), 12), Qt.AlignHCenter, self._title)
        painter.setPen(QColor(p.accent_text if self._lit > 0.5 else p.text))
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        shown = self._bound or ("…" if self._armed else "未设置")
        painter.drawText(QRectF(r.left(), r.top() + 14, r.width(), 18), Qt.AlignHCenter | Qt.AlignVCenter, shown)


# ---- Gamepad (Eden Pro-controller style) ----

# (code, title) for face / shoulders / etc.
_FACE = [("BTN_NORTH", "X"), ("BTN_WEST", "Y"), ("BTN_EAST", "B"), ("BTN_SOUTH", "A")]
_JC_FACE = [("JC_X", "X"), ("JC_Y", "Y"), ("JC_A", "A"), ("JC_B", "B")]


class VisualGamepad(QWidget):
    """Central Pro-style pad with bind chips around it; stick dots for live feedback."""

    keyPicked = Signal(str)          # source code clicked for remapping
    bindRequested = Signal(str)      # same — chip clicked

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(320)
        self._chips: dict[str, BindChip] = {}
        self._pressed: set[str] = set()
        self._lx = self._ly = self._rx = self._ry = 0.0
        self._armed: str | None = None

        root = QGridLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setHorizontalSpacing(6)
        root.setVerticalSpacing(6)

        # Row 0: shoulders
        root.addWidget(self._chip("BTN_TL2", "ZL"), 0, 0)
        root.addWidget(self._chip("BTN_TL", "L"), 0, 1)
        root.addWidget(self._chip("BTN_SELECT", "−"), 0, 3)
        root.addWidget(self._chip("BTN_START", "+"), 0, 4)
        root.addWidget(self._chip("BTN_TR", "R"), 0, 6)
        root.addWidget(self._chip("BTN_TR2", "ZR"), 0, 7)

        # Left stick cluster
        ls = QGridLayout()
        ls.addWidget(self._chip("BTN_DPAD_UP", "↑"), 0, 1)
        ls.addWidget(self._chip("BTN_DPAD_LEFT", "←"), 1, 0)
        ls.addWidget(self._chip("BTN_THUMBL", "L3"), 1, 1)
        ls.addWidget(self._chip("BTN_DPAD_RIGHT", "→"), 1, 2)
        ls.addWidget(self._chip("BTN_DPAD_DOWN", "↓"), 2, 1)
        root.addLayout(ls, 1, 0, 2, 2)

        # Center art
        self._art = _GamepadArt(self)
        root.addWidget(self._art, 1, 2, 2, 4)

        # Face buttons diamond
        face = QGridLayout()
        face.addWidget(self._chip("BTN_NORTH", "X"), 0, 1)
        face.addWidget(self._chip("BTN_WEST", "Y"), 1, 0)
        face.addWidget(self._chip("BTN_EAST", "B"), 1, 2)
        face.addWidget(self._chip("BTN_SOUTH", "A"), 2, 1)
        face.addWidget(self._chip("BTN_THUMBR", "R3"), 3, 1)
        root.addLayout(face, 1, 6, 2, 2)

        root.addWidget(self._chip("BTN_MODE", "Home"), 3, 3, 1, 2)

        # Joy-Con aliases share chips where titles overlap
        for jc, btn in (
            ("JC_ZL", "BTN_TL2"), ("JC_L", "BTN_TL"), ("JC_ZR", "BTN_TR2"), ("JC_R", "BTN_TR"),
            ("JC_MINUS", "BTN_SELECT"), ("JC_PLUS", "BTN_START"), ("JC_HOME", "BTN_MODE"),
            ("JC_UP", "BTN_DPAD_UP"), ("JC_DOWN", "BTN_DPAD_DOWN"),
            ("JC_LEFT", "BTN_DPAD_LEFT"), ("JC_RIGHT", "BTN_DPAD_RIGHT"),
            ("JC_L_STICK", "BTN_THUMBL"), ("JC_R_STICK", "BTN_THUMBR"),
            ("JC_X", "BTN_NORTH"), ("JC_Y", "BTN_WEST"), ("JC_A", "BTN_EAST"), ("JC_B", "BTN_SOUTH"),
        ):
            if btn in self._chips:
                self._chips[jc] = self._chips[btn]

        tip = QLabel("点击映射框后，按下要映射到的键；再点同一框可取消等待。实体按键会高亮。")
        tip.setWordWrap(True)
        tip.setProperty("role", "secondary")
        root.addWidget(tip, 4, 0, 1, 8)

    def _chip(self, code: str, title: str) -> BindChip:
        chip = BindChip(code, title)
        chip.clicked.connect(self._on_chip)
        self._chips[code] = chip
        return chip

    def _on_chip(self, code: str) -> None:
        self.bindRequested.emit(code)
        # keyPicked kept for API compat; InputPage only listens to bindRequested.

    def set_button(self, code: str, pressed: bool) -> None:
        # Normalize Joy-Con codes onto shared chips for lighting
        chip = self._chips.get(code)
        if chip:
            chip.set_pressed(pressed)
        if pressed:
            self._pressed.add(code)
        else:
            self._pressed.discard(code)
        self._art.set_pressed(self._pressed)
        # crude stick nudge when stick-click held
        if code in ("BTN_THUMBL", "JC_L_STICK"):
            self._art.set_sticks(0.3 if pressed else self._lx, self._ly, self._rx, self._ry)
        if code in ("BTN_THUMBR", "JC_R_STICK"):
            self._art.set_sticks(self._lx, self._ly, 0.3 if pressed else self._rx, self._ry)

    def set_stick(self, left: bool, x: float, y: float) -> None:
        if left:
            self._lx, self._ly = x, y
        else:
            self._rx, self._ry = x, y
        self._art.set_sticks(self._lx, self._ly, self._rx, self._ry)

    def set_mappings(self, maps: dict[str, str]) -> None:
        for code, chip in self._chips.items():
            if code.startswith("JC_"):
                continue
            chip.set_bound(maps.get(code, ""))

    def set_armed(self, code: str | None) -> None:
        self._armed = code
        for c, chip in self._chips.items():
            if c.startswith("JC_"):
                continue
            chip.set_armed(c == code)

    def clear_pressed(self) -> None:
        self._pressed.clear()
        for code, chip in self._chips.items():
            if not code.startswith("JC_"):
                chip.set_pressed(False)
        self._lx = self._ly = self._rx = self._ry = 0.0
        self._art.set_pressed(set())
        self._art.set_sticks(0, 0, 0, 0)


class _GamepadArt(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 140)
        self._pressed: set[str] = set()
        self._lx = self._ly = self._rx = self._ry = 0.0

    def set_pressed(self, pressed: set[str]) -> None:
        self._pressed = set(pressed)
        self.update()

    def set_sticks(self, lx, ly, rx, ry) -> None:
        self._lx, self._ly, self._rx, self._ry = lx, ly, rx, ry
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        body = QRectF(w * 0.08, h * 0.22, w * 0.84, h * 0.56)
        painter.setPen(QPen(QColor(p.border), 1.5))
        painter.setBrush(QColor(p.card_hover))
        painter.drawRoundedRect(body, 36, 36)
        # sticks with green Eden-style dots
        self._stick(painter, w * 0.30, h * 0.58, self._lx, self._ly)
        self._stick(painter, w * 0.70, h * 0.58, self._rx, self._ry)
        # face markers
        for code, nx, ny in (
            ("BTN_NORTH", 0.72, 0.32), ("BTN_SOUTH", 0.72, 0.52),
            ("BTN_WEST", 0.62, 0.42), ("BTN_EAST", 0.82, 0.42),
        ):
            on = code in self._pressed or any(c.endswith(code.split("_")[-1]) and c.startswith("JC_") for c in self._pressed)
            # simpler: also check JC aliases manually
            aliases = {"BTN_NORTH": "JC_X", "BTN_SOUTH": "JC_B", "BTN_WEST": "JC_Y", "BTN_EAST": "JC_A"}
            on = code in self._pressed or aliases.get(code, "") in self._pressed
            painter.setBrush(QColor(p.accent) if on else QColor(p.card))
            painter.setPen(QPen(QColor(p.border), 1))
            painter.drawEllipse(QRectF(w * nx - 8, h * ny - 8, 16, 16))

    def _stick(self, painter, cx, cy, x, y) -> None:
        p = theme.palette()
        painter.setPen(QPen(QColor(p.border), 1))
        painter.setBrush(QColor(p.card))
        painter.drawEllipse(QRectF(cx - 22, cy - 22, 44, 44))
        # Eden green dot
        green = QColor("#3DDC84")
        painter.setBrush(green)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx + x * 12 - 5, cy + y * 12 - 5, 10, 10))


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
