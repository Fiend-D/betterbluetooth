"""Battery sources for non-Bluetooth wireless peripherals (2.4G receivers, USB-wireless gamepads)."""
from __future__ import annotations

import abc
import os
import sys
from typing import Callable

from ..models import AUDIO_KINDS, Device, DeviceKind, kind_from_name, strip_bt_name


class PeripheralSource(abc.ABC):
    name = "peripheral"

    async def start(self, on_change: Callable[[], None]) -> None:
        pass

    async def stop(self) -> None:
        pass

    @abc.abstractmethod
    async def devices(self) -> list[Device]:
        """Return devices with transport="wireless", or Bluetooth matches with extra["bt_address"] set."""


def create_sources(mock: bool = False) -> list[PeripheralSource]:
    if mock or os.environ.get("BB_BACKEND") == "mock":
        from .mock import MockPeripherals
        return [MockPeripherals()]
    sources: list[PeripheralSource] = []
    if sys.platform.startswith("linux"):
        from .upower import UPowerSource
        sources.append(UPowerSource())
    elif sys.platform == "win32":
        try:
            from .hidpp import HidppSource
        except ImportError:
            pass
        else:
            sources.append(HidppSource())
        try:
            from .gamepad_hid import GamepadHidSource
        except ImportError:
            try:
                from .switch import SwitchControllerSource
            except ImportError:
                pass
            else:
                sources.append(SwitchControllerSource())
        else:
            sources.append(GamepadHidSource())
    return sources


def _name_tokens(name: str) -> set[str]:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in name).split() if len(t) >= 3}


def _names_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    al, bl = a.lower(), b.lower()
    if al == bl or al in bl or bl in al:
        return True
    # Shared distinctive tokens (xbox/controller/dualsense/…)
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    shared = ta & tb
    if not shared:
        return False
    # "controller" alone is too weak; require another token or exact token overlap ≥2
    weak = {"controller", "wireless", "game", "gamepad", "bluetooth"}
    strong = shared - weak
    return bool(strong) or len(shared) >= 2


# Higher = more trustworthy. WinRT synthesizes mWh buckets (often stuck ~10%).
_BATTERY_RANK = {
    "PnP": 100,
    "HID": 90,
    "GATT": 80,
    "WinRT Gamepad": 25,
    "WinRT Raw": 25,
    "XInput": 15,
}


def _battery_rank(dev: Device) -> int:
    extra = dev.extra or {}
    via = extra.get("battery_via") or extra.get("via") or ""
    return _BATTERY_RANK.get(str(via), 40)


def _apply_battery(dst: Device, src: Device) -> bool:
    """Copy battery from src onto dst when src is missing or lower-quality."""
    if src.battery is None:
        return False
    if dst.battery is not None and _battery_rank(src) <= _battery_rank(dst):
        return False
    dst.battery = src.battery
    if src.charging is not None:
        dst.charging = src.charging
    dst.extra = dict(dst.extra or {})
    via = (src.extra or {}).get("battery_via") or (src.extra or {}).get("via")
    if via:
        dst.extra["battery_via"] = via
    return True


def _match_by_stripped_name(connected_bt: list[Device], candidates: list[str]) -> Device | None:
    """Match Hands-Free / Stereo endpoint names onto the parent Bluetooth device."""
    bases = {strip_bt_name(n).lower() for n in candidates if n}
    bases.update(n.lower() for n in candidates if n)
    bases.discard("")
    if not bases:
        return None
    hits = [
        d for d in connected_bt
        if (d.name or "").lower() in bases
        or strip_bt_name(d.name).lower() in bases
        or any(
            strip_bt_name(d.name).lower() == strip_bt_name(n).lower()
            for n in candidates if n
        )
    ]
    if len(hits) == 1:
        return hits[0]
    needy = [d for d in hits if d.battery is None]
    return needy[0] if len(needy) == 1 else None


def merge(bluetooth: list[Device], peripherals: list[Device]) -> list[Device]:
    """Attach peripheral readings to matching Bluetooth devices; append the rest."""
    by_addr = {d.address: d for d in bluetooth}
    connected_bt = [d for d in bluetooth if d.connected]
    by_name: dict[str, list[Device]] = {}
    for d in connected_bt:
        by_name.setdefault(d.name, []).append(d)
        base = strip_bt_name(d.name)
        if base and base != d.name:
            by_name.setdefault(base, []).append(d)
    result = list(bluetooth)
    seen: set[str] = set()

    # Prefer high-quality sources first so a later coarse WinRT/XInput cannot stick.
    peripherals = sorted(peripherals, key=_battery_rank, reverse=True)

    for p in peripherals:
        extra = p.extra or {}
        bt = by_addr.get(extra.get("bt_address", ""))
        candidates: list[str] = []
        if extra.get("bt_name"):
            candidates.append(extra["bt_name"])
        candidates.extend(extra.get("bt_names") or [])
        candidates.append(p.name)

        if bt is None:
            for name in candidates:
                same = by_name.get(name, [])
                if len(same) == 1:
                    bt = same[0]
                    break
        if bt is None:
            bt = _match_by_stripped_name(connected_bt, candidates)

        if bt is None and p.kind == DeviceKind.GAMEPAD:
            # Match by name even when Windows mis-classified the BT device as OTHER.
            # Never fuzzy-attach a gamepad reading onto headphones / speakers.
            fuzzy = [
                d for d in connected_bt
                if d.kind not in AUDIO_KINDS
                and any(_names_match(d.name, n) for n in candidates)
                and (d.kind == DeviceKind.GAMEPAD or d.kind == DeviceKind.OTHER
                     or "controller" in (d.name or "").lower()
                     or "xbox" in (d.name or "").lower()
                     or "dual" in (d.name or "").lower()
                     or "joy" in (d.name or "").lower()
                     or "gamesir" in (d.name or "").lower()
                     or "8bit" in (d.name or "").lower()
                     or "flydigi" in (d.name or "").lower()
                     or "盖世" in (d.name or "")
                     or "飞智" in (d.name or "")
                     or "北通" in (d.name or ""))
            ]
            if len(fuzzy) == 1:
                bt = fuzzy[0]
            elif len(fuzzy) > 1:
                needy = [d for d in fuzzy if d.battery is None]
                pads = [d for d in needy if d.kind == DeviceKind.GAMEPAD]
                if len(pads) == 1:
                    bt = pads[0]
                elif len(needy) == 1:
                    bt = needy[0]
            elif len(connected_bt) == 1 and connected_bt[0].battery is None:
                sole = connected_bt[0]
                if sole.kind in AUDIO_KINDS:
                    pass
                elif sole.kind in (DeviceKind.GAMEPAD, DeviceKind.OTHER) or _names_match(sole.name, p.name):
                    bt = sole

        if bt is not None:
            if bt.connected:
                _apply_battery(bt, p)
                # Only classify when the BT side is still OTHER. Prefer the
                # device / endpoint name (Hands-Free → headset) over a PnP
                # shadow that was historically hard-coded as GAMEPAD.
                if bt.kind == DeviceKind.OTHER:
                    inferred = kind_from_name(bt.name)
                    pnpish = (
                        extra.get("via") == "PnP"
                        or extra.get("battery_via") == "PnP"
                        or extra.get("pnp_shadow")
                    )
                    if not inferred:
                        for n in candidates:
                            guess = kind_from_name(n)
                            if not guess:
                                continue
                            # Legacy PnP shadows labeled every address "Xbox Wireless
                            # Controller"; never let that reclassify headphones.
                            if pnpish and guess == DeviceKind.GAMEPAD:
                                low = (n or "").lower()
                                if low in (
                                    "xbox wireless controller", "xbox controller",
                                    "wireless controller", "controller",
                                ):
                                    continue
                            inferred = guess
                            break
                    if inferred:
                        bt.kind = inferred
                    elif p.kind != DeviceKind.OTHER and not (
                        pnpish and p.kind == DeviceKind.GAMEPAD
                    ):
                        bt.kind = p.kind
                if p.kind == DeviceKind.GAMEPAD:
                    bt.extra = dict(bt.extra or {})
                    hints = list(bt.extra.get("model_hints") or [])
                    for n in [p.name, extra.get("bt_name"), *(extra.get("bt_names") or [])]:
                        if n and n not in hints:
                            hints.append(str(n))
                    if hints:
                        bt.extra["model_hints"] = hints[:12]
                    if extra.get("product") and not bt.extra.get("product"):
                        bt.extra["product"] = extra["product"]
                    if extra.get("xbox_bt_spoof"):
                        bt.extra["xbox_bt_spoof"] = True
            continue

        # PnP shadows / Hands-Free endpoints of already-listed BT devices must not
        # show up under「无线外设（2.4G）」— that was the AS-J18 duplicate.
        if extra.get("pnp_shadow") or extra.get("via") == "PnP" or extra.get("battery_via") == "PnP":
            if extra.get("bt_address") in by_addr:
                continue
            if p.kind in AUDIO_KINDS:
                continue
            if any(tok in (p.name or "").lower() for tok in (
                "hands-free", "hands free", "stereo", "avrcp", "headset",
            )):
                continue

        if p.address in seen:
            continue
        seen.add(p.address)
        result.append(p)
    return result
