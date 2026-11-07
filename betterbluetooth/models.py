from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class DeviceKind(str, Enum):
    HEADSET = "headset"
    HEADPHONES = "headphones"
    SPEAKER = "speaker"
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    GAMEPAD = "gamepad"
    PHONE = "phone"
    COMPUTER = "computer"
    WATCH = "watch"
    PEN = "pen"
    OTHER = "other"


@dataclass
class Device:
    address: str
    name: str
    kind: DeviceKind = DeviceKind.OTHER
    paired: bool = False
    connected: bool = False
    battery: int | None = None
    rssi: int | None = None
    system_name: str = ""
    #: "bluetooth" for devices managed by the Bluetooth backend, "wireless" for 2.4G/USB peripherals
    transport: str = "bluetooth"
    charging: bool | None = None
    extra: dict = field(default_factory=dict)
    #: App-level stable identity (survives re-pair when MAC changes). Empty until resolved.
    stable_id: str = ""

    @property
    def id(self) -> str:
        return self.stable_id or self.address

    @property
    def is_bluetooth(self) -> bool:
        return self.transport == "bluetooth"


@dataclass
class AdapterState:
    present: bool = False
    powered: bool = False
    name: str = ""
    discovering: bool = False


_MAC_RE = re.compile(r"([0-9A-Fa-f]{2}[:\-_]?){5}[0-9A-Fa-f]{2}")


def normalize_address(addr: str | int) -> str:
    if isinstance(addr, int):
        raw = f"{addr:012X}"
    else:
        raw = re.sub(r"[^0-9A-Fa-f]", "", addr).upper()
    return ":".join(raw[i:i + 2] for i in range(0, 12, 2))


def kind_from_icon(icon: str | None) -> DeviceKind:
    """Map a freedesktop icon name (as reported by BlueZ) to a DeviceKind."""
    if not icon:
        return DeviceKind.OTHER
    table = {
        "audio-headset": DeviceKind.HEADSET,
        "audio-headphones": DeviceKind.HEADPHONES,
        "audio-card": DeviceKind.SPEAKER,
        "audio-speakers": DeviceKind.SPEAKER,
        "input-mouse": DeviceKind.MOUSE,
        "input-keyboard": DeviceKind.KEYBOARD,
        "input-gaming": DeviceKind.GAMEPAD,
        "input-tablet": DeviceKind.PEN,
        "phone": DeviceKind.PHONE,
        "computer": DeviceKind.COMPUTER,
    }
    return table.get(icon, DeviceKind.OTHER)


def kind_from_class(cod: int | None) -> DeviceKind:
    """Map a classic Bluetooth Class of Device to a DeviceKind."""
    if not cod:
        return DeviceKind.OTHER
    major = (cod >> 8) & 0x1F
    minor = (cod >> 2) & 0x3F
    if major == 0x01:
        return DeviceKind.COMPUTER
    if major == 0x02:
        return DeviceKind.PHONE
    if major == 0x04:
        if minor in (0x01, 0x02):
            return DeviceKind.HEADSET
        if minor in (0x06,):
            return DeviceKind.HEADPHONES
        return DeviceKind.SPEAKER
    if major == 0x05:
        kb_ptr = (minor >> 4) & 0x03
        sub = minor & 0x0F
        if sub in (0x01, 0x02):
            return DeviceKind.GAMEPAD
        if sub == 0x05:
            return DeviceKind.PEN
        if kb_ptr == 0x01 or kb_ptr == 0x03:
            return DeviceKind.KEYBOARD
        if kb_ptr == 0x02:
            return DeviceKind.MOUSE
    if major == 0x07:
        return DeviceKind.WATCH
    return DeviceKind.OTHER


def kind_from_name(name: str | None) -> DeviceKind | None:
    """Guess kind from a Bluetooth display name when CoD / Appearance is missing."""
    text = (name or "").lower()
    if not text:
        return None
    if any(tok in text for tok in (
        "xbox", "dualsense", "dualshock", "joy-con", "joycon", "pro controller",
        "gamepad", "wireless controller", "switch pro", "8bitdo", "八位堂",
        "gamesir", "盖世小鸡", "flydigi", "飞智", "betop", "北通",
        "gulikit", "谷粒", "pxn", "莱仕达", "iine", "良值", "mocute", "魔卡特",
        "vader", "apex", "tarantula", "cyclone",
    )):
        return DeviceKind.GAMEPAD
    if any(tok in text for tok in ("keyboard", "keychron", "mx keys", "magic keyboard")):
        return DeviceKind.KEYBOARD
    if any(tok in text for tok in ("mouse", "mx master", "g pro", "deathadder")):
        return DeviceKind.MOUSE
    if any(tok in text for tok in ("headset", "airpods", "buds", "headphones", "wh-1000", "sony wh")):
        return DeviceKind.HEADPHONES
    return None


def kind_from_appearance(app: int | None) -> DeviceKind:
    """Map a BLE GAP Appearance value to a DeviceKind."""
    if not app:
        return DeviceKind.OTHER
    exact = {
        0x03C1: DeviceKind.KEYBOARD,
        0x03C2: DeviceKind.MOUSE,
        0x03C3: DeviceKind.GAMEPAD,
        0x03C4: DeviceKind.GAMEPAD,
        0x03C5: DeviceKind.PEN,
        0x03C7: DeviceKind.PEN,
        0x0941: DeviceKind.HEADPHONES,
        0x0942: DeviceKind.HEADSET,
        0x0943: DeviceKind.HEADPHONES,
    }
    if app in exact:
        return exact[app]
    category = app >> 6
    return {
        0x01: DeviceKind.PHONE,
        0x02: DeviceKind.COMPUTER,
        0x03: DeviceKind.WATCH,
        0x21: DeviceKind.SPEAKER,
        0x25: DeviceKind.HEADPHONES,
    }.get(category, DeviceKind.OTHER)


AUDIO_KINDS = {DeviceKind.HEADSET, DeviceKind.HEADPHONES, DeviceKind.SPEAKER}
