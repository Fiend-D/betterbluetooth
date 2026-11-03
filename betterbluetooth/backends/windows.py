from __future__ import annotations

import asyncio
import platform
import re
import sys
import time
import uuid
from typing import Any, Callable

from winrt.windows.devices.bluetooth import (
    BluetoothAdapter,
    BluetoothCacheMode,
    BluetoothConnectionStatus,
    BluetoothDevice,
    BluetoothLEDevice,
)
from winrt.windows.devices.bluetooth.genericattributeprofile import GattCommunicationStatus
from winrt.windows.devices.enumeration import (
    DeviceInformation,
    DeviceInformationKind,
    DevicePairingKinds,
    DevicePairingResultStatus,
    DeviceWatcherStatus,
)
from winrt.windows.devices.radios import Radio, RadioState
from winrt.windows.storage.streams import DataReader

from ..models import Device, AdapterState, kind_from_appearance, kind_from_class, normalize_address
from . import win_setupapi
from .base import Backend, BackendError

BATTERY_SERVICE = uuid.UUID("0000180f-0000-1000-8000-00805f9b34fb")
BATTERY_LEVEL = uuid.UUID("00002a19-0000-1000-8000-00805f9b34fb")
GATT_CACHE_OK = 60
GATT_CACHE_FAIL = 300

AEP_PROTOCOL_CLASSIC = "{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}"
AEP_PROTOCOL_LE = "{bb7bb05e-5972-42b5-94fc-76eaa7084d49}"
PROP_ADDRESS = "System.Devices.Aep.DeviceAddress"
PROP_SIGNAL = "System.Devices.Aep.SignalStrength"
PROP_COD_MAJOR = "System.Devices.Aep.Bluetooth.Cod.Major"
PROP_COD_MINOR = "System.Devices.Aep.Bluetooth.Cod.Minor"
PROP_APPEARANCE = "System.Devices.Aep.Bluetooth.Le.Appearance"
SCAN_PROPERTIES = [PROP_ADDRESS, "System.Devices.Aep.IsPaired", PROP_SIGNAL,
                   PROP_COD_MAJOR, PROP_COD_MINOR, PROP_APPEARANCE]
_UNSIGNED = ("unbox_uint16", "unbox_uint32", "unbox_uint8", "unbox_int32")

_MAC_IN_ID = re.compile(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})")


def _overload(obj: Any, names: list[str], *args):
    """pywinrt exposes WinRT overloads under different names depending on version."""
    for name in names:
        fn = getattr(obj, name, None)
        if fn is not None:
            return fn(*args)
    raise AttributeError(f"{type(obj).__name__} has none of {names}")


async def _find_all(selector: str):
    return await _overload(DeviceInformation, ["find_all_async_aqs_filter", "find_all_async"], selector)


def _prop(info: DeviceInformation, key: str, *unbox_names: str):
    """Read a boxed value from DeviceInformation.properties; None when absent or not unboxable."""
    try:
        props = info.properties
        value = props[key] if key in props else None
    except Exception:
        try:
            value = props.lookup(key) if props.has_key(key) else None
        except Exception:
            return None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    import winrt.system
    for unbox_name in unbox_names:
        try:
            return getattr(winrt.system, unbox_name)(value)
        except Exception:
            continue
    return None


def _new_watcher(aqs: str, properties: list[str]):
    kind = DeviceInformationKind.ASSOCIATION_ENDPOINT
    try:
        return DeviceInformation.create_watcher(aqs, properties, kind)
    except TypeError:
        return DeviceInformation.create_watcher_with_kind_aqs_filter_and_additional_properties(
            aqs, properties, kind)


_supported_properties: list[str] | None = None


def _create_watcher(aqs: str):
    """Windows rejects the whole watcher on any unknown property key, so probe keys one by one once."""
    global _supported_properties
    if _supported_properties is None:
        try:
            _new_watcher(aqs, SCAN_PROPERTIES)
            _supported_properties = list(SCAN_PROPERTIES)
        except OSError:
            supported = []
            for key in SCAN_PROPERTIES:
                try:
                    _new_watcher(aqs, [key])
                    supported.append(key)
                except OSError as e:
                    print(f"[windows] property {key} rejected: {e}", file=sys.stderr)
            _supported_properties = supported
    return _new_watcher(aqs, _supported_properties)


def _address_from_id(device_id: str) -> str | None:
    found = _MAC_IN_ID.findall(device_id)
    return normalize_address(found[-1]) if found else None


_PAIR_ERRORS = {
    DevicePairingResultStatus.AUTHENTICATION_FAILURE: "认证失败",
    DevicePairingResultStatus.AUTHENTICATION_TIMEOUT: "配对超时",
    DevicePairingResultStatus.REJECTED_BY_HANDLER: "配对被拒绝",
    DevicePairingResultStatus.CONNECTION_REJECTED: "设备拒绝连接",
    DevicePairingResultStatus.NOT_READY_TO_PAIR: "设备未进入配对模式",
    DevicePairingResultStatus.NO_SUPPORTED_PROFILES: "设备没有可用的服务",
    DevicePairingResultStatus.PAIRING_CANCELED: "配对已取消",
    DevicePairingResultStatus.ACCESS_DENIED: "系统拒绝了配对请求",
    DevicePairingResultStatus.AUTHENTICATION_NOT_ALLOWED: "设备需要的配对方式暂不支持",
    DevicePairingResultStatus.OPERATION_ALREADY_IN_PROGRESS: "正在配对中",
}


class WindowsBackend(Backend):
    name = "WinRT"
    capabilities = frozenset({"power", "pair", "remove", "scan"})

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._classic: dict[str, BluetoothDevice] = {}
        self._le: dict[str, BluetoothLEDevice] = {}
        self._tokens: list[tuple[Any, Any]] = []
        self._paired_infos: dict[str, list[DeviceInformation]] = {}
        self._scan_infos: dict[str, DeviceInformation] = {}
        self._gatt_cache: dict[str, tuple[float, int | None]] = {}

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    async def stop(self) -> None:
        for dev, token in self._tokens:
            try:
                dev.remove_connection_status_changed(token)
            except Exception:
                pass
        for dev in [*self._classic.values(), *self._le.values()]:
            try:
                dev.close()
            except Exception:
                pass

    def _notify_threadsafe(self, *_args) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._changed)

    def _watch(self, dev) -> None:
        try:
            self._tokens.append((dev, dev.add_connection_status_changed(self._notify_threadsafe)))
        except Exception:
            pass

    async def _get_classic(self, device_id: str) -> BluetoothDevice | None:
        dev = self._classic.get(device_id)
        if dev is None:
            dev = await BluetoothDevice.from_id_async(device_id)
            if dev is not None:
                self._classic[device_id] = dev
                self._watch(dev)
        return dev

    async def _get_le(self, device_id: str) -> BluetoothLEDevice | None:
        dev = self._le.get(device_id)
        if dev is None:
            dev = await BluetoothLEDevice.from_id_async(device_id)
            if dev is not None:
                self._le[device_id] = dev
                self._watch(dev)
        return dev

    async def _radio(self):
        adapter = await BluetoothAdapter.get_default_async()
        if adapter is None:
            return None
        return await adapter.get_radio_async()

    async def adapter(self) -> AdapterState:
        try:
            radio = await self._radio()
        except Exception:
            radio = None
        if radio is None:
            return AdapterState()
        return AdapterState(True, radio.state == RadioState.ON, platform.node())

    async def set_powered(self, on: bool) -> None:
        await Radio.request_access_async()
        radio = await self._radio()
        if radio is None:
            raise BackendError("未找到蓝牙适配器")
        await radio.set_state_async(RadioState.ON if on else RadioState.OFF)

    async def devices(self) -> list[Device]:
        merged: dict[str, Device] = {}
        le_objs: dict[str, BluetoothLEDevice] = {}
        paired_infos: dict[str, list[DeviceInformation]] = {}

        def merge(dev: Device, info: DeviceInformation) -> None:
            paired_infos.setdefault(dev.address, []).append(info)
            cur = merged.get(dev.address)
            if cur is None:
                merged[dev.address] = dev
                return
            cur.connected = cur.connected or dev.connected
            if cur.kind.value == "other":
                cur.kind = dev.kind

        for info in await _find_all(BluetoothDevice.get_device_selector_from_pairing_state(True)):
            dev = await self._get_classic(info.id)
            if dev is None:
                continue
            merge(Device(
                address=normalize_address(dev.bluetooth_address),
                name=dev.name or info.name,
                kind=kind_from_class(dev.class_of_device.raw_value),
                paired=True,
                connected=dev.connection_status == BluetoothConnectionStatus.CONNECTED,
            ), info)

        for info in await _find_all(BluetoothLEDevice.get_device_selector_from_pairing_state(True)):
            dev = await self._get_le(info.id)
            if dev is None:
                continue
            address = normalize_address(dev.bluetooth_address)
            le_objs[address] = dev
            merge(Device(
                address=address,
                name=dev.name or info.name,
                kind=kind_from_appearance(dev.appearance.raw_value),
                paired=True,
                connected=dev.connection_status == BluetoothConnectionStatus.CONNECTED,
            ), info)

        self._paired_infos = paired_infos
        loop = asyncio.get_running_loop()
        try:
            levels = await loop.run_in_executor(None, win_setupapi.read_batteries)
        except Exception:
            levels = {}
        for address, dev in merged.items():
            if not dev.connected:
                continue
            dev.battery = levels.get(address)
            if dev.battery is None and address in le_objs:
                dev.battery = await self._gatt_battery(address, le_objs[address])
        return list(merged.values())

    async def _gatt_battery(self, address: str, dev: BluetoothLEDevice) -> int | None:
        now = time.monotonic()
        cached = self._gatt_cache.get(address)
        if cached:
            age = now - cached[0]
            if age < (GATT_CACHE_OK if cached[1] is not None else GATT_CACHE_FAIL):
                return cached[1]
        level = None
        try:
            res = await asyncio.wait_for(_overload(
                dev, ["get_gatt_services_for_uuid_with_cache_mode_async", "get_gatt_services_for_uuid_async"],
                BATTERY_SERVICE, BluetoothCacheMode.UNCACHED), 10)
            if res.status == GattCommunicationStatus.SUCCESS:
                for service in res.services:
                    try:
                        chars = await _overload(
                            service, ["get_characteristics_for_uuid_with_cache_mode_async",
                                      "get_characteristics_for_uuid_async"],
                            BATTERY_LEVEL, BluetoothCacheMode.UNCACHED)
                        for ch in chars.characteristics:
                            val = await _overload(
                                ch, ["read_value_with_cache_mode_async", "read_value_async"],
                                BluetoothCacheMode.UNCACHED)
                            if val.status == GattCommunicationStatus.SUCCESS:
                                level = DataReader.from_buffer(val.value).read_byte()
                                break
                    finally:
                        service.close()
                    if level is not None:
                        break
        except Exception:
            level = None
        self._gatt_cache[address] = (now, level)
        return level

    def _scan_device(self, info: DeviceInformation) -> Device | None:
        name = (info.name or "").strip()
        address = _prop(info, PROP_ADDRESS, "unbox_string") or _address_from_id(info.id)
        if not name or not address:
            return None
        address = normalize_address(address)
        if address.replace(":", "") in name.replace(":", "").replace("-", "").upper():
            return None
        major = _prop(info, PROP_COD_MAJOR, *_UNSIGNED)
        minor = _prop(info, PROP_COD_MINOR, *_UNSIGNED)
        appearance = _prop(info, PROP_APPEARANCE, *_UNSIGNED)
        cod = ((major & 0x1F) << 8 | (minor or 0) << 2) if major else None
        kind = kind_from_class(cod) if cod else kind_from_appearance(appearance)
        rssi = _prop(info, PROP_SIGNAL, "unbox_int32", "unbox_int16", "unbox_int8")
        return Device(address=address, name=name, kind=kind, rssi=rssi)

    async def scan(self, on_found: Callable[[list[Device]], None], duration: float) -> None:
        loop = asyncio.get_running_loop()
        infos: dict[str, DeviceInformation] = {}
        emit_pending = False

        def emit() -> None:
            nonlocal emit_pending
            emit_pending = False
            found: dict[str, Device] = {}
            for info in infos.values():
                dev = self._scan_device(info)
                if dev is None:
                    continue
                prev = found.get(dev.address)
                if prev is None or (dev.rssi or -127) > (prev.rssi or -127):
                    found[dev.address] = dev
                    self._scan_infos[dev.address] = info
            on_found(sorted(found.values(), key=lambda d: -(d.rssi if d.rssi is not None else -127)))

        def schedule() -> None:
            nonlocal emit_pending
            if not emit_pending:
                emit_pending = True
                loop.call_later(0.5, emit)

        def added(info: DeviceInformation) -> None:
            infos[info.id] = info
            schedule()

        def updated(update) -> None:
            info = infos.get(update.id)
            if info is not None:
                info.update(update)
                schedule()

        def removed(update) -> None:
            if infos.pop(update.id, None) is not None:
                schedule()

        watchers = []
        try:
            for protocol in (AEP_PROTOCOL_CLASSIC, AEP_PROTOCOL_LE):
                aqs = (f'System.Devices.Aep.ProtocolId:="{protocol}" AND '
                       "System.Devices.Aep.IsPaired:=System.StructuredQueryType.Boolean#False")
                w = _create_watcher(aqs)
                tokens: list[tuple[str, Any]] = []
                watchers.append((w, tokens))
                handlers = (
                    ("added", added, True),
                    ("updated", updated, True),
                    ("removed", removed, False),
                )
                for event, handler, required in handlers:
                    try:
                        token = getattr(w, f"add_{event}")(
                            lambda _w, arg, h=handler: loop.call_soon_threadsafe(h, arg))
                    except OSError:
                        if required:
                            raise
                        continue
                    tokens.append((event, token))
                w.start()
            await asyncio.sleep(duration)
        finally:
            for w, tokens in watchers:
                try:
                    if w.status in (DeviceWatcherStatus.STARTED, DeviceWatcherStatus.ENUMERATION_COMPLETED):
                        w.stop()
                except Exception:
                    pass
                for event, token in tokens:
                    try:
                        getattr(w, f"remove_{event}")(token)
                    except Exception:
                        pass

    async def pair(self, address: str) -> None:
        info = self._scan_infos.get(address)
        if info is None:
            raise BackendError("设备不在搜索结果中，请重新搜索")
        custom = info.pairing.custom

        def on_request(_sender, args) -> None:
            kind = args.pairing_kind
            pin = getattr(args, "pin", "")
            if kind == DevicePairingKinds.PROVIDE_PIN:
                args.accept("0000")
                return
            if pin and self._loop:
                self._loop.call_soon_threadsafe(self._message, f"配对码 {pin}，已自动确认")
            args.accept()

        token = custom.add_pairing_requested(on_request)
        try:
            kinds = (DevicePairingKinds.CONFIRM_ONLY | DevicePairingKinds.CONFIRM_PIN_MATCH
                     | DevicePairingKinds.DISPLAY_PIN | DevicePairingKinds.PROVIDE_PIN)
            result = await custom.pair_async(kinds)
        finally:
            custom.remove_pairing_requested(token)
        if result.status not in (DevicePairingResultStatus.PAIRED, DevicePairingResultStatus.ALREADY_PAIRED):
            raise BackendError(_PAIR_ERRORS.get(result.status, f"配对失败（{result.status}）"))
        self._scan_infos.pop(address, None)

    async def remove(self, address: str) -> None:
        infos = self._paired_infos.get(address)
        if not infos:
            raise BackendError("设备不存在")
        for info in infos:
            await info.pairing.unpair_async()
            self._classic.pop(info.id, None)
            self._le.pop(info.id, None)
        self._gatt_cache.pop(address, None)
