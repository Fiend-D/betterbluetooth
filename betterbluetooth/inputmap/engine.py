"""Coordinates input backends with Bluetooth device list and persisted profiles."""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal

from ..models import Device, DeviceKind
from .base import InputBackend, InputEvent
from .codes import PRESETS, label
from .joycon import JoyConKeeper
from .profile import InputProfile, InputStore, RemapRule, device_key, supports_input
from .win_gamepad import WinGamepadPoller


def create_backend() -> InputBackend:
    if sys.platform == "win32":
        from .windows_hook import WindowsHookBackend
        return WindowsHookBackend()
    if sys.platform.startswith("linux"):
        from .linux_evdev import LinuxEvdevBackend
        return LinuxEvdevBackend()
    from .base import InputBackend as _B

    class _Null(_B):
        def capability(self):
            return {"test": False, "remap": False, "message": "当前平台暂不支持输入映射"}

        def start(self): pass
        def stop(self): pass
        def sync_devices(self, devices): pass
        def set_profiles(self, profiles, master_enabled): pass
        def set_test_target(self, device_key): pass

    return _Null()


class InputMapService(QObject):
    eventReceived = Signal(object)   # InputEvent
    statusChanged = Signal(str)
    storeChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.store = InputStore.load()
        self.backend = create_backend()
        self.capability = self.backend.capability()
        self._joycon = JoyConKeeper()
        self._xinput = WinGamepadPoller()
        self._devices: list[Device] = []

        self._test_key: str | None = None
        self.backend.set_callbacks(self._on_event, self._on_status)
        self._joycon.set_on_event(self._on_event)
        self._xinput.set_on_event(self._on_event)

    def start(self) -> None:
        self.backend.start()
        self._joycon.start()
        self._xinput.start()
        self.apply_profiles()

    def stop(self) -> None:
        self._test_key = None
        self.backend.set_test_target(None)
        self._joycon.set_test_target(None)
        self._xinput.set_test_target(None)
        self._joycon.stop()
        self._xinput.stop()
        self.backend.stop()

    def _on_event(self, event: InputEvent) -> None:
        if not event.label and not event.code.startswith("ABS_"):
            event.label = label(event.code)
        self.eventReceived.emit(event)

    def _on_status(self, text: str) -> None:
        self.statusChanged.emit(text)

    def update_devices(self, devices: list[Device]) -> None:
        self._devices = [d for d in devices if supports_input(d)]
        payload = [{
            "key": device_key(d),
            "address": d.address,
            "name": d.name,
            "kind": d.kind.value,
            "connected": d.connected,
        } for d in self._devices]
        self.backend.sync_devices(payload)
        # Names for RawGameController matching (D-mode GamepadSpace etc.).
        pad_names = {
            device_key(d): (d.name or "")
            for d in self._devices
            if d.kind == DeviceKind.GAMEPAD and d.connected
        }
        self._xinput.set_device_names(pad_names)
        # Active gamepad → keyboard remap (Windows inject path).
        remap_key = self._test_key
        remap_rules: dict[str, list[str]] = {}
        remap_on = False
        if remap_key:
            profile = self.store.profiles.get(remap_key)
            if (
                profile
                and profile.enabled
                and self.store.master_enabled
                and profile.kind == "gamepad"
                and profile.rules
            ):
                remap_rules = profile.rule_map()
                remap_on = True
        else:
            # No test page open: remap the enabled gamepad profile, preferring
            # the one whose device is connected (X and D mode are separate devices).
            enabled = [
                p for p in self.store.profiles.values()
                if p.enabled and self.store.master_enabled and p.kind == "gamepad" and p.rules
            ]
            live = [p for p in enabled if p.device_key in pad_names]
            if len(live) == 1 or (not live and len(enabled) == 1):
                enabled = live or enabled
                remap_key = enabled[0].device_key
                remap_rules = enabled[0].rule_map()
                remap_on = True
                pad_names.setdefault(remap_key, enabled[0].name or "")
                self._xinput.set_device_names(pad_names)
        self._xinput.set_remap(remap_rules, remap_on, remap_key)
        # Joy-Con keep-alive / test targets.
        targets = {}
        rules: dict[str, dict[str, list[str]]] = {}
        for d in self._devices:
            if d.kind != DeviceKind.GAMEPAD or not d.connected:
                continue
            key = device_key(d)
            profile = self.store.profiles.get(key)
            name_u = (d.name or "").upper()
            is_jc = "JOY-CON" in name_u or "PRO CONTROLLER" in name_u or key.startswith("switch:")
            if not is_jc:
                continue
            want_keep = bool(profile and profile.joycon_keepalive and self.store.master_enabled)
            want_map = bool(profile and profile.enabled and self.store.master_enabled and profile.rules)
            want_test = self._test_key == key
            if want_keep or want_map or want_test:
                targets[key] = {"address": d.address, "name": d.name}
            if want_map and profile is not None:
                rules[key] = profile.rule_map()
        self._joycon.set_targets(targets, rules)

    def apply_profiles(self) -> None:
        self.backend.set_profiles(list(self.store.profiles.values()), self.store.master_enabled)
        self.update_devices(self._devices)
        self.storeChanged.emit()

    def save(self) -> None:
        self.store.save()
        self.apply_profiles()

    def set_master(self, enabled: bool) -> None:
        self.store.master_enabled = enabled
        self.save()

    def refresh_capability(self) -> dict:
        self.capability = self.backend.capability()
        return self.capability

    def remap_runtime_status(self) -> str:
        fn = getattr(self.backend, "remap_runtime_status", None)
        if callable(fn):
            return fn()
        if not self.capability.get("remap"):
            return self.capability.get("message", "系统改键不可用")
        return "系统改键后端已就绪"

    def profile_for(self, dev: Device) -> InputProfile:
        return self.store.ensure(dev)

    def set_test_target(self, key: str | None) -> None:
        self._test_key = key
        self.backend.set_test_target(key)
        self._joycon.set_test_target(key)
        self._xinput.set_test_target(key)
        # Re-push Joy-Con targets so testing alone opens HID without keepalive.
        self.update_devices(self._devices)
        from ..debuglog import log
        log("input", f"test_target={key!r} xinput={'on' if key else 'off'}")

    def apply_preset(self, profile: InputProfile, preset_id: str) -> None:
        if preset_id.startswith("user:") or preset_id in self.store.presets:
            pid = preset_id.removeprefix("user:")
            if self.store.apply_saved_preset(profile, pid):
                self.save()
            return
        preset = PRESETS.get(preset_id)
        if not preset:
            return
        _, pairs = preset
        by_from = {r.from_code: r for r in profile.rules}
        for src, dst in pairs:
            by_from[src] = RemapRule(from_code=src, to_codes=[dst] if dst else [])
        profile.rules = list(by_from.values())
        self.store.profiles[profile.device_key] = profile
        self.save()

    def save_user_preset(self, profile: InputProfile, title: str):
        preset = self.store.save_preset_from_profile(profile, title)
        self.save()
        return preset

    def rekey_for_device(self, dev: Device, legacy_keys: list[str]) -> None:
        key = device_key(dev)
        if self.store.rekey_profile(legacy_keys, key):
            self.save()
        else:
            # Still drop duplicate legacy entries if stable profile already exists.
            changed = False
            for k in legacy_keys:
                if k and k != key and k in self.store.profiles:
                    self.store.profiles.pop(k, None)
                    changed = True
            if changed:
                self.save()

    def find_device(self, key: str) -> Device | None:
        for d in self._devices:
            if device_key(d) == key:
                return d
        for d in self._devices:
            if d.address == key or d.stable_id == key:
                return d
        return None
