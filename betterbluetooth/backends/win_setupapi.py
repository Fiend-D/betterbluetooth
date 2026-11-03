"""Read DEVPKEY_Bluetooth_Battery from PnP device nodes via SetupAPI (Windows only)."""
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

DEVPKEY_BLUETOOTH_BATTERY = DEVPROPKEY(GUID.from_string("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}"), 2)

_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
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

_HEX12 = re.compile(r"(?<![0-9A-F])([0-9A-F]{12})(?![0-9A-F])")
_BASE_UUID_TAIL = "00805F9B34FB"


def _address_from_instance_id(instance_id: str) -> str | None:
    candidates = [m for m in _HEX12.findall(instance_id.upper()) if m != _BASE_UUID_TAIL]
    return normalize_address(candidates[-1]) if candidates else None


def read_batteries() -> dict[str, int]:
    """Return {address: percent} for every present Bluetooth devnode exposing a battery level."""
    result: dict[str, int] = {}
    handle = _setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if handle in (None, INVALID_HANDLE_VALUE):
        return result
    try:
        index = 0
        data = SP_DEVINFO_DATA()
        data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        id_buf = ctypes.create_unicode_buffer(512)
        while _setupapi.SetupDiEnumDeviceInfo(handle, index, ctypes.byref(data)):
            index += 1
            if not _setupapi.SetupDiGetDeviceInstanceIdW(handle, ctypes.byref(data), id_buf, 512, None):
                continue
            instance_id = id_buf.value
            if not instance_id.upper().startswith(("BTHENUM\\", "BTHLE", "BTHHFENUM")):
                continue
            prop_type = wintypes.ULONG()
            value = ctypes.c_ubyte()
            ok = _setupapi.SetupDiGetDevicePropertyW(
                handle, ctypes.byref(data), ctypes.byref(DEVPKEY_BLUETOOTH_BATTERY),
                ctypes.byref(prop_type), ctypes.byref(value), 1, None, 0)
            if not ok:
                continue
            address = _address_from_instance_id(instance_id)
            if address and 0 <= value.value <= 100:
                result[address] = value.value
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(handle)
    return result
