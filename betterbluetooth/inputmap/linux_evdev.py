"""Linux input: evdev for testing, grab + uinput for system-wide keyboard remapping."""
from __future__ import annotations

import glob
import os
import re
import select
import threading
import time
from typing import Any

from .base import InputBackend, InputEvent
from .codes import label as code_label
from .profile import InputProfile

_MAC = re.compile(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})", re.I)
_VIRTUAL_NAME_PREFIX = "BB Remap "

try:
    import evdev
    from evdev import UInput, ecodes
except ImportError:  # pragma: no cover
    evdev = None  # type: ignore
    UInput = None  # type: ignore
    ecodes = None  # type: ignore


def _norm_mac(text: str) -> str | None:
    m = _MAC.search(text.replace("-", ":").lower())
    return m.group(1).upper() if m else None


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _can_write_uinput() -> bool:
    path = "/dev/uinput"
    return os.path.exists(path) and os.access(path, os.W_OK)


def _uinput_help() -> str:
    return (
        "系统改键需要 /dev/uinput 写权限（当前没有）。"
        "临时生效：sudo chmod 666 /dev/uinput"
        "；永久生效：sudo bash <安装目录>/setup-input-remap.sh 后重新登录。"
    )


def _is_our_virtual(name: str) -> bool:
    return (name or "").startswith(_VIRTUAL_NAME_PREFIX)


class LinuxEvdevBackend(InputBackend):
    name = "Linux evdev"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._devices: list[dict] = []
        self._profiles: dict[str, InputProfile] = {}
        self._master = False
        self._test_target: str | None = None
        self._lock = threading.Lock()
        self._open: dict[str, Any] = {}
        self._uinputs: dict[str, Any] = {}
        self._path_key: dict[str, str] = {}
        self._grabbed: set[str] = set()
        self._perm_warned = False
        self._uinput_warned = False
        self._active_remap_names: set[str] = set()
        self._inject_errors = 0

    def capability(self) -> dict:
        if evdev is None:
            return {"test": False, "remap": False,
                    "message": "输入模块未正确打包，请重新下载完整安装包"}
        try:
            paths = list(evdev.list_devices())
        except PermissionError:
            return {"test": True, "remap": False,
                    "message": "无法访问 /dev/input。请执行：sudo usermod -aG input $USER 后重新登录"}
        except OSError as e:
            return {"test": False, "remap": False, "message": f"无法枚举输入设备：{e}"}

        can_list = bool(paths)
        can_uinput = _can_write_uinput()
        if can_list and can_uinput:
            return {"test": True, "remap": True,
                    "message": "按键测试与系统改键已就绪（对本设备打开「启用映射」）"}
        if can_list and not can_uinput:
            return {"test": True, "remap": False, "message": _uinput_help()}
        nodes = glob.glob("/dev/input/event*")
        if nodes:
            return {"test": True, "remap": False,
                    "message": "无法打开输入设备（需加入 input 组并允许 /dev/uinput）"}
        return {"test": True, "remap": False, "message": "未发现输入设备节点"}

    def remap_runtime_status(self) -> str:
        with self._lock:
            names = sorted(self._active_remap_names)
            master = self._master
            enabled = [p for p in self._profiles.values() if p.enabled and p.rules]
        if not master:
            return "总开关未开启（设置 → 系统级按键映射）"
        if not enabled:
            return "已开启总开关，但当前设备未启用或没有映射规则"
        if not _can_write_uinput():
            return _uinput_help()
        if names:
            return f"系统改键生效中：{', '.join(names)}"
        return "已启用映射，但未匹配到物理键盘"

    def start(self) -> None:
        if evdev is None or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bb-input-linux", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._close_all()

    def sync_devices(self, devices: list[dict]) -> None:
        with self._lock:
            self._devices = list(devices)
        self._wake.set()

    def set_profiles(self, profiles: list[InputProfile], master_enabled: bool) -> None:
        with self._lock:
            self._profiles = {p.device_key: p for p in profiles}
            self._master = master_enabled
        self._wake.set()

    def set_test_target(self, device_key: str | None) -> None:
        with self._lock:
            self._test_target = device_key
        self._wake.set()

    def _close_all(self) -> None:
        for path, dev in list(self._open.items()):
            try:
                if path in self._grabbed:
                    dev.ungrab()
            except OSError:
                pass
            try:
                dev.close()
            except OSError:
                pass
        self._open.clear()
        self._grabbed.clear()
        self._path_key.clear()
        for ui in self._uinputs.values():
            try:
                ui.close()
            except OSError:
                pass
        self._uinputs.clear()
        self._active_remap_names.clear()

    def _emergency_ungrab(self, reason: str) -> None:
        """Release all grabs so the user can type again."""
        for path in list(self._grabbed):
            dev = self._open.get(path)
            if dev is None:
                self._grabbed.discard(path)
                continue
            try:
                dev.ungrab()
            except OSError:
                pass
            self._grabbed.discard(path)
        self._active_remap_names.clear()
        self._status(f"已释放键盘独占（{reason}）。系统改键已暂停，请关闭「启用映射」后重试。")

    def _match_key(self, path: str, name: str, uniq: str) -> str | None:
        if _is_our_virtual(name):
            return None
        mac = _norm_mac(uniq) or _norm_mac(name) or _norm_mac(path)
        with self._lock:
            devices = list(self._devices)
            test = self._test_target
            remap_targets = []
            if self._master:
                for p in self._profiles.values():
                    if p.enabled and p.rules and p.kind in ("keyboard", "gamepad"):
                        remap_targets.append(p.device_key)
        if mac:
            mac_c = mac.replace(":", "")
            for d in devices:
                addr = (d.get("address") or "").upper().replace(":", "").replace("-", "")
                if addr and (addr == mac_c or mac_c in addr or addr in mac_c):
                    return d["key"]
        cname = _compact(name)
        best: str | None = None
        best_score = 0
        for d in devices:
            dn = _compact(d.get("name") or "")
            if not dn or not cname:
                continue
            if dn == cname:
                return d["key"]
            if dn in cname or cname in dn:
                score = min(len(dn), len(cname))
                if score > best_score:
                    best_score = score
                    best = d["key"]
        if best is not None:
            return best

        candidates: list[str] = []
        if test:
            candidates.append(test)
        if len(remap_targets) == 1 and remap_targets[0] not in candidates:
            # Only MAC/name-matched devices for remap fallback when uniq present.
            if mac or "bluetooth" in (name or "").lower():
                candidates.append(remap_targets[0])
        for cand in candidates:
            kind = next((d.get("kind") for d in devices if d.get("key") == cand), None)
            if self._looks_like(name, kind):
                return cand
        return None

    @staticmethod
    def _looks_like(name: str, kind: str | None) -> bool:
        n = (name or "").lower()
        if _is_our_virtual(name):
            return False
        if kind == "gamepad":
            if any(m in n for m in ("keyboard", "consumer control", "system control")):
                return False
            return True
        if kind == "keyboard":
            if any(m in n for m in ("mouse", "touchpad", "consumer control", "system control")):
                return False
            if "at translated" in n or "builtin" in n:
                return False
            return True
        return True

    def _should_remap(self, key: str) -> InputProfile | None:
        with self._lock:
            if not self._master:
                return None
            p = self._profiles.get(key)
            if p and p.enabled and p.kind in ("keyboard", "gamepad") and p.rules:
                return p
        return None

    def _refresh_handles(self) -> None:
        if evdev is None:
            return
        wanted_paths: set[str] = set()
        active_names: set[str] = set()
        try:
            paths = evdev.list_devices()
        except OSError as e:
            self._status(f"枚举输入设备失败：{e}")
            return
        if not paths:
            nodes = glob.glob("/dev/input/event*")
            with self._lock:
                need = bool(self._test_target) or (
                    self._master and any(p.enabled and p.rules for p in self._profiles.values())
                )
            if nodes and need and not self._perm_warned:
                self._perm_warned = True
                self._status("无法打开 /dev/input：请将用户加入 input 组后重新登录。")
            return
        self._perm_warned = False

        want_remap = False
        with self._lock:
            want_remap = self._master and any(
                p.enabled and p.rules for p in self._profiles.values()
            )
        if want_remap and not _can_write_uinput():
            if not self._uinput_warned:
                self._uinput_warned = True
                self._status(_uinput_help())
            # Make sure we are not holding a grab without injection.
            if self._grabbed:
                self._emergency_ungrab("无 uinput 权限")
        else:
            self._uinput_warned = False

        for path in paths:
            try:
                info = evdev.InputDevice(path)
            except OSError:
                continue
            try:
                name = info.name or ""
                if _is_our_virtual(name):
                    info.close()
                    continue
                caps = info.capabilities()
                if ecodes.EV_KEY not in caps:
                    info.close()
                    continue
                key = self._match_key(path, name, getattr(info, "uniq", "") or "")
                if key is None:
                    info.close()
                    continue
                with self._lock:
                    testing = self._test_target == key
                remapping = self._should_remap(key)
                if not testing and remapping is None:
                    info.close()
                    continue
                if remapping is not None and not _can_write_uinput():
                    remapping = None
                    if not testing:
                        info.close()
                        continue

                wanted_paths.add(path)
                if path in self._open:
                    self._path_key[path] = key
                    if remapping is not None and path not in self._grabbed:
                        ui = self._ensure_uinput(key, self._open[path])
                        if ui is not None:
                            try:
                                self._open[path].grab()
                                self._grabbed.add(path)
                                active_names.add(name or key)
                            except OSError as e:
                                self._status(f"无法独占 {name}：{e}")
                    elif remapping is None and path in self._grabbed:
                        try:
                            self._open[path].ungrab()
                        except OSError:
                            pass
                        self._grabbed.discard(path)
                    elif remapping is not None:
                        active_names.add(name or key)
                    info.close()
                    continue

                self._open[path] = info
                self._path_key[path] = key
                if remapping is not None:
                    ui = self._ensure_uinput(key, info)
                    if ui is None:
                        if not testing:
                            self._open.pop(path, None)
                            self._path_key.pop(path, None)
                            info.close()
                            continue
                    else:
                        try:
                            info.grab()
                            self._grabbed.add(path)
                            active_names.add(name or key)
                        except OSError as e:
                            self._status(f"无法独占 {name}：{e}")
            except OSError:
                try:
                    info.close()
                except OSError:
                    pass

        for path in list(self._open):
            if path not in wanted_paths:
                dev = self._open.pop(path)
                key = self._path_key.pop(path, None)
                try:
                    if path in self._grabbed:
                        dev.ungrab()
                        self._grabbed.discard(path)
                except OSError:
                    pass
                try:
                    dev.close()
                except OSError:
                    pass
                if key and key not in self._path_key.values():
                    ui = self._uinputs.pop(key, None)
                    if ui is not None:
                        try:
                            ui.close()
                        except OSError:
                            pass

        with self._lock:
            self._active_remap_names = active_names

    def _ensure_uinput(self, key: str, info) -> Any | None:
        if key in self._uinputs:
            return self._uinputs[key]
        if not _can_write_uinput():
            return None
        try:
            # Copy capabilities but use a unique name we always filter out of matching.
            ui = UInput.from_device(
                info,
                name=f"{_VIRTUAL_NAME_PREFIX}{info.name or 'Keyboard'}"[:80],
            )
            self._uinputs[key] = ui
            self._inject_errors = 0
            return ui
        except OSError as e:
            self._status(f"创建虚拟键盘失败：{e}")
            return None

    def _inject(self, key: str, path: str, etype: int, ecode: int, value: int) -> bool:
        ui = self._uinputs.get(key)
        if ui is None:
            if path in self._grabbed:
                self._emergency_ungrab("虚拟键盘丢失")
            return False
        try:
            ui.write(etype, ecode, value)
            ui.syn()
            self._inject_errors = 0
            return True
        except OSError as e:
            self._inject_errors += 1
            if self._inject_errors >= 3:
                self._emergency_ungrab(f"注入失败：{e}")
            return False

    def _loop(self) -> None:
        last_refresh = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if self._wake.is_set() or now - last_refresh > 1.5:
                self._wake.clear()
                try:
                    self._refresh_handles()
                except Exception as e:  # noqa: BLE001
                    self._status(f"输入后端错误：{e}")
                    self._emergency_ungrab(str(e))
                last_refresh = now
            if not self._open:
                self._wake.wait(0.4)
                self._wake.clear()
                continue
            try:
                r, _, _ = select.select(list(self._open.values()), [], [], 0.4)
            except (OSError, ValueError):
                self._stop.wait(0.2)
                continue
            for dev in r:
                path = getattr(dev, "path", None) or next(
                    (p for p, d in self._open.items() if d is dev), None)
                if not path:
                    continue
                key = self._path_key.get(path)
                if not key:
                    continue
                try:
                    for event in dev.read():
                        self._handle(key, path, event)
                except OSError:
                    pass

    def _handle(self, key: str, path: str, event) -> None:
        grabbed = path in self._grabbed
        with self._lock:
            testing = self._test_target == key

        # Always forward non-key events when grabbed (MSC/SYN/LED/ABS…).
        if event.type != ecodes.EV_KEY:
            if grabbed:
                # Don't double-syn on SYN itself — just write through.
                ui = self._uinputs.get(key)
                if ui is None:
                    self._emergency_ungrab("虚拟键盘丢失")
                    return
                try:
                    ui.write(event.type, event.code, event.value)
                    if event.type != ecodes.EV_SYN:
                        ui.syn()
                except OSError as e:
                    self._emergency_ungrab(f"注入失败：{e}")
            elif testing and event.type == ecodes.EV_ABS:
                axis = ecodes.ABS.get(event.code, f"ABS_{event.code}")
                if isinstance(axis, list):
                    axis = axis[0]
                self._emit(InputEvent(key, axis, True, f"{axis}={event.value}"))
            return

        name = ecodes.KEY.get(event.code, f"KEY_{event.code}")
        if isinstance(name, list):
            name = name[0]
        pressed = event.value != 0
        if testing and event.value != 2:
            self._emit(InputEvent(key, name, pressed, code_label(name)))

        if not grabbed:
            return

        # Grabbed: must always inject something, or the key is swallowed.
        profile = self._should_remap(key)
        ui = self._uinputs.get(key)
        if ui is None:
            self._emergency_ungrab("虚拟键盘丢失")
            return

        mapping = profile.rule_map() if profile is not None else {}
        targets = mapping.get(name)

        try:
            if targets is None:
                # Passthrough original key.
                ui.write(event.type, event.code, event.value)
            elif not targets:
                # Suppressed — still need SYN so queue stays consistent.
                pass
            else:
                for to_name in targets:
                    code = getattr(ecodes, to_name, None)
                    if code is None and to_name.startswith(("KEY_", "BTN_")):
                        code = ecodes.ecodes.get(to_name)
                    if code is None:
                        continue
                    ui.write(ecodes.EV_KEY, code, event.value)
            ui.syn()
            self._inject_errors = 0
        except OSError as e:
            self._inject_errors += 1
            if self._inject_errors >= 2:
                self._emergency_ungrab(f"注入失败：{e}")
