"""Gamepad visual themes + face-button layouts matched by Bluetooth device name."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GamepadStyle:
    id: str
    label: str
    layout: str  # xbox | switch | playstation | generic
    case: str
    case_edge: str
    plate: str
    button: str
    button_top: str
    button_side: str
    legend: str
    legend_dim: str
    accent: str
    pressed: str
    armed: str
    stick_well: str
    stick_cap: str
    brand_mark: str
    # Face labels in diamond order: north, west, east, south
    face_labels: tuple[str, str, str, str]
    face_codes: tuple[str, str, str, str]
    # Shoulder / system labels
    shoulder_l: str = "LB"
    shoulder_l2: str = "LT"
    shoulder_r: str = "RB"
    shoulder_r2: str = "RT"
    select_label: str = "View"
    start_label: str = "Menu"
    guide_label: str = "Guide"


STYLES: dict[str, GamepadStyle] = {
    "xbox": GamepadStyle(
        id="xbox", label="Xbox", layout="xbox",
        case="#1A1D1A", case_edge="#0C0E0C", plate="#2A2F2A",
        button="#2E3430", button_top="#3A423C", button_side="#1C201C",
        legend="#F2F5F2", legend_dim="#8A948A",
        accent="#107C10", pressed="#3DDC84", armed="#FFB020",
        stick_well="#141814", stick_cap="#3A423C",
        brand_mark="XBOX",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="Xbox",
    ),
    "switch": GamepadStyle(
        id="switch", label="Switch", layout="switch",
        case="#2B2D31", case_edge="#15161A", plate="#3A3D44",
        button="#E8EAEF", button_top="#F5F6FA", button_side="#C8CAD2",
        legend="#1A1C22", legend_dim="#6B7080",
        accent="#E60012", pressed="#FF5A5A", armed="#FFB020",
        stick_well="#1A1C22", stick_cap="#4A4E58",
        brand_mark="NINTENDO",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="R", shoulder_r2="ZR",
        select_label="−", start_label="+", guide_label="Home",
    ),
    "playstation": GamepadStyle(
        id="playstation", label="PlayStation", layout="playstation",
        case="#1C1C1E", case_edge="#0A0A0C", plate="#2C2C30",
        button="#2A2A2E", button_top="#36363C", button_side="#18181C",
        legend="#F5F5F7", legend_dim="#8E8E96",
        accent="#0070D1", pressed="#4DA3FF", armed="#FFB020",
        stick_well="#121214", stick_cap="#3A3A40",
        brand_mark="PlayStation",
        face_labels=("△", "□", "○", "✕"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Create", start_label="Options", guide_label="PS",
    ),
    "generic": GamepadStyle(
        id="generic", label="通用手柄", layout="generic",
        case="#2A2D32", case_edge="#1A1C20", plate="#3A3E45",
        button="#E8EAED", button_top="#F5F6F8", button_side="#C5C8CE",
        legend="#1F2328", legend_dim="#6B7280",
        accent="#4A9EFF", pressed="#7EC0FF", armed="#FFB020",
        stick_well="#1A1C20", stick_cap="#4A505A",
        brand_mark="",
        face_labels=("X", "Y", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Select", start_label="Start", guide_label="Home",
    ),
    "8bitdo": GamepadStyle(
        id="8bitdo", label="8BitDo", layout="switch",
        case="#F0EEE8", case_edge="#B8B4A8", plate="#FAF8F2",
        button="#2C2A26", button_top="#3A3732", button_side="#1A1814",
        legend="#F5F2EA", legend_dim="#A09888",
        accent="#C8102E", pressed="#F04460", armed="#E8A017",
        stick_well="#D8D4C8", stick_cap="#4A4640",
        brand_mark="8BitDo",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="R", shoulder_r2="ZR",
        select_label="Select", start_label="Start", guide_label="Home",
    ),
}

# Longer / more specific tokens first.
_BRAND_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("xbox", (
        "xbox", "x-box", "xinput", "microsoft xbox", "xbox wireless",
        "xbox one", "xbox series", "gamepad for xbox",
    )),
    ("playstation", (
        "dualsense", "dualshock", "playstation", "sony interactive",
        "wireless controller", "ps5", "ps4", "ds4", "ds5",
    )),
    ("switch", (
        "joy-con", "joycon", "pro controller", "nintendo", "switch pro",
        "ns-pro", "hori",
    )),
    ("8bitdo", ("8bitdo", "8bit do", "ultimate bluetooth", "pro2", "sn30", "sf30")),
]


def detect_gamepad_style(device_name: str | None) -> GamepadStyle:
    text = (device_name or "").lower()
    for style_id, tokens in _BRAND_RULES:
        if any(tok in text for tok in tokens):
            return STYLES[style_id]
    return STYLES["generic"]
