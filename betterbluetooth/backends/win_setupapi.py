"""Read DEVPKEY_Bluetooth_BatteryLevel from PnP nodes (Windows Settings source).

Xbox / many BT pads expose an exact percent here. XInput often returns UNKNOWN
over Bluetooth; WinRT TryGetBatteryReport can rate-limit and bucket wrongly.
Walk Bluetooth + Hands-Free nodes, and climb HID parents (PadForge approach).
"""
from __future__ import annotations

import ctypes
import re
import uuid
from ctypes import wintypes

from ..models import normalize_address


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_string(cls, text: str) -> "GUID":
        g = cls()
        ctypes.memmove(ctypes.byref(g), uuid.UUID(text).bytes_le, 16)
        return g


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.ULONG)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", GUID),
                ("DevInst", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]


DIGCF_PRESENT = 0x02
DIGCF_ALLCLASSES = 0x04
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
CR_SUCCESS = 0
DEVPROP_TYPE_BYTE = 0x00000003
DEVPROP_TYPE_UINT32 = 0x00000007
DEVPROP_TYPE_STRING = 0x00000012

DEVPKEY_BLUETOOTH_BATTERY = DEVPROPKEY(GUID.from_string("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}"), 2)
DEVPKEY_NAME = DEVPROPKEY(GUID.from_string("{B725F130-47EF-101A-A5F1-02608C9EEBAC}"), 10)
DEVPKEY_DEVICE_FRIENDLY = DEVPROPKEY(GUID.from_string("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14)

_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_cfgmgr = ctypes.WinDLL("cfgmgr32", use_last_error=True)

_setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
_setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
_setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
_setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
_setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), wintypes.LPWSTR, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD)]
_setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
_setupapi.SetupDiGetDevicePropertyW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), ctypes.POINTER(DEVPROPKEY),
    ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
_setupapi.SetupDiGetDevicePropertyW.restype = wintypes.BOOL
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
_setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

_cfgmgr.CM_Get_Parent.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG]
_cfgmgr.CM_Get_Parent.restype = wintypes.DWORD
_cfgmgr.CM_Get_DevNode_PropertyW.argtypes = [
    wintypes.DWORD, ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(wintypes.ULONG),
    ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG), wintypes.ULONG]
_cfgmgr.CM_Get_DevNode_PropertyW.restype = wintypes.DWORD
_cfgmgr.CM_Get_Device_IDW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.ULONG, wintypes.ULONG]
_cfgmgr.CM_Get_Device_IDW.restype = wintypes.DWORD

_HEX12 = re.compile(r"(?<![0-9A-F])([0-9A-F]{12})(?![0-9A-F])")
_BASE_UUID_TAIL = "00805F9B34FB"
_BT_PREFIX = ("BTHENUM\\", "BTHLE", "BTHLEDEVICE", "BTHHFENUM", "BTH\\")


def _address_from_instance_id(instance_id: str) -> str | None:
    candidates = [m for m in _HEX12.findall(instance_id.upper()) if m != _BASE_UUID_TAIL]
    return normalize_address(candidates[-1]) if candidates else None


def _read_byte_prop(devinst: int, key: DEVPROPKEY) -> int | None:
    prop_type = wintypes.ULONG()
    value = ctypes.c_ubyte()
    size = wintypes.ULONG(1)
    if _cfgmgr.CM_Get_DevNode_PropertyW(
            devinst, ctypes.byref(key), ctypes.byref(prop_type),
            ctypes.byref(value), ctypes.byref(size), 0) != CR_SUCCESS:
        return None
    if prop_type.value not in (DEVPROP_TYPE_BYTE, DEVPROP_TYPE_UINT32):
        return None
    return int(value.value)


def _read_string_prop(devinst: int, key: DEVPROPKEY) -> str | None:
    prop_type = wintypes.ULONG()
    size = wintypes.ULONG(0)
    # Size probe
    _cfgmgr.CM_Get_DevNode_PropertyW(
        devinst, ctypes.byref(key), ctypes.byref(prop_type), None, ctypes.byref(size), 0)
    if size.value < 2:
        return None
    buf = ctypes.create_unicode_buffer(size.value // 2)
    size2 = wintypes.ULONG(size.value)
    if _cfgmgr.CM_Get_DevNode_PropertyW(
            devinst, ctypes.byref(key), ctypes.byref(prop_type),
            buf, ctypes.byref(size2), 0) != CR_SUCCESS:
        return None
    if prop_type.value != DEVPROP_TYPE_STRING:
        return None
    return (buf.value or "").strip() or None


def _instance_id(devinst: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    if _cfgmgr.CM_Get_Device_IDW(devinst, buf, 512, 0) != CR_SUCCESS:
        return ""
    return buf.value or ""


def _walk_battery(devinst: int, depth: int = 8) -> tuple[int | None, str | None, str]:
    """Climb parents until a Bluetooth battery percent is found."""
    cur = devinst
    for _ in range(depth):
        level = _read_byte_prop(cur, DEVPKEY_BLUETOOTH_BATTERY)
        iid = _instance_id(cur)
        if level is not None and 0 <= level <= 100:
            name = (_read_string_prop(cur, DEVPKEY_DEVICE_FRIENDLY)
                    or _read_string_prop(cur, DEVPKEY_NAME))
            return level, name, iid
        parent = wintypes.DWORD()
        if _cfgmgr.CM_Get_Parent(ctypes.byref(parent), cur, 0) != CR_SUCCESS:
            break
        cur = parent.value
    return None, None, ""


def read_batteries() -> dict[str, int]:
    """Return {normalized_address: percent} for present Bluetooth battery nodes."""
    by_addr, _by_name = read_batteries_detailed()
    return by_addr


def read_batteries_detailed() -> tuple[dict[str, int], dict[str, int]]:
    """Return (by_address, by_lowercase_name) battery maps.

    Prefer levels found by walking up from HID/XINPUT (same path as Windows Settings
    for Xbox BT). Plain BTHENUM nodes can be stale and only fill gaps.
    """
    by_addr: dict[str, int] = {}
    by_name: dict[str, int] = {}
    trusted: set[str] = set()  # addresses confirmed via HID ancestry
    handle = _setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if handle in (None, INVALID_HANDLE_VALUE):
        return by_addr, by_name
    try:
        index = 0
        data = SP_DEVINFO_DATA()
        data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        id_buf = ctypes.create_unicode_buffer(512)
        nodes: list[tuple[str, int]] = []  # (instance_id, DevInst)
        while _setupapi.SetupDiEnumDeviceInfo(handle, index, ctypes.byref(data)):
            index += 1
            if not _setupapi.SetupDiGetDeviceInstanceIdW(handle, ctypes.byref(data), id_buf, 512, None):
                continue
            nodes.append((id_buf.value or "", data.DevInst))

        # Pass 1: HID / XINPUT / USB → climb to Bluetooth battery (authoritative).
        for instance_id, devinst in nodes:
            upper = instance_id.upper()
            if not (upper.startswith("HID\\") or "XINPUT" in upper or upper.startswith("USB\\")):
                continue
            level, name, parent_id = _walk_battery(devinst)
            if level is None:
                continue
            addr = _address_from_instance_id(parent_id) or _address_from_instance_id(instance_id)
            if addr:
                by_addr[addr] = level
                trusted.add(addr)
            if name:
                by_name[name.lower()] = level

        # Pass 2: BTHENUM / HFP — only fill addresses not already trusted.
        for instance_id, devinst in nodes:
            upper = instance_id.upper()
            if not upper.startswith(_BT_PREFIX):
                continue
            prop_type = wintypes.ULONG()
            value = ctypes.c_ubyte()
            data = SP_DEVINFO_DATA()
            data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            data.DevInst = devinst
            # Re-query property via cfgmgr (SetupDi handle enum already done).
            level = _read_byte_prop(devinst, DEVPKEY_BLUETOOTH_BATTERY)
            if level is None or not (0 <= level <= 100):
                continue
            addr = _address_from_instance_id(instance_id)
            name = (_read_string_prop(devinst, DEVPKEY_DEVICE_FRIENDLY)
                    or _read_string_prop(devinst, DEVPKEY_NAME))
            if addr and addr not in trusted:
                by_addr[addr] = level
            if name and name.lower() not in by_name:
                by_name[name.lower()] = level
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(handle)
    try:
        from ..debuglog import log
        sample = ", ".join(f"{a[-5:]}={v}%" for a, v in list(by_addr.items())[:8])
        log("pnp", f"battery nodes={len(by_addr)} trusted={len(trusted)} names={len(by_name)} {sample}")
    except Exception:
        pass
    return by_addr, by_name
