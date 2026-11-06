"""Portable input codes shared by Linux (evdev) and Windows (VK / usage)."""
from __future__ import annotations

# Linux KEY_* name → Windows virtual-key code (subset used for remapping / presets).
KEY_TO_VK: dict[str, int] = {
    "KEY_A": 0x41, "KEY_B": 0x42, "KEY_C": 0x43, "KEY_D": 0x44, "KEY_E": 0x45,
    "KEY_F": 0x46, "KEY_G": 0x47, "KEY_H": 0x48, "KEY_I": 0x49, "KEY_J": 0x4A,
    "KEY_K": 0x4B, "KEY_L": 0x4C, "KEY_M": 0x4D, "KEY_N": 0x4E, "KEY_O": 0x4F,
    "KEY_P": 0x50, "KEY_Q": 0x51, "KEY_R": 0x52, "KEY_S": 0x53, "KEY_T": 0x54,
    "KEY_U": 0x55, "KEY_V": 0x56, "KEY_W": 0x57, "KEY_X": 0x58, "KEY_Y": 0x59,
    "KEY_Z": 0x5A,
    "KEY_1": 0x31, "KEY_2": 0x32, "KEY_3": 0x33, "KEY_4": 0x34, "KEY_5": 0x35,
    "KEY_6": 0x36, "KEY_7": 0x37, "KEY_8": 0x38, "KEY_9": 0x39, "KEY_0": 0x30,
    "KEY_ENTER": 0x0D, "KEY_ESC": 0x1B, "KEY_BACKSPACE": 0x08, "KEY_TAB": 0x09,
    "KEY_SPACE": 0x20, "KEY_MINUS": 0xBD, "KEY_EQUAL": 0xBB, "KEY_LEFTBRACE": 0xDB,
    "KEY_RIGHTBRACE": 0xDD, "KEY_BACKSLASH": 0xDC, "KEY_SEMICOLON": 0xBA,
    "KEY_APOSTROPHE": 0xDE, "KEY_GRAVE": 0xC0, "KEY_COMMA": 0xBC, "KEY_DOT": 0xBE,
    "KEY_SLASH": 0xBF, "KEY_CAPSLOCK": 0x14,
    "KEY_F1": 0x70, "KEY_F2": 0x71, "KEY_F3": 0x72, "KEY_F4": 0x73,
    "KEY_F5": 0x74, "KEY_F6": 0x75, "KEY_F7": 0x76, "KEY_F8": 0x77,
    "KEY_F9": 0x78, "KEY_F10": 0x79, "KEY_F11": 0x7A, "KEY_F12": 0x7B,
    "KEY_LEFTCTRL": 0xA2, "KEY_LEFTSHIFT": 0xA0, "KEY_LEFTALT": 0xA4, "KEY_LEFTMETA": 0x5B,
    "KEY_RIGHTCTRL": 0xA3, "KEY_RIGHTSHIFT": 0xA1, "KEY_RIGHTALT": 0xA5, "KEY_RIGHTMETA": 0x5C,
    "KEY_UP": 0x26, "KEY_DOWN": 0x28, "KEY_LEFT": 0x25, "KEY_RIGHT": 0x27,
    "KEY_INSERT": 0x2D, "KEY_DELETE": 0x2E, "KEY_HOME": 0x24, "KEY_END": 0x23,
    "KEY_PAGEUP": 0x21, "KEY_PAGEDOWN": 0x22,
    "KEY_NUMLOCK": 0x90, "KEY_SCROLLLOCK": 0x91, "KEY_PAUSE": 0x13, "KEY_SYSRQ": 0x2C,
    "KEY_KP0": 0x60, "KEY_KP1": 0x61, "KEY_KP2": 0x62, "KEY_KP3": 0x63, "KEY_KP4": 0x64,
    "KEY_KP5": 0x65, "KEY_KP6": 0x66, "KEY_KP7": 0x67, "KEY_KP8": 0x68, "KEY_KP9": 0x69,
    "KEY_KPDOT": 0x6E, "KEY_KPPLUS": 0x6B, "KEY_KPMINUS": 0x6D, "KEY_KPASTERISK": 0x6A,
    "KEY_KPSLASH": 0x6F, "KEY_KPENTER": 0x0D, "KEY_COMPOSE": 0x5D,
}

VK_TO_KEY: dict[int, str] = {v: k for k, v in KEY_TO_VK.items()}

# Display labels for common keys / buttons.
LABELS: dict[str, str] = {
    "KEY_LEFTCTRL": "Left Ctrl", "KEY_RIGHTCTRL": "Right Ctrl",
    "KEY_LEFTSHIFT": "Left Shift", "KEY_RIGHTSHIFT": "Right Shift",
    "KEY_LEFTALT": "Left Alt", "KEY_RIGHTALT": "Right Alt",
    "KEY_LEFTMETA": "Win / Meta", "KEY_RIGHTMETA": "Right Meta",
    "KEY_CAPSLOCK": "Caps Lock", "KEY_ENTER": "Enter", "KEY_ESC": "Esc",
    "KEY_BACKSPACE": "Backspace", "KEY_TAB": "Tab", "KEY_SPACE": "Space",
    "KEY_UP": "↑", "KEY_DOWN": "↓", "KEY_LEFT": "←", "KEY_RIGHT": "→",
    "BTN_SOUTH": "A / Cross", "BTN_EAST": "B / Circle", "BTN_NORTH": "X / Triangle",
    "BTN_WEST": "Y / Square", "BTN_TL": "L1 / LB", "BTN_TR": "R1 / RB",
    "BTN_TL2": "L2 / LT", "BTN_TR2": "R2 / RT", "BTN_SELECT": "Select / −",
    "BTN_START": "Start / +", "BTN_MODE": "Guide / Home", "BTN_THUMBL": "L3",
    "BTN_THUMBR": "R3", "BTN_DPAD_UP": "D-Pad ↑", "BTN_DPAD_DOWN": "D-Pad ↓",
    "BTN_DPAD_LEFT": "D-Pad ←", "BTN_DPAD_RIGHT": "D-Pad →",
    "JC_A": "A", "JC_B": "B", "JC_X": "X", "JC_Y": "Y",
    "JC_L": "L", "JC_R": "R", "JC_ZL": "ZL", "JC_ZR": "ZR",
    "JC_MINUS": "−", "JC_PLUS": "+", "JC_HOME": "Home", "JC_CAPTURE": "Capture",
    "JC_L_STICK": "L Stick", "JC_R_STICK": "R Stick",
    "JC_UP": "↑", "JC_DOWN": "↓", "JC_LEFT": "←", "JC_RIGHT": "→",
    "JC_SL": "SL", "JC_SR": "SR",
}


# Qt.Key_* → portable KEY_* (for in-panel keyboard grab testing).
QT_KEY_TO_CODE: dict[int, str] = {}


def _init_qt_map() -> None:
    if QT_KEY_TO_CODE:
        return
    try:
        from PySide6.QtCore import Qt
    except ImportError:
        return
    mapping = {
        Qt.Key_Escape: "KEY_ESC", Qt.Key_Tab: "KEY_TAB", Qt.Key_Backspace: "KEY_BACKSPACE",
        Qt.Key_Return: "KEY_ENTER", Qt.Key_Enter: "KEY_KPENTER", Qt.Key_Space: "KEY_SPACE",
        Qt.Key_CapsLock: "KEY_CAPSLOCK",
        Qt.Key_Shift: "KEY_LEFTSHIFT", Qt.Key_Control: "KEY_LEFTCTRL",
        Qt.Key_Alt: "KEY_LEFTALT", Qt.Key_Meta: "KEY_LEFTMETA",
        Qt.Key_Up: "KEY_UP", Qt.Key_Down: "KEY_DOWN", Qt.Key_Left: "KEY_LEFT", Qt.Key_Right: "KEY_RIGHT",
        Qt.Key_Insert: "KEY_INSERT", Qt.Key_Delete: "KEY_DELETE",
        Qt.Key_Home: "KEY_HOME", Qt.Key_End: "KEY_END",
        Qt.Key_PageUp: "KEY_PAGEUP", Qt.Key_PageDown: "KEY_PAGEDOWN",
        Qt.Key_Minus: "KEY_MINUS", Qt.Key_Equal: "KEY_EQUAL",
        Qt.Key_BracketLeft: "KEY_LEFTBRACE", Qt.Key_BracketRight: "KEY_RIGHTBRACE",
        Qt.Key_Backslash: "KEY_BACKSLASH", Qt.Key_Semicolon: "KEY_SEMICOLON",
        Qt.Key_Apostrophe: "KEY_APOSTROPHE", Qt.Key_QuoteLeft: "KEY_GRAVE",
        Qt.Key_Comma: "KEY_COMMA", Qt.Key_Period: "KEY_DOT", Qt.Key_Slash: "KEY_SLASH",
        Qt.Key_Print: "KEY_SYSRQ", Qt.Key_ScrollLock: "KEY_SCROLLLOCK",
        Qt.Key_Pause: "KEY_PAUSE", Qt.Key_NumLock: "KEY_NUMLOCK",
        Qt.Key_Menu: "KEY_COMPOSE",
    }
    app_key = getattr(Qt, "Key_ApplicationLeft", None)
    if app_key is not None:
        mapping[app_key] = "KEY_COMPOSE"
    for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        mapping[getattr(Qt, f"Key_{ch}")] = f"KEY_{ch}"
    for i in range(10):
        mapping[getattr(Qt, f"Key_{i}")] = f"KEY_{i}"
    for i in range(1, 13):
        mapping[getattr(Qt, f"Key_F{i}")] = f"KEY_F{i}"
    QT_KEY_TO_CODE.update({int(k): v for k, v in mapping.items()})


_QT_KEYPAD: dict[int, str] = {}


def _init_qt_keypad() -> None:
    if _QT_KEYPAD:
        return
    try:
        from PySide6.QtCore import Qt
    except ImportError:
        return
    _QT_KEYPAD.update({
        int(Qt.Key_0): "KEY_KP0", int(Qt.Key_1): "KEY_KP1", int(Qt.Key_2): "KEY_KP2",
        int(Qt.Key_3): "KEY_KP3", int(Qt.Key_4): "KEY_KP4", int(Qt.Key_5): "KEY_KP5",
        int(Qt.Key_6): "KEY_KP6", int(Qt.Key_7): "KEY_KP7", int(Qt.Key_8): "KEY_KP8",
        int(Qt.Key_9): "KEY_KP9", int(Qt.Key_Period): "KEY_KPDOT",
        int(Qt.Key_Plus): "KEY_KPPLUS", int(Qt.Key_Minus): "KEY_KPMINUS",
        int(Qt.Key_Asterisk): "KEY_KPASTERISK", int(Qt.Key_Slash): "KEY_KPSLASH",
        int(Qt.Key_Enter): "KEY_KPENTER", int(Qt.Key_Equal): "KEY_KPEQUAL",
    })


def qt_key_to_code(qt_key: int, modifiers: int = 0) -> str | None:
    _init_qt_map()
    try:
        from PySide6.QtCore import Qt
        if (modifiers or 0) & Qt.KeypadModifier:
            _init_qt_keypad()
            code = _QT_KEYPAD.get(int(qt_key))
            if code:
                return code
    except (ImportError, TypeError):
        pass
    return QT_KEY_TO_CODE.get(int(qt_key))


def label(code: str) -> str:
    if code in LABELS:
        return LABELS[code]
    if code.startswith("KEY_"):
        return code[4:].replace("LEFT", "L ").replace("RIGHT", "R ").title()
    return code


# Built-in keyboard remodel presets: list of (from, to) ; to=None means suppress.
PRESETS: dict[str, tuple[str, list[tuple[str, str | None]]]] = {
    "swap_caps_ctrl": ("互换 Caps Lock 与 Left Ctrl", [
        ("KEY_CAPSLOCK", "KEY_LEFTCTRL"),
        ("KEY_LEFTCTRL", "KEY_CAPSLOCK"),
    ]),
    "caps_as_esc": ("Caps Lock → Esc", [("KEY_CAPSLOCK", "KEY_ESC")]),
    "swap_alt_meta": ("互换 Left Alt 与 Win", [
        ("KEY_LEFTALT", "KEY_LEFTMETA"),
        ("KEY_LEFTMETA", "KEY_LEFTALT"),
    ]),
    "disable_win": ("禁用 Win 键", [
        ("KEY_LEFTMETA", None),
        ("KEY_RIGHTMETA", None),
    ]),
}
