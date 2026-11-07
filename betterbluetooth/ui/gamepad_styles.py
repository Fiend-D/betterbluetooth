"""Gamepad visual themes + face-button layouts matched by Bluetooth device name / model."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class GamepadStyle:
    id: str
    label: str
    layout: str  # xbox | switch | playstation | generic
    shell: str   # stick/dpad geometry: xbox | playstation | switch | joycon_l | joycon_r
    case: str
    case_edge: str
    plate: str
    gloss: str
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
    face_colors: tuple[str, str, str, str] = ("", "", "", "")
    shoulder_l: str = "LB"
    shoulder_l2: str = "LT"
    shoulder_r: str = "RB"
    shoulder_r2: str = "RT"
    select_label: str = "View"
    start_label: str = "Menu"
    guide_label: str = "Guide"
    # Back paddles / M keys: (code, label)
    extras: tuple[tuple[str, str], ...] = ()
    # Front micro-bumpers / 小肩键 (L4/R4), drawn near LB/RB
    bumpers: tuple[tuple[str, str], ...] = ()
    has_touchpad: bool = False
    has_capture: bool = False
    model_hint: str = ""


def _style(**kwargs) -> GamepadStyle:
    return GamepadStyle(**kwargs)


STYLES: dict[str, GamepadStyle] = {
    "xbox": _style(
        id="xbox", label="Xbox", layout="xbox", shell="xbox",
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
        extras=(("BTN_EXTRA1", "P1"), ("BTN_EXTRA2", "P2")),
        model_hint="Xbox / Series / Elite",
    ),
    "xbox_elite": _style(
        id="xbox_elite", label="Xbox Elite", layout="xbox", shell="xbox",
        case="#1A1C1A", case_edge="#080A08", plate="#282C28", gloss="#383C38",
        button="#2A302C", button_top="#384038", button_side="#161A16",
        legend="#F2F5F2", legend_dim="#8A948A",
        accent="#107C10", pressed="#3DDC84", armed="#FFB020",
        stick_well="#0E120E", stick_ring="#1A221A", stick_cap="#2E362E",
        dpad="#222822", dpad_top="#2E362E",
        brand_mark="ELITE",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="",
        extras=(("BTN_EXTRA1", "P1"), ("BTN_EXTRA2", "P2"),
                ("BTN_EXTRA3", "P3"), ("BTN_EXTRA4", "P4")),
        model_hint="Xbox Elite Series 2",
    ),
    "switch": _style(
        id="switch", label="Switch Pro", layout="switch", shell="switch",
        case="#2A2C30", case_edge="#121318", plate="#3A3D44", gloss="#4A4E56",
        button="#F0F1F5", button_top="#FAFBFE", button_side="#C4C6CE",
        legend="#1A1C22", legend_dim="#6B7080",
        accent="#E60012", pressed="#FF6A6A", armed="#FFB020",
        stick_well="#16181C", stick_ring="#22252A", stick_cap="#3A3E46",
        dpad="#E8EAEF", dpad_top="#F5F6FA",
        brand_mark="NINTENDO",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="R", shoulder_r2="ZR",
        select_label="−", start_label="+", guide_label="⌂",
        extras=(),
        has_capture=True,
        model_hint="Nintendo Switch Pro",
    ),
    "joycon_l": _style(
        id="joycon_l", label="Joy-Con (L)", layout="switch", shell="joycon_l",
        case="#00C3E3", case_edge="#0088A0", plate="#1AE0FF", gloss="#7AEEFF",
        button="#2A2C30", button_top="#3A3C40", button_side="#16181C",
        legend="#F5F6FA", legend_dim="#A0A4B0",
        accent="#00C3E3", pressed="#7AEEFF", armed="#FFB020",
        stick_well="#0088A0", stick_ring="#00A8C0", stick_cap="#2A2C30",
        dpad="#2A2C30", dpad_top="#3A3C40",
        brand_mark="L",
        face_labels=("", "", "", ""),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="SL", shoulder_r2="SR",
        select_label="−", start_label="", guide_label="📷",
        extras=(("BTN_EXTRA1", "SL"), ("BTN_EXTRA2", "SR")),
        has_capture=True,
        model_hint="Joy-Con Left",
    ),
    "joycon_r": _style(
        id="joycon_r", label="Joy-Con (R)", layout="switch", shell="joycon_r",
        case="#FF3C28", case_edge="#B02818", plate="#FF5A48", gloss="#FF8A7A",
        button="#2A2C30", button_top="#3A3C40", button_side="#16181C",
        legend="#F5F6FA", legend_dim="#A0A4B0",
        accent="#FF3C28", pressed="#FF8A7A", armed="#FFB020",
        stick_well="#B02818", stick_ring="#D03828", stick_cap="#2A2C30",
        dpad="#2A2C30", dpad_top="#3A3C40",
        brand_mark="R",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="SL", shoulder_l2="SR", shoulder_r="R", shoulder_r2="ZR",
        select_label="", start_label="+", guide_label="⌂",
        extras=(("BTN_EXTRA1", "SL"), ("BTN_EXTRA2", "SR")),
        model_hint="Joy-Con Right",
    ),
    "playstation": _style(
        id="playstation", label="DualSense", layout="playstation", shell="playstation",
        case="#1A1A1C", case_edge="#08080A", plate="#2A2A2E", gloss="#3A3A40",
        button="#26262A", button_top="#323238", button_side="#141416",
        legend="#F5F5F7", legend_dim="#8E8E96",
        accent="#0070D1", pressed="#4DA3FF", armed="#FFB020",
        stick_well="#0C0C0E", stick_ring="#1A1A1E", stick_cap="#2E2E34",
        dpad="#222226", dpad_top="#303036",
        brand_mark="PS5",
        face_labels=("△", "□", "○", "✕"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#1FAF66", "#D46AD0", "#E85A5A", "#6AA8E8"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Create", start_label="Options", guide_label="PS",
        extras=(("BTN_TOUCHPAD", "触控板"), ("BTN_EXTRA1", "静音")),
        has_touchpad=True,
        model_hint="DualSense / PS5",
    ),
    "dualshock": _style(
        id="dualshock", label="DualShock 4", layout="playstation", shell="playstation",
        case="#1A1A1C", case_edge="#08080A", plate="#2A2A2E", gloss="#3A3A40",
        button="#26262A", button_top="#323238", button_side="#141416",
        legend="#F5F5F7", legend_dim="#8E8E96",
        accent="#003087", pressed="#4DA3FF", armed="#FFB020",
        stick_well="#0C0C0E", stick_ring="#1A1A1E", stick_cap="#2E2E34",
        dpad="#222226", dpad_top="#303036",
        brand_mark="PS4",
        face_labels=("△", "□", "○", "✕"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#1FAF66", "#D46AD0", "#E85A5A", "#6AA8E8"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Share", start_label="Options", guide_label="PS",
        extras=(("BTN_TOUCHPAD", "触控板"),),
        has_touchpad=True,
        model_hint="DualShock 4",
    ),
    "8bitdo": _style(
        id="8bitdo", label="8BitDo", layout="switch", shell="switch",
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
        extras=(("BTN_EXTRA1", "★"), ("BTN_C", "C"), ("BTN_Z", "Z")),
        model_hint="8BitDo Pro / Ultimate",
    ),
    "gamesir": _style(
        id="gamesir", label="盖世小鸡", layout="xbox", shell="xbox",
        case="#1E2228", case_edge="#0C0E12", plate="#2A3038", gloss="#3A4450",
        button="#2A323C", button_top="#3A4450", button_side="#161A20",
        legend="#F2F5F8", legend_dim="#8A94A0",
        accent="#FF6A00", pressed="#FFA04A", armed="#FFB020",
        stick_well="#0E1218", stick_ring="#1A222A", stick_cap="#2E3640",
        dpad="#222830", dpad_top="#2E3640",
        brand_mark="GameSir",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="G",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2"),
                ("BTN_EXTRA3", "M3"), ("BTN_EXTRA4", "M4"),
                ("BTN_C", "C"), ("BTN_Z", "Z")),
        model_hint="盖世小鸡 GameSir",
    ),
    "gamesir_ps": _style(
        id="gamesir_ps", label="盖世小鸡 · 对称", layout="playstation", shell="playstation",
        case="#1E2228", case_edge="#0C0E12", plate="#2A3038", gloss="#3A4450",
        button="#2A323C", button_top="#3A4450", button_side="#161A20",
        legend="#F2F5F8", legend_dim="#8A94A0",
        accent="#FF6A00", pressed="#FFA04A", armed="#FFB020",
        stick_well="#0E1218", stick_ring="#1A222A", stick_cap="#2E3640",
        dpad="#222830", dpad_top="#2E3640",
        brand_mark="GameSir",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Select", start_label="Start", guide_label="G",
        extras=(("BTN_EXTRA1", "C1"), ("BTN_EXTRA2", "C2"),
                ("BTN_EXTRA3", "C3"), ("BTN_EXTRA4", "C4"),
                ("BTN_TOUCHPAD", "触控区")),
        has_touchpad=True,
        model_hint="GameSir Tarantula / 对称布局",
    ),
    "flydigi": _style(
        id="flydigi", label="飞智", layout="xbox", shell="xbox",
        case="#12141A", case_edge="#06080C", plate="#22262E", gloss="#323842",
        button="#2A3038", button_top="#3A4450", button_side="#14181E",
        legend="#F0F2F5", legend_dim="#8890A0",
        accent="#7C4DFF", pressed="#B388FF", armed="#FFB020",
        stick_well="#0A0C10", stick_ring="#1A1E26", stick_cap="#2E3440",
        dpad="#1E222A", dpad_top="#2A3038",
        brand_mark="Flydigi",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="Select", start_label="Start", guide_label="Home",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2"),
                ("BTN_EXTRA3", "M3"), ("BTN_EXTRA4", "M4"),
                ("BTN_C", "C"), ("BTN_Z", "Z")),
        model_hint="飞智 Vader / Apex",
    ),
    "betop": _style(
        id="betop", label="北通", layout="xbox", shell="xbox",
        case="#1A2030", case_edge="#0A1018", plate="#2A3448", gloss="#3A4860",
        button="#2A3448", button_top="#3A4860", button_side="#141C28",
        legend="#F0F4FA", legend_dim="#8898B0",
        accent="#1E88E5", pressed="#64B5F6", armed="#FFB020",
        stick_well="#0C121C", stick_ring="#1A2434", stick_cap="#2A3448",
        dpad="#222C3C", dpad_top="#2E3848",
        brand_mark="BETOP",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="Select", start_label="Start", guide_label="Home",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="北通 Betop",
    ),
    "gulikit": _style(
        id="gulikit", label="谷粒", layout="switch", shell="switch",
        case="#2A2C30", case_edge="#121318", plate="#3A3D44", gloss="#4A4E56",
        button="#F0F1F5", button_top="#FAFBFE", button_side="#C4C6CE",
        legend="#1A1C22", legend_dim="#6B7080",
        accent="#00B4A0", pressed="#40E0D0", armed="#FFB020",
        stick_well="#16181C", stick_ring="#22252A", stick_cap="#3A3E46",
        dpad="#E8EAEF", dpad_top="#F5F6FA",
        brand_mark="GuliKit",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="R", shoulder_r2="ZR",
        select_label="−", start_label="+", guide_label="⌂",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        has_capture=True,
        model_hint="谷粒 KingKong / NS",
    ),
    "pxn": _style(
        id="pxn", label="莱仕达", layout="xbox", shell="xbox",
        case="#1C1E24", case_edge="#0A0C10", plate="#2A2E38", gloss="#3A4050",
        button="#2A303C", button_top="#3A4454", button_side="#14181E",
        legend="#F2F4F8", legend_dim="#8890A0",
        accent="#E53935", pressed="#EF9A9A", armed="#FFB020",
        stick_well="#0E1016", stick_ring="#1A1E26", stick_cap="#2E3440",
        dpad="#222630", dpad_top="#2E3440",
        brand_mark="PXN",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="Select", start_label="Start", guide_label="Home",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="莱仕达 PXN",
    ),
    "iine": _style(
        id="iine", label="良值", layout="switch", shell="switch",
        case="#2A2C30", case_edge="#121318", plate="#3A3D44", gloss="#4A4E56",
        button="#F0F1F5", button_top="#FAFBFE", button_side="#C4C6CE",
        legend="#1A1C22", legend_dim="#6B7080",
        accent="#FF6F00", pressed="#FFB74D", armed="#FFB020",
        stick_well="#16181C", stick_ring="#22252A", stick_cap="#3A3E46",
        dpad="#E8EAEF", dpad_top="#F5F6FA",
        brand_mark="IINE",
        face_labels=("X", "Y", "A", "B"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L", shoulder_l2="ZL", shoulder_r="R", shoulder_r2="ZR",
        select_label="−", start_label="+", guide_label="⌂",
        extras=(("BTN_EXTRA1", "M"),),
        has_capture=True,
        model_hint="良值 IINE",
    ),
    # —— 山湾 ShanWan ——
    "shanwan_q34u2": _style(
        id="shanwan_q34u2", label="山湾 Q34U 二代", layout="xbox", shell="xbox",
        case="#1C2030", case_edge="#0A0E18", plate="#2A3448", gloss="#3A4860",
        button="#2A3448", button_top="#3A4860", button_side="#141C28",
        legend="#F0F4FA", legend_dim="#8898B0",
        accent="#FF7043", pressed="#FFAB91", armed="#FFB020",
        stick_well="#0C121C", stick_ring="#1A2434", stick_cap="#2A3448",
        dpad="#222C3C", dpad_top="#2E3848",
        brand_mark="Q34UⅡ",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        bumpers=(("BTN_EXTRA5", "L4"), ("BTN_EXTRA6", "R4")),
        model_hint="山湾 Q34U 二代 · 2背键+2小肩键",
    ),
    "shanwan_q34u": _style(
        id="shanwan_q34u", label="山湾 Q34U", layout="xbox", shell="xbox",
        case="#1C2030", case_edge="#0A0E18", plate="#2A3448", gloss="#3A4860",
        button="#2A3448", button_top="#3A4860", button_side="#141C28",
        legend="#F0F4FA", legend_dim="#8898B0",
        accent="#FF7043", pressed="#FFAB91", armed="#FFB020",
        stick_well="#0C121C", stick_ring="#1A2434", stick_cap="#2A3448",
        dpad="#222C3C", dpad_top="#2E3848",
        brand_mark="Q34U",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="山湾 Q34U · 2背键",
    ),
    "shanwan_q42": _style(
        id="shanwan_q42", label="山湾 Q42", layout="xbox", shell="xbox",
        case="#1C2030", case_edge="#0A0E18", plate="#2A3448", gloss="#3A4860",
        button="#2A3448", button_top="#3A4860", button_side="#141C28",
        legend="#F0F4FA", legend_dim="#8898B0",
        accent="#42A5F5", pressed="#90CAF9", armed="#FFB020",
        stick_well="#0C121C", stick_ring="#1A2434", stick_cap="#2A3448",
        dpad="#222C3C", dpad_top="#2E3848",
        brand_mark="Q42",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="山湾 Q42 / Q42XL",
    ),
    "shanwan": _style(
        id="shanwan", label="山湾", layout="xbox", shell="xbox",
        case="#1C2030", case_edge="#0A0E18", plate="#2A3448", gloss="#3A4860",
        button="#2A3448", button_top="#3A4860", button_side="#141C28",
        legend="#F0F4FA", legend_dim="#8898B0",
        accent="#FF7043", pressed="#FFAB91", armed="#FFB020",
        stick_well="#0C121C", stick_ring="#1A2434", stick_cap="#2A3448",
        dpad="#222C3C", dpad_top="#2E3848",
        brand_mark="ShanWan",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="山湾 ShanWan",
    ),
    "easysmx": _style(
        id="easysmx", label="易速马", layout="xbox", shell="xbox",
        case="#161820", case_edge="#080A10", plate="#262A34", gloss="#363C4A",
        button="#2A303C", button_top="#3A4454", button_side="#14181E",
        legend="#F2F4F8", legend_dim="#8890A0",
        accent="#00E676", pressed="#69F0AE", armed="#FFB020",
        stick_well="#0E1016", stick_ring="#1A1E26", stick_cap="#2E3440",
        dpad="#222630", dpad_top="#2E3440",
        brand_mark="EasySMX",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="LB", shoulder_l2="LT", shoulder_r="RB", shoulder_r2="RT",
        select_label="View", start_label="Menu", guide_label="",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2"),
                ("BTN_EXTRA3", "M3"), ("BTN_EXTRA4", "M4")),
        bumpers=(("BTN_EXTRA5", "L4"), ("BTN_EXTRA6", "R4")),
        model_hint="易速马 X20 / S05",
    ),
    "ipega": _style(
        id="ipega", label="iPega", layout="xbox", shell="xbox",
        case="#1A1C22", case_edge="#0A0C10", plate="#2A2E38", gloss="#3A4050",
        button="#2A303C", button_top="#3A4454", button_side="#14181E",
        legend="#F2F4F8", legend_dim="#8890A0",
        accent="#29B6F6", pressed="#81D4FA", armed="#FFB020",
        stick_well="#0E1016", stick_ring="#1A1E26", stick_cap="#2E3440",
        dpad="#222630", dpad_top="#2E3440",
        brand_mark="iPega",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        face_colors=("#C8A000", "#2D6BB8", "#C43C2E", "#2E8B2E"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Select", start_label="Start", guide_label="Home",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="iPega / 飞智兄弟款",
    ),
    "mocute": _style(
        id="mocute", label="魔卡特", layout="xbox", shell="xbox",
        case="#1A1C22", case_edge="#0A0C10", plate="#2A2E38", gloss="#3A4050",
        button="#2A303C", button_top="#3A4454", button_side="#14181E",
        legend="#F2F4F8", legend_dim="#8890A0",
        accent="#AB47BC", pressed="#CE93D8", armed="#FFB020",
        stick_well="#0E1016", stick_ring="#1A1E26", stick_cap="#2E3440",
        dpad="#222630", dpad_top="#2E3440",
        brand_mark="MOCUTE",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Select", start_label="Start", guide_label="Home",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="魔卡特 MOCUTE",
    ),
    "generic": _style(
        id="generic", label="通用手柄", layout="generic", shell="xbox",
        case="#2A2D32", case_edge="#14161A", plate="#3A3E45", gloss="#4A5058",
        button="#E8EAED", button_top="#F5F6F8", button_side="#C5C8CE",
        legend="#1F2328", legend_dim="#6B7280",
        accent="#4A9EFF", pressed="#7EC0FF", armed="#FFB020",
        stick_well="#1A1C20", stick_ring="#2A2E34", stick_cap="#4A505A",
        dpad="#E0E2E6", dpad_top="#F0F2F5",
        brand_mark="",
        face_labels=("Y", "X", "B", "A"),
        face_codes=("BTN_NORTH", "BTN_WEST", "BTN_EAST", "BTN_SOUTH"),
        shoulder_l="L1", shoulder_l2="L2", shoulder_r="R1", shoulder_r2="R2",
        select_label="Select", start_label="Start", guide_label="Home",
        extras=(("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2")),
        model_hint="通用 / 未知型号",
    ),
}


_P2 = (("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2"))
_P4 = (("BTN_EXTRA1", "M1"), ("BTN_EXTRA2", "M2"),
       ("BTN_EXTRA3", "M3"), ("BTN_EXTRA4", "M4"))
_P6 = _P4 + (("BTN_EXTRA5", "M5"), ("BTN_EXTRA6", "M6"))
_BUMP = (("BTN_EXTRA5", "L4"), ("BTN_EXTRA6", "R4"))
_CZ = (("BTN_C", "C"), ("BTN_Z", "Z"))


def _variant(base: str, **kw) -> GamepadStyle:
    return replace(STYLES[base], **kw)


def _register_model_variants() -> None:
    """Per-SKU overlays on brand bases (layout/extras differ by model line)."""
    specs: list[GamepadStyle] = [
        # —— Sony ——
        _variant("playstation", id="dualsense_edge", label="DualSense Edge",
                 brand_mark="EDGE", extras=_P4, has_touchpad=True,
                 model_hint="DualSense Edge · 背键"),
        # —— 盖世小鸡 GameSir（非对称 Xbox 系）——
        _variant("gamesir", id="gamesir_g7_pro", label="G7 Pro", brand_mark="G7 Pro",
                 extras=_P2, bumpers=(), model_hint="盖世小鸡 G7 Pro · Xbox授权"),
        _variant("gamesir", id="gamesir_g7_se", label="G7 SE", brand_mark="G7 SE",
                 extras=_P2, bumpers=(), model_hint="盖世小鸡 G7 SE · 可锁背键"),
        _variant("gamesir", id="gamesir_g7", label="G7", brand_mark="G7",
                 extras=_P2, bumpers=(), model_hint="盖世小鸡 G7"),
        _variant("gamesir", id="gamesir_nova", label="启明星", brand_mark="Nova",
                 extras=_P2, bumpers=_BUMP, model_hint="盖世小鸡 启明星 / 启明星2"),
        _variant("gamesir", id="gamesir_cyclone", label="风行者", brand_mark="Cyclone",
                 extras=_P2, bumpers=_BUMP, model_hint="盖世小鸡 风行者 / Cyclone"),
        _variant("gamesir", id="gamesir_kaleid", label="幻境", brand_mark="Kaleid",
                 extras=_P2, bumpers=(), model_hint="盖世小鸡 幻境 Kaleid / T4"),
        _variant("gamesir", id="gamesir_shadow", label="影舞者", brand_mark="影舞者",
                 extras=_P2, bumpers=(), model_hint="盖世小鸡 影舞者"),
        _variant("gamesir", id="gamesir_helios", label="天启", brand_mark="天启",
                 extras=_P2, bumpers=(), model_hint="盖世小鸡 天启"),
        _variant("gamesir", id="gamesir_uranus", label="天王星", brand_mark="天王星",
                 extras=_P4, bumpers=_BUMP, model_hint="盖世小鸡 天王星 8K"),
        _variant("gamesir", id="gamesir_supernova", label="超新星", brand_mark="超新星",
                 extras=_P2, bumpers=_BUMP, model_hint="盖世小鸡 超新星"),
        # 对称 / 九尾狐 / Tarantula：多宏键
        _variant("gamesir_ps", id="gamesir_tarantula", label="九尾狐", brand_mark="九尾狐",
                 extras=(("BTN_EXTRA1", "C1"), ("BTN_EXTRA2", "C2"),
                         ("BTN_EXTRA3", "C3"), ("BTN_EXTRA4", "C4"),
                         ("BTN_EXTRA5", "C5"), ("BTN_EXTRA6", "C6"),
                         *_CZ),
                 bumpers=(), has_touchpad=True,
                 model_hint="盖世小鸡 九尾狐 / Tarantula · 对称+宏键"),
        # —— 北通 Betop ——
        _variant("betop", id="betop_kunpeng70", label="鲲鹏70", brand_mark="鲲鹏70",
                 extras=_P6, bumpers=(), model_hint="北通 鲲鹏70 · 6拓展键"),
        _variant("betop", id="betop_kunpeng50", label="鲲鹏50", brand_mark="鲲鹏50",
                 extras=_P4, bumpers=(), model_hint="北通 鲲鹏50 · 4背键+智控屏"),
        _variant("betop", id="betop_kunpeng40", label="鲲鹏40", brand_mark="鲲鹏40",
                 extras=_P2, bumpers=(), model_hint="北通 鲲鹏40 / 星闪"),
        _variant("betop", id="betop_kunpeng20", label="鲲鹏20", brand_mark="鲲鹏20",
                 extras=_P2, bumpers=(), model_hint="北通 鲲鹏20"),
        _variant("betop", id="betop_zeus2", label="宙斯2", brand_mark="宙斯2",
                 extras=_P4, bumpers=_BUMP, model_hint="北通 宙斯2 光轴精英"),
        _variant("betop", id="betop_zeus", label="宙斯", brand_mark="宙斯",
                 extras=_P4, bumpers=(), model_hint="北通 宙斯 / 宙斯Pro"),
        _variant("betop", id="betop_asura3", label="阿修罗3", brand_mark="阿修罗3",
                 extras=_P2, bumpers=(), model_hint="北通 阿修罗3 / 3S"),
        _variant("betop", id="betop_asura2_mech", label="阿修罗2Pro 机械", brand_mark="机械",
                 extras=_P2, bumpers=(), model_hint="北通 阿修罗2Pro 机械版"),
        _variant("betop", id="betop_asura2", label="阿修罗2", brand_mark="阿修罗2",
                 extras=_P2, bumpers=(), model_hint="北通 阿修罗2 / 2Pro"),
        _variant("betop", id="betop_pangu", label="盘古", brand_mark="盘古",
                 extras=_P4, bumpers=_BUMP, model_hint="北通 盘古智控"),
        _variant("betop", id="betop_bat", label="蝙蝠", brand_mark="蝙蝠",
                 extras=(), bumpers=(), model_hint="北通 蝙蝠系列"),
        _variant("betop", id="betop_sparta", label="斯巴达", brand_mark="斯巴达",
                 extras=(), bumpers=(), model_hint="北通 斯巴达系列"),
        # —— 飞智 Flydigi ——
        _variant("flydigi", id="flydigi_apex5", label="八爪鱼5", brand_mark="APEX 5",
                 extras=_P4 + _CZ, bumpers=_BUMP,
                 model_hint="飞智 八爪鱼5 / Apex 5 · 4背键+2小肩"),
        _variant("flydigi", id="flydigi_apex4", label="八爪鱼4", brand_mark="APEX 4",
                 extras=_P4 + _CZ, bumpers=_BUMP,
                 model_hint="飞智 八爪鱼4 / Apex 4"),
        _variant("flydigi", id="flydigi_apex3", label="八爪鱼3", brand_mark="APEX 3",
                 extras=_P4 + _CZ, bumpers=_BUMP,
                 model_hint="飞智 八爪鱼3 / Apex 3"),
        _variant("flydigi", id="flydigi_apex", label="八爪鱼", brand_mark="APEX",
                 extras=_P4 + _CZ, bumpers=_BUMP,
                 model_hint="飞智 八爪鱼 / Apex"),
        _variant("flydigi", id="flydigi_vader5", label="Vader 5", brand_mark="Vader5",
                 extras=_P4, bumpers=_BUMP,
                 model_hint="飞智 Vader 5 / 5 Pro / 5S"),
        _variant("flydigi", id="flydigi_vader4", label="Vader 4", brand_mark="Vader4",
                 extras=_P4, bumpers=_BUMP,
                 model_hint="飞智 Vader 4 / 4 Pro"),
        _variant("flydigi", id="flydigi_vader3", label="Vader 3", brand_mark="Vader3",
                 extras=_P4, bumpers=_BUMP,
                 model_hint="飞智 Vader 3 / 3 Pro"),
        _variant("flydigi", id="flydigi_direwolf", label="冰原狼", brand_mark="Direwolf",
                 extras=_P2, bumpers=_BUMP,
                 model_hint="飞智 冰原狼 Direwolf"),
        # —— 机械师 Machenike ——
        _variant("gamesir", id="machenike_g6", label="机械师 G6", brand_mark="G6",
                 accent="#00BCD4", pressed="#4DD0E1",
                 extras=_P4, bumpers=_BUMP,
                 model_hint="机械师 G6 / G6 Pro"),
        _variant("gamesir", id="machenike_g5", label="机械师 G5", brand_mark="G5",
                 accent="#00BCD4", pressed="#4DD0E1",
                 extras=_P2, bumpers=(),
                 model_hint="机械师 G5 Pro / G5 Pro Max"),
        _variant("gamesir", id="machenike", label="机械师", brand_mark="Machenike",
                 accent="#00BCD4", pressed="#4DD0E1",
                 extras=_P2, bumpers=(),
                 model_hint="机械师 Machenike"),
    ]
    for s in specs:
        STYLES[s.id] = s


_register_model_variants()


# More specific rules first. Tokens matched as substrings of lowercased name.
_BRAND_RULES: list[tuple[str, tuple[str, ...]]] = [
    # 山湾
    ("shanwan_q34u2", (
        "q34u2", "q34u 2", "q34u二代", "q34u 二代", "q34uⅡ", "q34uⅱ",
        "shanwan q34u2", "山湾q34u2", "山弯q34u2",
        # D-mode BT alias; Q34U 二代 still advertises GamepadSpace-Q34U.
        "gamepadspace-q34u", "gamepadspace_q34u",
    )),
    ("shanwan_q34u", ("q34u", "q34u-8k", "shanwan q34", "山湾q34", "山弯q34")),
    ("shanwan_q42", ("q42xl", "q42", "shanwan q42", "山湾q42", "山弯q42")),
    ("shanwan", ("shanwan", "shan wan", "山湾", "山弯", "shootingplus", "gamepadspace")),
    # 盖世小鸡 — 具体型号优先
    ("gamesir_tarantula", (
        "tarantula", "九尾狐", "glyphswap",
    )),
    ("gamesir_ps", ("t3 pro",)),
    ("gamesir_uranus", ("天王星", "uranus")),
    ("gamesir_nova", ("启明星", "nova lite", "nova 2", "nova2", "启明星2")),
    ("gamesir_cyclone", ("cyclone", "风行者", "风行者2", "风行者pro")),
    ("gamesir_supernova", ("超新星", "supernova")),
    ("gamesir_kaleid", ("kaleid", "幻境", "t4 kaleid", "t4幻境")),
    ("gamesir_shadow", ("影舞者", "shadow dancer")),
    ("gamesir_helios", ("天启", "helios")),
    ("gamesir_g7_pro", ("g7 pro", "g7pro")),
    ("gamesir_g7_se", ("g7 se", "g7se")),
    ("gamesir_g7", ("g7",)),
    ("gamesir", (
        "gamesir", "盖世小鸡", "小鸡", "g8+", "g8 se", "x2s", "x2 pro", "x3 pro",
        "x3北极", "x5s", "x5 lite", "观星者", "灵狐",
    )),
    # 北通 — 具体型号优先（机械版单独）
    ("betop_asura2_mech", (
        "阿修罗2pro机械", "阿修罗2pro 机械", "asura 2pro mech", "asura2pro机械",
        "阿修罗2机械", "机械版", "无线机械", "多模机械",
    )),
    ("betop_kunpeng70", ("鲲鹏70", "kunpeng70", "kunpeng 70")),
    ("betop_kunpeng50", ("鲲鹏50", "kunpeng50", "kunpeng 50")),
    ("betop_kunpeng40", ("鲲鹏40", "kunpeng40", "kunpeng 40")),
    ("betop_kunpeng20", ("鲲鹏20", "kunpeng20", "kunpeng 20", "鲲鹏")),
    ("betop_zeus2", ("宙斯2", "zeus 2", "zeus2", "宙斯二")),
    ("betop_zeus", ("宙斯", "zeus")),
    ("betop_asura3", ("阿修罗3", "asura 3", "asura3", "阿修罗3s")),
    ("betop_asura2", ("阿修罗2", "asura 2", "asura2", "阿修罗2pro", "阿修罗")),
    ("betop_pangu", ("盘古", "pangu")),
    ("betop_bat", ("蝙蝠", "batop bat", "bd4", "bd2")),
    ("betop_sparta", ("斯巴达", "sparta")),
    ("betop", ("betop", "北通", "batop", "月影", "绝影", "幻影豹")),
    # 飞智
    ("flydigi_apex5", ("apex 5", "apex5", "八爪鱼5", "八爪鱼 5")),
    ("flydigi_apex4", ("apex 4", "apex4", "八爪鱼4", "八爪鱼 4")),
    ("flydigi_apex3", ("apex 3", "apex3", "八爪鱼3", "八爪鱼 3")),
    ("flydigi_apex", ("apex", "八爪鱼")),
    ("flydigi_vader5", ("vader 5", "vader5", "vader 5 pro", "vader5 pro", "vader 5s")),
    ("flydigi_vader4", ("vader 4", "vader4", "vader 4 pro", "vader4 pro")),
    ("flydigi_vader3", ("vader 3", "vader3", "vader 3 pro", "vader3 pro")),
    ("flydigi_direwolf", ("direwolf", "冰原狼")),
    ("flydigi", ("flydigi", "飞智", "vader")),
    # 机械师
    ("machenike_g6", ("g6 pro", "g6pro", "machenike g6", "机械师g6", "机械师 g6")),
    ("machenike_g5", ("g5 pro", "g5pro", "machenike g5", "机械师g5", "机械师 g5")),
    ("machenike", ("machenike", "机械师")),
    ("easysmx", ("easysmx", "easy smx", "易速马", "x20 pro", "x20pro", "s05 pro", "s05pro", "赤兔")),
    ("xbox_elite", ("xbox elite", "elite series", "elite 2", "elite2")),
    ("dualsense_edge", ("dualsense edge", "dual sense edge", "ds5 edge")),
    ("dualshock", ("dualshock", "ds4")),
    ("playstation", (
        "dualsense", "dual sense", "ps5", "sony interactive", "playstation",
    )),
    ("joycon_l", ("joy-con (l)", "joycon (l)", "joy-con left", "joycon left", "joy-con l")),
    ("joycon_r", ("joy-con (r)", "joycon (r)", "joy-con right", "joycon right", "joy-con r")),
    ("switch", (
        "pro controller", "nintendo", "switch pro", "ns-pro", "joy-con", "joycon",
    )),
    ("8bitdo", (
        "8bitdo", "8bit do", "八位堂", "ultimate bluetooth", "ultimate 2c",
        "ultimate 3", "pro 2", "pro2", "pro 3", "pro3", "sn30", "sf30",
    )),
    ("gulikit", ("gulikit", "谷粒", "kingkong", "kk3", "kk2")),
    ("pxn", ("pxn", "莱仕达", "p5", "p50", "9603")),
    ("iine", ("iine", "良值", "lianzhi")),
    ("ipega", ("ipega", "pg-")),
    ("mocute", ("mocute", "魔卡特")),
    ("xbox", (
        "xbox", "x-box", "xinput", "microsoft xbox", "xbox wireless",
        "xbox one", "xbox series", "gamepad for xbox",
    )),
]


# Brands/models that commonly advertise as "Xbox Wireless Controller" / 045E:02FD
# over Bluetooth X-Input mode. Battery is usually unreadable (same dead ends as
# real Xbox BT); layout must be chosen manually or via non-Xbox name hints.
XBOX_SPOOF_STYLE_IDS: frozenset[str] = frozenset({
    "shanwan_q34u2", "shanwan_q34u", "shanwan_q42", "shanwan",
    "gamesir", "gamesir_cyclone", "gamesir_g7", "gamesir_g7_se", "gamesir_g7_pro",
    "gamesir_nova", "gamesir_supernova", "gamesir_tarantula", "gamesir_uranus",
    "gamesir_kaleid", "gamesir_shadow", "gamesir_helios",
    "flydigi", "betop", "easysmx", "ipega", "mocute", "pxn",
})


def looks_like_xbox_spoof_name(device_name: str | None) -> bool:
    """True when the BT/HID name is a generic Xbox alias (no OEM model tokens)."""
    text = (device_name or "").lower().strip()
    if not text:
        return False
    for style_id, tokens in _BRAND_RULES:
        if style_id in ("xbox", "xbox_elite"):
            continue
        if any(tok in text for tok in tokens):
            return False
    xboxish = (
        "xbox wireless controller",
        "xbox bluetooth gamepad",
        "xbox controller",
        "wireless controller",
        "gamepad for xbox",
    )
    return any(x in text for x in xboxish) or text in ("xbox", "xinput")


def detect_gamepad_style(
    device_name: str | None,
    override_id: str | None = None,
) -> GamepadStyle:
    """Resolve layout. override_id wins (user picked real model under Xbox spoof name)."""
    oid = (override_id or "").strip()
    if oid and oid in STYLES:
        return STYLES[oid]
    text = (device_name or "").lower().strip()
    # Model-specific Chinese pads before generic Xbox spoof names.
    for style_id, tokens in _BRAND_RULES:
        if style_id == "xbox":
            continue
        if any(tok in text for tok in tokens):
            return STYLES.get(style_id, STYLES["generic"])
    if "xbox" in text or "xinput" in text or "x-box" in text:
        if "elite" in text:
            return STYLES["xbox_elite"]
        return STYLES["xbox"]
    # DualShock 4 often advertises only as "Wireless Controller".
    if text in ("wireless controller", "sony wireless controller"):
        return STYLES["dualshock"]
    return STYLES["generic"]


def selectable_pad_styles() -> list[tuple[str, str]]:
    """(style_id, label) for the manual model picker. '' = auto."""
    preferred = [
        "shanwan_q34u2", "shanwan_q34u", "shanwan_q42", "shanwan",
        "gamesir_cyclone", "gamesir_g7_pro", "gamesir_g7", "gamesir_tarantula",
        "gamesir_nova", "gamesir_supernova", "gamesir",
        "flydigi", "betop", "easysmx", "pxn", "ipega", "mocute",
        "8bitdo", "gulikit", "iine",
        "xbox", "xbox_elite", "playstation", "dualshock", "switch",
        "generic",
    ]
    out: list[tuple[str, str]] = [("", "自动识别")]
    seen: set[str] = set()
    for sid in preferred:
        st = STYLES.get(sid)
        if st is None or sid in seen:
            continue
        seen.add(sid)
        hint = st.model_hint or st.label
        out.append((sid, hint))
    for sid, st in STYLES.items():
        if sid in seen or sid == "generic":
            continue
        seen.add(sid)
        out.append((sid, st.model_hint or st.label))
    return out


def listed_models() -> list[str]:
    """Human-readable catalog for docs / debugging."""
    return sorted({s.model_hint or s.label for s in STYLES.values() if s.id != "generic"})


def shell_positions(shell: str) -> dict[str, tuple[float, float]]:
    """Control centers in Eden design coords (origin = pad center)."""
    if shell == "playstation":
        return {
            "lstick": (-55, 28), "rstick": (55, 28),
            "face": (108, -48), "dpad": (-108, -48),
            "select": (-48, -92), "start": (48, -92),
            "guide": (0, -28), "touchpad": (0, -72),
            "capture": (0, 0),
        }
    if shell == "xbox":
        return {
            "lstick": (-100, -42), "rstick": (58, 28),
            "face": (108, -42), "dpad": (-100, 38),
            "select": (-42, -82), "start": (42, -82),
            "guide": (0, -52), "touchpad": (0, 0),
            "capture": (0, 0),
        }
    if shell == "joycon_l":
        return {
            "lstick": (0, -40), "rstick": (0, 0),
            "face": (0, 0), "dpad": (0, 40),
            "select": (0, -90), "start": (0, 0),
            "guide": (0, -110), "touchpad": (0, 0),
            "capture": (0, -110),
        }
    if shell == "joycon_r":
        return {
            "lstick": (0, 40), "rstick": (0, 0),
            "face": (0, -40), "dpad": (0, 0),
            "select": (0, 0), "start": (0, -90),
            "guide": (0, -110), "touchpad": (0, 0),
            "capture": (0, 0),
        }
    # switch / default — Eden Pro geometry
    return {
        "lstick": (-111, -55), "rstick": (51, 0),
        "face": (105, -56), "dpad": (-61, 0),
        "select": (-50, -86), "start": (50, -86),
        "guide": (29, -56), "touchpad": (0, 0),
        "capture": (-29, -56),
    }
