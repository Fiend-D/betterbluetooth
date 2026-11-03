from __future__ import annotations

import asyncio
import re
from typing import Callable

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

from ..models import Device, DeviceKind, normalize_address
from . import PeripheralSource

UPOWER = "org.freedesktop.UPower"
IFACE_DEVICE = "org.freedesktop.UPower.Device"
_WATCHED = {"Percentage", "IsPresent", "State", "BatteryLevel", "Model"}
_MAC = re.compile(r"([0-9a-fA-F]{2}([:_])[0-9a-fA-F]{2}(\2[0-9a-fA-F]{2}){4})")

# org.freedesktop.UPower.Device.Type
_KINDS = {
    5: DeviceKind.MOUSE, 6: DeviceKind.KEYBOARD, 8: DeviceKind.PHONE, 12: DeviceKind.GAMEPAD,
    13: DeviceKind.PEN, 14: DeviceKind.MOUSE, 17: DeviceKind.HEADSET, 18: DeviceKind.SPEAKER,
    19: DeviceKind.HEADPHONES, 26: DeviceKind.WATCH,
}
_SKIP_TYPES = {0, 1, 2, 3, 4, 11, 15, 16}
_STATE_CHARGING = 1
# org.freedesktop.UPower.Device.BatteryLevel for coarse-only devices (e.g. Joy-Con via hid-nintendo);
# when it is not None (1), Percentage is meaningless.
_LEVEL_PERCENT = {3: 20, 4: 5, 6: 55, 7: 80, 8: 100}


class UPowerSource(PeripheralSource):
    name = "UPower"

    def __init__(self) -> None:
        self.bus: MessageBus | None = None
        self._on_change: Callable[[], None] | None = None

    async def start(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self.bus.add_message_handler(lambda msg: self._on_signal(msg))
        await self.bus.call(Message(
            destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus", member="AddMatch", signature="s",
            body=[f"type='signal',sender='{UPOWER}'"],
        ))

    async def stop(self) -> None:
        if self.bus:
            self.bus.disconnect()

    def _on_signal(self, msg: Message) -> None:
        if msg.message_type != MessageType.SIGNAL or not self._on_change:
            return
        if msg.member in ("DeviceAdded", "DeviceRemoved"):
            self._on_change()
        elif msg.member == "PropertiesChanged" and msg.body and msg.body[0] == IFACE_DEVICE:
            if _WATCHED & set(msg.body[1]):
                self._on_change()

    async def _call(self, path: str, iface: str, member: str, signature: str = "", body=None):
        assert self.bus is not None
        reply = await asyncio.wait_for(self.bus.call(Message(
            destination=UPOWER, path=path, interface=iface, member=member,
            signature=signature, body=body or [])), 5)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(reply.error_name)
        return reply.body

    async def devices(self) -> list[Device]:
        if not self.bus:
            return []
        paths = (await self._call("/org/freedesktop/UPower", UPOWER, "EnumerateDevices"))[0]
        result = []
        for path in paths:
            try:
                raw = (await self._call(path, "org.freedesktop.DBus.Properties", "GetAll", "s", [IFACE_DEVICE]))[0]
            except Exception:
                continue
            p = {k: (v.value if isinstance(v, Variant) else v) for k, v in raw.items()}
            dev = self._to_device(path, p)
            if dev:
                result.append(dev)
        return result

    @staticmethod
    def _to_device(path: str, p: dict) -> Device | None:
        if p.get("PowerSupply") or not p.get("IsPresent", True):
            return None
        dtype = int(p.get("Type", 0))
        if dtype in _SKIP_TYPES:
            return None
        native = str(p.get("NativePath", ""))
        serial = str(p.get("Serial", ""))
        extra: dict = {}
        if native.startswith("/org/bluez/"):
            extra["bt_address"] = normalize_address(native.rsplit("dev_", 1)[-1])
        else:
            m = _MAC.search(native) or _MAC.search(serial)
            if m:
                extra["bt_address"] = normalize_address(m.group(1))
        model = str(p.get("Model") or "").strip()
        vendor = str(p.get("Vendor") or "").strip()
        name = model or (f"{vendor} 设备" if vendor else "无线设备")
        percentage = p.get("Percentage")
        battery = int(round(percentage)) if percentage is not None else None
        level = int(p.get("BatteryLevel", 0) or 0)
        if level in _LEVEL_PERCENT:
            battery = _LEVEL_PERCENT[level]
        if "hidpp" in native:
            extra["via"] = "Logitech 接收器"
        elif "nintendo" in native:
            extra["via"] = "Switch 手柄"
        else:
            extra["via"] = "无线外设"
        return Device(
            address=f"upower:{serial or native or path}",
            name=name,
            kind=_KINDS.get(dtype, DeviceKind.OTHER),
            connected=True,
            battery=battery,
            transport="wireless",
            charging=int(p.get("State", 0)) == _STATE_CHARGING,
            extra=extra,
        )
