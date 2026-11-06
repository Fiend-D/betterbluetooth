"""Built-in full-size keyboard visual themes matched by Bluetooth device name."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyboardStyle:
    id: str
    label: str
    # Chassis / plate
    case: str
    case_edge: str
    plate: str
    # Keycaps
    keycap: str
    keycap_top: str          # lighter face (sculpted look)
    keycap_side: str         # darker bottom edge
    legend: str
    legend_dim: str
    # Special / modifier keycaps (often darker)
    mod_keycap: str
    mod_keycap_top: str
    mod_legend: str
    # Accent (logo strip / armed / pressed glow)
    accent: str
    pressed: str
    armed: str
    bound_dot: str
    brand_mark: str          # short badge text drawn on case


STYLES: dict[str, KeyboardStyle] = {
    "default": KeyboardStyle(
        id="default", label="通用",
        case="#2A2D32", case_edge="#1A1C20", plate="#3A3E45",
        keycap="#E8EAED", keycap_top="#F5F6F8", keycap_side="#C5C8CE",
        legend="#1F2328", legend_dim="#6B7280",
        mod_keycap="#3D424A", mod_keycap_top="#4A505A", mod_legend="#E8EAED",
        accent="#4A9EFF", pressed="#7EC0FF", armed="#FFB020", bound_dot="#4A9EFF",
        brand_mark="",
    ),
    "logitech": KeyboardStyle(
        id="logitech", label="Logitech",
        case="#1B1B1F", case_edge="#0E0E10", plate="#2A2A30",
        keycap="#2E2E34", keycap_top="#3A3A42", keycap_side="#1C1C20",
        legend="#F2F2F4", legend_dim="#9A9AA3",
        mod_keycap="#222228", mod_keycap_top="#2C2C34", mod_legend="#F2F2F4",
        accent="#00B8FC", pressed="#5AD4FF", armed="#00B8FC", bound_dot="#00B8FC",
        brand_mark="LOGITECH",
    ),
    "razer": KeyboardStyle(
        id="razer", label="Razer",
        case="#0D0F0D", case_edge="#050605", plate="#1A1F1A",
        keycap="#1C211C", keycap_top="#262C26", keycap_side="#0E120E",
        legend="#E8FFE8", legend_dim="#6A9A6A",
        mod_keycap="#141814", mod_keycap_top="#1C221C", mod_legend="#E8FFE8",
        accent="#44D62C", pressed="#7CFF66", armed="#44D62C", bound_dot="#44D62C",
        brand_mark="RAZER",
    ),
    "corsair": KeyboardStyle(
        id="corsair", label="Corsair",
        case="#12151A", case_edge="#080A0D", plate="#1E242C",
        keycap="#232A33", keycap_top="#2E3640", keycap_side="#14181E",
        legend="#F5F7FA", legend_dim="#8B95A3",
        mod_keycap="#1A2028", mod_keycap_top="#242C36", mod_legend="#F5F7FA",
        accent="#FFD200", pressed="#FFE566", armed="#FFD200", bound_dot="#FFD200",
        brand_mark="CORSAIR",
    ),
    "keychron": KeyboardStyle(
        id="keychron", label="Keychron",
        case="#C8CDD4", case_edge="#9AA1AB", plate="#D8DCE2",
        keycap="#F4F1EA", keycap_top="#FFFCF6", keycap_side="#D5D0C4",
        legend="#2B2F36", legend_dim="#7A808A",
        mod_keycap="#3C4450", mod_keycap_top="#4A5360", mod_legend="#F4F1EA",
        accent="#E85D04", pressed="#FF8A3D", armed="#E85D04", bound_dot="#E85D04",
        brand_mark="KEYCHRON",
    ),
    "apple": KeyboardStyle(
        id="apple", label="Apple",
        case="#C5C5C7", case_edge="#9E9EA0", plate="#D8D8DA",
        keycap="#FBFBFC", keycap_top="#FFFFFF", keycap_side="#D0D0D4",
        legend="#1D1D1F", legend_dim="#6E6E73",
        mod_keycap="#E8E8EA", mod_keycap_top="#F2F2F4", mod_legend="#1D1D1F",
        accent="#0071E3", pressed="#4DA3FF", armed="#0071E3", bound_dot="#0071E3",
        brand_mark="",
    ),
    "microsoft": KeyboardStyle(
        id="microsoft", label="Microsoft",
        case="#2B2B2B", case_edge="#151515", plate="#3A3A3A",
        keycap="#F3F3F3", keycap_top="#FAFAFA", keycap_side="#D0D0D0",
        legend="#1A1A1A", legend_dim="#6B6B6B",
        mod_keycap="#2F2F2F", mod_keycap_top="#3C3C3C", mod_legend="#F3F3F3",
        accent="#00A4EF", pressed="#5CC8FF", armed="#7FBA00", bound_dot="#00A4EF",
        brand_mark="MICROSOFT",
    ),
    "steelseries": KeyboardStyle(
        id="steelseries", label="SteelSeries",
        case="#161616", case_edge="#080808", plate="#222222",
        keycap="#2A2A2A", keycap_top="#353535", keycap_side="#181818",
        legend="#F0F0F0", legend_dim="#888888",
        mod_keycap="#202020", mod_keycap_top="#2C2C2C", mod_legend="#F0F0F0",
        accent="#FF6400", pressed="#FF944D", armed="#FF6400", bound_dot="#FF6400",
        brand_mark="STEELSERIES",
    ),
    "hyperx": KeyboardStyle(
        id="hyperx", label="HyperX",
        case="#1A1214", case_edge="#0C0809", plate="#2A1C20",
        keycap="#2A2226", keycap_top="#362A30", keycap_side="#181014",
        legend="#FFF0F3", legend_dim="#A08088",
        mod_keycap="#20181C", mod_keycap_top="#2C2228", mod_legend="#FFF0F3",
        accent="#E31C25", pressed="#FF5A60", armed="#E31C25", bound_dot="#E31C25",
        brand_mark="HYPERX",
    ),
    "nuphy": KeyboardStyle(
        id="nuphy", label="NuPhy",
        case="#E6E2DA", case_edge="#B8B2A6", plate="#F0ECE4",
        keycap="#FFFDF8", keycap_top="#FFFFFF", keycap_side="#E0DCD2",
        legend="#2C2A26", legend_dim="#8A857A",
        mod_keycap="#5B6C5D", mod_keycap_top="#6B7D6E", mod_legend="#FFFDF8",
        accent="#6B8F71", pressed="#9BC4A0", armed="#C4A35A", bound_dot="#6B8F71",
        brand_mark="NUPHY",
    ),
    "ikbc": KeyboardStyle(
        id="ikbc", label="iKBC",
        case="#2C3036", case_edge="#181A1E", plate="#3C424A",
        keycap="#F0EEE8", keycap_top="#FAF8F2", keycap_side="#D4D0C6",
        legend="#22262C", legend_dim="#6E7278",
        mod_keycap="#3A4048", mod_keycap_top="#484E58", mod_legend="#F0EEE8",
        accent="#C8102E", pressed="#F04460", armed="#C8102E", bound_dot="#C8102E",
        brand_mark="iKBC",
    ),
}

# Longer / more specific tokens first.
_BRAND_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("logitech", ("logitech", "logi ", "mx keys", "mx mechanical", "g915", "g815", "g713", "g715", "k380", "k780", "k845")),
    ("razer", ("razer", "blackwidow", "huntsman", "orphan", "deathstalker")),
    ("corsair", ("corsair", "k70", "k65", "k63", "k100", "k55", "strafe")),
    ("keychron", ("keychron", "k2 ", "k3 ", "k4 ", "k5 ", "k6 ", "k8 ", "k10", "q1 ", "q2 ", "q3 ", "v1 ", "v2 ")),
    ("apple", ("magic keyboard", "apple keyboard", "apple inc", "magic kb")),
    ("microsoft", ("microsoft", "sculpt", "surface keyboard", "designer compact")),
    ("steelseries", ("steelseries", "apex", "prism")),
    ("hyperx", ("hyperx", "alloy")),
    ("nuphy", ("nuphy", "air75", "air60", "air96", "halo65", "halo75")),
    ("ikbc", ("ikbc", "cd87", "cd108", "w200", "poker")),
]


def detect_style(device_name: str | None) -> KeyboardStyle:
    text = (device_name or "").lower()
    for style_id, tokens in _BRAND_RULES:
        if any(tok in text for tok in tokens):
            return STYLES[style_id]
    return STYLES["default"]
