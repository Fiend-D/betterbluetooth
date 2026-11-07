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
    gloss: str          # top-edge highlight on shell
    button: str
    button_top: str
    button_side: str
    legend: str
    legend_dim: str
    accent: str
    pressed: str
    armed: str
    stick_well: str
    stick_ring: str
    stick_cap: str
    dpad: str
    dpad_top: str
    brand_mark: str
    # Face labels in diamond order: north, west, east, south
    face_labels: tuple[str, str, str, str]
    face_codes: tuple[str, str, str, str]
    # Optional per-face accent (Xbox ABXY / PS symbols); empty = use button fill
    face_colors: tuple[str, str, str, str] = ("", "", "", "")
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
        case="#1C201C", case_edge="#0A0C0A", plate="#2A302A", gloss="#3A443A",
        button="#2A302C", button_top="#384038", button_side="#161A16",
        legend="#F2F5F2", legend_dim="#8A948A",
        accent="#107C10", pressed="#3DDC84", armed="#FFB020",
        stick_well="#0E120E", stick_ring="#1A221A", stick_cap="#2E362E",
        dpad="#222822", dpad_top="#2E362E",
        brand_mark="XBOX",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="",
    ),
    "switch": GamepadStyle(
        id="switch", label="Switch", layout="switch",
        case="#2A2C30", case_edge="#121318", plate="#3A3D44", gloss="#4A4E56",
        button="#F0F1F5", button_top="#FAFBFE", button_side="#C4C6CE",
        legend="#1A1C22", legend_dim="#6B7080",
        accent="#E60012", pressed="#FF6A6A", armed="#FFB020",
        stick_well="#16181C", stick_ring="#22252A", stick_cap="#3A3E46",
        dpad="#E8EAEF", dpad_top="#F5F6FA",
        brand_mark="NINTENDO",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("", "", "", ""),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="R", shoulder_r2="ZR",
        select_label="−", start_label="+", guide_label="⌂",
    ),
    "playstation": GamepadStyle(
        id="playstation", label="PlayStation", layout="playstation",
        case="#1A1A1C", case_edge="#08080A", plate="#2A2A2E", gloss="#3A3A40",
        button="#26262A", button_top="#323238", button_side="#141416",
        legend="#F5F5F7", legend_dim="#8E8E96",
        accent="#0070D1", pressed="#4DA3FF", armed="#FFB020",
        stick_well="#0C0C0E", stick_ring="#1A1A1E", stick_cap="#2E2E34",
        dpad="#222226", dpad_top="#303036",
        brand_mark="PS",
        face_labels=("△", "□", "○", "✕"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#1FAF66", "#D46AD0", "#E85A5A", "#6AA8E8"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Create", start_label="Options", guide_label="PS",
    ),
    "generic": GamepadStyle(
        id="generic", label="通用手柄", layout="generic",
        case="#2A2D32", case_edge="#14161A", plate="#3A3E45", gloss="#4A5058",
        button="#E8EAED", button_top="#F5F6F8", button_side="#C5C8CE",
        legend="#1F2328", legend_dim="#6B7280",
        accent="#4A9EFF", pressed="#7EC0FF", armed="#FFB020",
        stick_well="#1A1C20", stick_ring="#2A2E34", stick_cap="#4A505A",
        dpad="#E0E2E6", dpad_top="#F0F2F5",
        brand_mark="",
        face_labels=("X", "Y", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Select", start_label="Start", guide_label="Home",
    ),
    "8bitdo": GamepadStyle(
        id="8bitdo", label="8BitDo", layout="switch",
        case="#E8E4DA", case_edge="#B0AA9C", plate="#F4F0E6", gloss="#FFFCF4",
        button="#2A2824", button_top="#3A3732", button_side="#161410",
        legend="#F5F2EA", legend_dim="#A09888",
        accent="#C8102E", pressed="#F04460", armed="#E8A017",
        stick_well="#C8C2B4", stick_ring="#D8D2C4", stick_cap="#3A3732",
        dpad="#2A2824", dpad_top="#3A3732",
        brand_mark="8BitDo",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="R", shoulder_r2="ZR",
        select_label="Select", start_label="Start", guide_label="Home",
    ),
}

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
        "ns-pro",
    )),
    ("8bitdo", ("8bitdo", "8bit do", "ultimate bluetooth", "pro2", "sn30", "sf30")),
]


def detect_gamepad_style(device_name: str | None) -> GamepadStyle:
    text = (device_name or "").lower()
    for style_id, tokens in _BRAND_RULES:
        if any(tok in text for tok in tokens):
            return STYLES[style_id]
    return STYLES["generic"]
