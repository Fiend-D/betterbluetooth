"""Windows input: Raw Input for device identity + low-level keyboard hook for remapping.

Coverage is most desktop apps. Games that read exclusive Raw Input may bypass the hook.
"""
from __future__ import annotations

import ctypes
import re
import threading
import time
from ctypes import wintypes
from typing import Any

from .base import InputBackend, InputEvent
from .codes import KEY_TO_VK, VK_TO_KEY, label as code_label
from .profile import InputProfile

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Some Python builds (notably under Wine) omit a few HANDLE aliases from wintypes.
for _alias in ("HCURSOR", "HICON", "HBRUSH", "HMENU"):
    if not hasattr(wintypes, _alias):
        setattr(wintypes, _alias, wintypes.HANDLE)

WH_KEYBOARD_LL = 13
WM_INPUT = 0x00FF
WM_QUIT = 0x0012
WM_APP = 0x8000
WM_HOOK_SYNC = WM_APP + 41  # install/remove LL hook on input thread
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
RI_KEY_BREAK = 1
RID_INPUT = 0x10000003
RIM_TYPEKEYBOARD = 1
RIDEV_INPUTSINK = 0x00000100
HC_ACTION = 0
LLKHF_INJECTED = 0x10

_MAC = re.compile(r"([0-9A-F]{2}(?::[0-9A-F]{2}){5})")


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD)]


# LRESULT is pointer-sized; c_long truncates on Win64 and SetWindowsHookEx then fails.
LRESULT = ctypes.c_ssize_t
LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
HWND_MESSAGE = wintypes.HWND(-3)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND), ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD), ("pt", POINT),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def _device_name(handle) -> str:
    size = wintypes.UINT(0)
    user32.GetRawInputDeviceInfoW(handle, 0x20000007, None, ctypes.byref(size))  # RIDI_DEVICENAME
    if not size.value:
        return ""
    buf = ctypes.create_unicode_buffer(size.value)
    user32.GetRawInputDeviceInfoW(handle, 0x20000007, buf, ctypes.byref(size))
    return buf.value or ""


class WindowsHookBackend(InputBackend):
    name = "Windows RawInput"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._devices: list[dict] = []
        self._profiles: dict[str, InputProfile] = {}
        self._master = False
        self._test_target: str | None = None
        self._lock = threading.Lock()
        self._handle_key: dict[int, str] = {}  # raw device handle → profile key
        self._last_raw: dict[str, Any] = {"key": None, "vk": 0, "t": 0.0}
        self._hook = None
        self._proc = None
        self._wndproc = None
        self._hwnd = None
        self._hinst = None

    def capability(self) -> dict:
        return {
            "test": True,
            "remap": True,
            "message": "按键测试与映射已就绪（多数应用生效；部分独占输入的游戏可能绕过）",
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._thread_main, name="bb-input-win", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        tid = self._thread_id
        if tid:
            user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        self._thread_id = 0

    def sync_devices(self, devices: list[dict]) -> None:
        with self._lock:
            self._devices = list(devices)
        self._refresh_handle_map()

    def set_profiles(self, profiles: list[InputProfile], master_enabled: bool) -> None:
        with self._lock:
            self._profiles = {p.device_key: p for p in profiles}
            self._master = master_enabled
        self._refresh_handle_map()
        self._request_hook_sync()

    def set_test_target(self, device_key: str | None) -> None:
        with self._lock:
            self._test_target = device_key
        self._refresh_handle_map()
        self._request_hook_sync()

    def _keyboard_remap_profiles(self) -> list[InputProfile]:
        with self._lock:
            if not self._master:
                return []
            return [
                p for p in self._profiles.values()
                if p.enabled and p.kind == "keyboard" and p.rules
            ]

    def _sole_keyboard_remap(self) -> InputProfile | None:
        profiles = self._keyboard_remap_profiles()
        return profiles[0] if len(profiles) == 1 else None

    def _hook_wanted(self) -> bool:
        """LL hook only while remapping or testing — otherwise wired keyboards stay untouched."""
        with self._lock:
            if self._test_target:
                return True
            if not self._master:
                return False
            return any(
                p.enabled and p.kind == "keyboard" and p.rules
                for p in self._profiles.values()
            )

    def _request_hook_sync(self) -> None:
        tid = self._thread_id
        if tid:
            user32.PostThreadMessageW(tid, WM_HOOK_SYNC, 0, 0)

    @staticmethod
    def _looks_bluetooth_path(name: str) -> bool:
        u = (name or "").upper()
        return any(tok in u for tok in ("BTHENUM", "BTHLE", "BTHHF", "BLUETOOTH", "BTH\\"))

    def _refresh_handle_map(self) -> None:
        count = wintypes.UINT(0)
        user32.GetRawInputDeviceList(None, ctypes.byref(count), ctypes.sizeof(ctypes.c_void_p) * 2)
        if not count.value:
            return

        class RAWINPUTDEVICELIST(ctypes.Structure):
            _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]

        arr = (RAWINPUTDEVICELIST * count.value)()
        n = wintypes.UINT(count.value)
        if user32.GetRawInputDeviceList(arr, ctypes.byref(n), ctypes.sizeof(RAWINPUTDEVICELIST)) == 0xFFFFFFFF:
            return
        with self._lock:
            devices = list(self._devices)
            test = self._test_target
        sole = self._sole_keyboard_remap()
        sole_key = sole.device_key if sole is not None else None
        mapping: dict[int, str] = {}
        for entry in arr:
            if entry.dwType != RIM_TYPEKEYBOARD:
                continue
            name = _device_name(entry.hDevice).upper()
            mac = None
            m = _MAC.search(name.replace("-", ":"))
            if m:
                mac = m.group(1)
            matched: str | None = None
            for d in devices:
                key = d["key"]
                addr = (d.get("address") or "").upper().replace(":", "").replace("-", "")
                dname = (d.get("name") or "").upper()
                if mac and addr and mac.replace(":", "") in addr:
                    matched = key
                    break
                if dname and (dname in name or name in dname):
                    matched = key
                    break
            # Never attach a sole BT remap profile to a wired/USB keyboard path —
            # that was swallowing the user's local keyboard while the app was open.
            if matched is None and sole_key and self._looks_bluetooth_path(name):
                matched = sole_key
            if matched is None and test and self._looks_bluetooth_path(name):
                matched = test
            if matched is not None:
                mapping[int(entry.hDevice)] = matched
        with self._lock:
            self._handle_key = mapping

    def _match_profile(self, key: str | None) -> InputProfile | None:
        if not key:
            return None
        with self._lock:
            if not self._master:
                return None
            p = self._profiles.get(key)
            if p and p.enabled and p.kind == "keyboard" and p.rules:
                return p
        return None

    def remap_runtime_status(self) -> str:
        profiles = self._keyboard_remap_profiles()
        if not profiles:
            if self._test_target:
                return "按键测试中（已临时安装键盘钩子）"
            if not self._master:
                return "总开关未开启（设置 → 系统级按键映射）；未安装键盘钩子"
            return "已开启总开关，但没有已启用的键盘映射规则；未安装键盘钩子"
        if self._hook is None:
            return "键盘钩子未安装（无需管理员；请完全退出后重开应用）"
        if len(profiles) == 1:
            return f"系统改键生效中：{profiles[0].name or profiles[0].device_key}（仅改已识别的蓝牙键盘）"
        return f"系统改键已启用 {len(profiles)} 套方案（多键盘时依赖设备识别，可能不稳定）"

    def _thread_main(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._wndproc = WNDPROC(self._window_proc)
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASS()
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = hinst
        cls.lpszClassName = "BetterBluetoothInput"
        atom = user32.RegisterClassW(ctypes.byref(cls))
        if not atom:
            # Already registered from a previous run in-process is fine.
            err = ctypes.get_last_error()
            if err not in (0, 1410):  # ERROR_CLASS_ALREADY_EXISTS
                self._status(f"注册输入窗口类失败（错误 {err}）")
        # Message-only window: reliable WM_INPUT sink without a visible HWND.
        hwnd = user32.CreateWindowExW(
            0, "BetterBluetoothInput", "BBInput", 0,
            0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
        self._hwnd = hwnd
        if not hwnd:
            self._status(f"创建输入窗口失败（错误 {ctypes.get_last_error()}）")
        rid = (RAWINPUTDEVICE * 1)()
        rid[0].usUsagePage = 0x01
        rid[0].usUsage = 0x06  # keyboard
        rid[0].dwFlags = RIDEV_INPUTSINK
        rid[0].hwndTarget = hwnd
        if hwnd and not user32.RegisterRawInputDevices(rid, 1, ctypes.sizeof(RAWINPUTDEVICE)):
            self._status(f"注册 Raw Input 失败（错误 {ctypes.get_last_error()}）")
        self._refresh_handle_map()
        # Keep a strong reference — GC of the callback silently breaks the hook.
        self._proc = LowLevelKeyboardProc(self._ll_keyboard)
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, LowLevelKeyboardProc, wintypes.HINSTANCE, wintypes.DWORD,
        ]
        self._hinst = hinst
        # Do NOT install WH_KEYBOARD_LL until remapping / testing needs it.
        # A global LL hook at launch was freezing wired keyboards for some users.
        self._apply_hook_state()
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOOK_SYNC:
                self._apply_hook_state()
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        if hwnd:
            user32.DestroyWindow(hwnd)
        self._hwnd = None

    def _apply_hook_state(self) -> None:
        want = self._hook_wanted()
        if want and not self._hook:
            # WH_KEYBOARD_LL runs in this process; hMod must be NULL (PyInstaller/frozen
            # GetModuleHandleW(None) often makes SetWindowsHookEx fail even as admin).
            self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
            if not self._hook:
                hinst = getattr(self, "_hinst", None) or kernel32.GetModuleHandleW(None)
                self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, hinst, 0)
            if not self._hook:
                err = ctypes.get_last_error()
                self._status(f"安装键盘钩子失败（错误 {err}；通常无需管理员，请重启应用后重试）")
            else:
                self._status("键盘钩子已就绪（映射/测试中）")
        elif not want and self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._status("键盘钩子已卸载（无活动映射）")

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            self._on_raw_input(lparam)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_raw_input(self, lparam) -> None:
        size = wintypes.UINT(0)
        user32.GetRawInputData(lparam, RID_INPUT, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        if not size.value:
            return
        buf = ctypes.create_string_buffer(size.value)
        if user32.GetRawInputData(lparam, RID_INPUT, buf, ctypes.byref(size),
                                  ctypes.sizeof(RAWINPUTHEADER)) != size.value:
            return
        raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
        if raw.header.dwType != RIM_TYPEKEYBOARD:
            return
        handle = int(raw.header.hDevice) if raw.header.hDevice else 0
        with self._lock:
            key = self._handle_key.get(handle)
            test = self._test_target
        vk = int(raw.keyboard.VKey)
        pressed = (raw.keyboard.Flags & RI_KEY_BREAK) == 0
        # Only record correlation for handles we mapped (BT / matched). Wired
        # keyboards must not stamp _last_raw with a remap/test profile key.
        self._last_raw = {"key": key, "vk": vk, "t": time.monotonic(), "pressed": pressed}
        if key and test == key:
            code = VK_TO_KEY.get(vk, f"VK_{vk:02X}")
            self._emit(InputEvent(key, code, pressed, code_label(code)))

    def _ll_keyboard(self, ncode, wparam, lparam):
        # Any exception escaping an LL hook can swallow / freeze all keyboards.
        try:
            if ncode == HC_ACTION:
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if info.flags & LLKHF_INJECTED:
                    return user32.CallNextHookEx(self._hook, ncode, wparam, lparam)
                vk = int(info.vkCode)
                down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                up = wparam in (WM_KEYUP, WM_SYSKEYUP)
                if not (down or up):
                    return user32.CallNextHookEx(self._hook, ncode, wparam, lparam)

                last = self._last_raw
                with self._lock:
                    test = self._test_target

                # UI test feedback only when Raw Input already pinned the event to
                # the test device — never attribute wired-keyboard presses to it.
                if test:
                    recent_raw = (
                        last.get("key") == test
                        and last.get("vk") == vk
                        and time.monotonic() - float(last.get("t") or 0) < 0.08
                    )
                    if recent_raw:
                        code = VK_TO_KEY.get(vk)
                        if code:
                            self._emit(InputEvent(test, code, down, code_label(code)))

                # Remap ONLY when Raw Input correlated this key to a profile device.
                # Do NOT fall back to "sole keyboard profile" — that remapped the
                # wired keyboard whenever a single BT remap scheme was enabled.
                profile = None
                recent = (
                    last.get("key")
                    and last.get("vk") == vk
                    and time.monotonic() - float(last.get("t") or 0) < 0.08
                )
                if recent:
                    profile = self._match_profile(last.get("key"))

                if profile is not None:
                    code = VK_TO_KEY.get(vk)
                    rules = profile.rule_map()
                    if code and code in rules:
                        targets = rules[code]
                        for to in targets:
                            tvk = KEY_TO_VK.get(to)
                            if tvk is not None:
                                self._send_vk(tvk, down)
                        return 1  # swallow original (also when targets empty = disable)
        except Exception:
            pass
        try:
            return user32.CallNextHookEx(self._hook, ncode, wparam, lparam)
        except Exception:
            return 0

    @staticmethod
    def _send_vk(vk: int, down: bool) -> None:
        inp = INPUT()
        inp.type = 1  # INPUT_KEYBOARD
        flags = 0 if down else 2  # KEYEVENTF_KEYUP
        # Mark extended keys so arrows / Ins / Del etc. inject correctly.
        if vk in {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C}:
            flags |= 1  # KEYEVENTF_EXTENDEDKEY
        inp.union.ki = KEYBDINPUT(vk, 0, flags, 0, None)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
