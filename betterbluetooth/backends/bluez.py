# No `from __future__ import annotations` here: dbus-fast reads the D-Bus
# signatures from the method annotations of the agent below.
import asyncio
import os
import re
from pathlib import Path
from typing import Callable, Optional

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, method

from ..models import (
    AUDIO_KINDS, AdapterState, Device, DeviceKind, kind_from_appearance,
    kind_from_icon, kind_from_name, normalize_address, resolve_kind,
)
from .base import Backend, BackendError

BLUEZ = "org.bluez"
IFACE_ADAPTER = "org.bluez.Adapter1"
IFACE_DEVICE = "org.bluez.Device1"
IFACE_BATTERY = "org.bluez.Battery1"
IFACE_PROPS = "org.freedesktop.DBus.Properties"
AGENT_PATH = "/com/betterbluetooth/agent"

_WATCHED_PROPS = {"Connected", "Paired", "Percentage", "Powered", "Alias", "Name", "Trusted", "Icon"}

_ERRORS = {
    "org.bluez.Error.InProgress": "操作正在进行中",
    "org.bluez.Error.AlreadyExists": "设备已配对",
    "org.bluez.Error.AlreadyConnected": "设备已连接",
    "org.bluez.Error.NotReady": "蓝牙适配器未就绪，请先打开蓝牙",
    "org.bluez.Error.AuthenticationFailed": "认证失败",
    "org.bluez.Error.AuthenticationCanceled": "配对已取消",
    "org.bluez.Error.AuthenticationRejected": "配对被设备拒绝",
    "org.bluez.Error.AuthenticationTimeout": "配对超时",
    "org.bluez.Error.ConnectionAttemptFailed": "连接失败",
    "org.bluez.Error.DoesNotExist": "设备不存在",
    "org.freedesktop.DBus.Error.NoReply": "设备无响应",
}


def _friendly(name: str, text: str) -> str:
    low = text.lower()
    if "page-timeout" in low or "host is down" in low:
        return "设备无响应，请确认设备已开机并在附近"
    if "profile-unavailable" in low:
        return "设备不支持可连接的服务"
    if name in _ERRORS:
        return _ERRORS[name]
    return text or name


def _unwrap(props: dict) -> dict:
    return {k: (v.value if isinstance(v, Variant) else v) for k, v in props.items()}


class _Agent(ServiceInterface):
    """Pairing agent used only for pairings started by this app."""

    def __init__(self, backend: "BluezBackend"):
        super().__init__("org.bluez.Agent1")
        self._backend = backend

    def _check(self, device: str) -> None:
        if device != self._backend._pairing_path:
            raise DBusError("org.bluez.Error.Rejected", "Not initiated by BetterBluetooth")

    @method()
    def Release(self):
        pass

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        self._check(device)
        return "0000"

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        self._check(device)
        self._backend._message(f"请在设备上输入配对码：{pincode}")

    @method()
    def RequestPasskey(self, device: "o") -> "u":
        self._check(device)
        return 0

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        self._check(device)
        if entered == 0:
            self._backend._message(f"请在设备上输入 {passkey:06d} 并按回车")

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):
        self._check(device)
        self._backend._message(f"配对码 {passkey:06d}，已自动确认")

    @method()
    def RequestAuthorization(self, device: "o"):
        self._check(device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):
        self._check(device)

    @method()
    def Cancel(self):
        pass


class BluezBackend(Backend):
    name = "BlueZ"
    capabilities = frozenset({"power", "connect", "pair", "remove", "rename", "scan"})

    def __init__(self) -> None:
        super().__init__()
        self.bus: Optional[MessageBus] = None
        self._adapter_path: Optional[str] = None
        self._pairing_path: Optional[str] = None
        self._experimental: Optional[bool] = None

    async def start(self) -> None:
        try:
            self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        except Exception as e:
            raise BackendError(f"无法连接系统 D-Bus：{e}") from e
        self.bus.add_message_handler(lambda msg: self._on_dbus_message(msg))
        await self.bus.call(Message(
            destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus", member="AddMatch", signature="s",
            body=[f"type='signal',sender='{BLUEZ}'"],
        ))
        self.bus.export(AGENT_PATH, _Agent(self))
        try:
            await self._call("/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                             "os", [AGENT_PATH, "KeyboardDisplay"])
        except BackendError:
            pass

    async def stop(self) -> None:
        if self.bus:
            try:
                await self._call("/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent", "o", [AGENT_PATH])
            except Exception:
                pass
            self.bus.disconnect()

    def _on_dbus_message(self, msg: Message):
        if msg.message_type != MessageType.SIGNAL:
            return
        if msg.member == "PropertiesChanged" and msg.body:
            iface, changed = msg.body[0], msg.body[1]
            if iface in (IFACE_DEVICE, IFACE_BATTERY, IFACE_ADAPTER) and _WATCHED_PROPS & set(changed):
                self._changed()
        elif msg.member in ("InterfacesAdded", "InterfacesRemoved"):
            ifaces = msg.body[1] if len(msg.body) > 1 else []
            if {IFACE_DEVICE, IFACE_BATTERY, IFACE_ADAPTER} & set(ifaces):
                self._changed()

    async def _call(self, path: str, iface: str, member: str, signature: str = "",
                    body: Optional[list] = None, timeout: float = 30):
        assert self.bus is not None
        msg = Message(destination=BLUEZ, path=path, interface=iface, member=member,
                      signature=signature, body=body or [])
        try:
            reply = await asyncio.wait_for(self.bus.call(msg), timeout)
        except asyncio.TimeoutError:
            raise BackendError("操作超时") from None
        if reply.message_type == MessageType.ERROR:
            text = reply.body[0] if reply.body else ""
            raise BackendError(_friendly(reply.error_name or "", str(text)))
        return reply.body

    async def _objects(self) -> dict[str, dict[str, dict]]:
        body = await self._call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
        objs = {path: {i: _unwrap(p) for i, p in ifaces.items()} for path, ifaces in body[0].items()}
        adapters = sorted(p for p, i in objs.items() if IFACE_ADAPTER in i)
        if self._adapter_path not in adapters:
            self._adapter_path = adapters[0] if adapters else None
        return objs

    async def _set(self, path: str, iface: str, prop: str, value: Variant) -> None:
        await self._call(path, IFACE_PROPS, "Set", "ssv", [iface, prop, value])

    def _device_path(self, address: str) -> str:
        if not self._adapter_path:
            raise BackendError("未找到蓝牙适配器")
        return f"{self._adapter_path}/dev_{address.replace(':', '_')}"

    def _require_adapter(self) -> str:
        if not self._adapter_path:
            raise BackendError("未找到蓝牙适配器")
        return self._adapter_path

    @staticmethod
    def _to_device(props: dict, ifaces: dict) -> Device:
        battery = ifaces.get(IFACE_BATTERY, {}).get("Percentage")
        name = props.get("Alias") or props.get("Name") or props.get("Address", "")
        appearance = props.get("Appearance")
        try:
            appearance_i = int(appearance) if appearance is not None else None
        except (TypeError, ValueError):
            appearance_i = None
        kind = resolve_kind(
            kind_from_icon(props.get("Icon")),
            kind_from_appearance(appearance_i),
            kind_from_name(name),
            name=name,
        )
        return Device(
            address=normalize_address(props.get("Address", "")),
            name=name,
            system_name=props.get("Name", ""),
            kind=kind,
            paired=bool(props.get("Paired") or props.get("Bonded")),
            connected=bool(props.get("Connected")),
            battery=int(battery) if battery is not None else None,
            rssi=props.get("RSSI"),
            extra={"trusted": bool(props.get("Trusted"))},
        )

    async def adapter(self) -> AdapterState:
        objs = await self._objects()
        if not self._adapter_path:
            return AdapterState()
        p = objs[self._adapter_path][IFACE_ADAPTER]
        return AdapterState(True, bool(p.get("Powered")), p.get("Alias") or p.get("Name", ""),
                            bool(p.get("Discovering")))

    async def devices(self) -> list[Device]:
        objs = await self._objects()
        if not self._adapter_path:
            return []
        prefix = self._adapter_path + "/"
        result = []
        for path, ifaces in objs.items():
            props = ifaces.get(IFACE_DEVICE)
            if not props or not path.startswith(prefix):
                continue
            dev = self._to_device(props, ifaces)
            if dev.paired or dev.connected:
                result.append(dev)
        return result

    def diagnostics(self, devices: list[Device]) -> list[str]:
        missing_audio = [
            d for d in devices
            if d.connected and d.battery is None and d.kind in AUDIO_KINDS
        ]
        if missing_audio and not self._experimental_enabled():
            names = "、".join(d.name for d in missing_audio[:2])
            return [
                f"{names} 未上报电量。多数耳机需要开启 BlueZ 实验特性："
                "在 /etc/bluetooth/main.conf 的 [General] 中设置 Experimental = true，"
                "然后执行 sudo systemctl restart bluetooth。"
            ]
        missing_other = [
            d for d in devices
            if d.connected and d.battery is None
            and d.kind not in AUDIO_KINDS and d.kind != DeviceKind.GAMEPAD
        ]
        if missing_other and not missing_audio:
            names = "、".join(d.name for d in missing_other[:2])
            return [f"{names} 已连接但系统未提供电量（设备或驱动未通过 Battery1/UPower 上报）。"]
        return []

    def _experimental_enabled(self) -> bool:
        if self._experimental is None:
            self._experimental = _detect_experimental()
        return self._experimental

    async def set_powered(self, on: bool) -> None:
        await self._set(self._require_adapter(), IFACE_ADAPTER, "Powered", Variant("b", on))

    async def scan(self, on_found: Callable[[list[Device]], None], duration: float) -> None:
        adapter = self._require_adapter()
        try:
            await self._call(adapter, IFACE_ADAPTER, "SetDiscoveryFilter", "a{sv}",
                             [{"Transport": Variant("s", "auto"), "DuplicateData": Variant("b", False)}])
        except BackendError:
            pass
        await self._call(adapter, IFACE_ADAPTER, "StartDiscovery")
        try:
            loop = asyncio.get_running_loop()
            end = loop.time() + duration
            while loop.time() < end:
                await asyncio.sleep(1.0)
                objs = await self._objects()
                found = []
                for path, ifaces in objs.items():
                    props = ifaces.get(IFACE_DEVICE)
                    if not props or not path.startswith(adapter + "/"):
                        continue
                    if props.get("Paired") or props.get("RSSI") is None:
                        continue
                    if not (props.get("Name") or props.get("Alias", "").replace("-", ":") != props.get("Address")):
                        continue
                    found.append(self._to_device(props, ifaces))
                found.sort(key=lambda d: -(d.rssi or -127))
                on_found(found)
        finally:
            try:
                await self._call(adapter, IFACE_ADAPTER, "StopDiscovery")
            except Exception:
                pass

    async def connect(self, address: str) -> None:
        await self._call(self._device_path(address), IFACE_DEVICE, "Connect", timeout=45)

    async def disconnect(self, address: str) -> None:
        await self._call(self._device_path(address), IFACE_DEVICE, "Disconnect")

    async def pair(self, address: str) -> None:
        path = self._device_path(address)
        self._pairing_path = path
        try:
            try:
                await self._call(path, IFACE_DEVICE, "Pair", timeout=90)
            except BackendError as e:
                if str(e) != _ERRORS["org.bluez.Error.AlreadyExists"]:
                    raise
            await self._set(path, IFACE_DEVICE, "Trusted", Variant("b", True))
            try:
                await self._call(path, IFACE_DEVICE, "Connect", timeout=45)
            except BackendError as e:
                self._message(f"已配对，但连接失败：{e}")
        finally:
            self._pairing_path = None

    async def remove(self, address: str) -> None:
        await self._call(self._require_adapter(), IFACE_ADAPTER, "RemoveDevice", "o",
                         [self._device_path(address)])

    async def rename(self, address: str, name: str) -> None:
        await self._set(self._device_path(address), IFACE_DEVICE, "Alias", Variant("s", name))


def _detect_experimental() -> bool:
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if cmd and os.path.basename(cmd[0].decode(errors="ignore")) == "bluetoothd":
            if any(a in (b"-E", b"--experimental") for a in cmd):
                return True
            break
    try:
        text = Path("/etc/bluetooth/main.conf").read_text(errors="ignore")
    except OSError:
        return False
    return bool(re.search(r"^\s*Experimental\s*=\s*true", text, re.M | re.I))
