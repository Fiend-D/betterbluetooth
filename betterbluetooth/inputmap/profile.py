"""Per-device input remap profiles persisted next to app settings."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import config_dir
from ..models import Device, DeviceKind


INPUT_KINDS = frozenset({DeviceKind.KEYBOARD, DeviceKind.GAMEPAD, DeviceKind.MOUSE})


def device_key(dev: Device) -> str:
    """Stable key for profiles: prefer app identity, else Bluetooth MAC / transport id."""
    if getattr(dev, "stable_id", ""):
        return dev.stable_id
    return dev.address.upper() if ":" in dev.address else dev.address


def supports_input(dev: Device) -> bool:
    return dev.kind in INPUT_KINDS


@dataclass
class RemapRule:
    """Map one portable code to another, a chord, or suppress (to_codes empty)."""
    from_code: str
    to_codes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "RemapRule":
        to = raw.get("to_codes")
        if to is None and "to_code" in raw:
            to = [raw["to_code"]] if raw["to_code"] else []
        return cls(from_code=str(raw["from_code"]), to_codes=[str(x) for x in (to or [])])


@dataclass
class InputProfile:
    device_key: str
    kind: str = "keyboard"
    name: str = ""
    enabled: bool = False
    joycon_keepalive: bool = False
    rules: list[RemapRule] = field(default_factory=list)
    # Optional HID identity hints for matching when MAC is missing.
    vid: int | None = None
    pid: int | None = None
    serial: str = ""
    # Manual gamepad layout when X-mode pads spoof as "Xbox Wireless Controller".
    # Empty = auto-detect from name / HID hints. Style id from gamepad_styles.STYLES.
    pad_style: str = ""

    def rule_map(self) -> dict[str, list[str]]:
        return {r.from_code: list(r.to_codes) for r in self.rules}

    @classmethod
    def from_dict(cls, raw: dict) -> "InputProfile":
        rules = [RemapRule.from_dict(r) for r in raw.get("rules") or []]
        return cls(
            device_key=str(raw.get("device_key") or ""),
            kind=str(raw.get("kind") or "keyboard"),
            name=str(raw.get("name") or ""),
            enabled=bool(raw.get("enabled", False)),
            joycon_keepalive=bool(raw.get("joycon_keepalive", False)),
            rules=rules,
            vid=raw.get("vid"),
            pid=raw.get("pid"),
            serial=str(raw.get("serial") or ""),
            pad_style=str(raw.get("pad_style") or ""),
        )


@dataclass
class SavedPreset:
    """User-saved remap scheme that can be applied to any matching-kind device."""
    id: str
    title: str
    kind: str = "keyboard"  # keyboard | gamepad | any
    rules: list[RemapRule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "SavedPreset":
        return cls(
            id=str(raw.get("id") or uuid.uuid4().hex[:10]),
            title=str(raw.get("title") or "未命名预设"),
            kind=str(raw.get("kind") or "keyboard"),
            rules=[RemapRule.from_dict(r) for r in raw.get("rules") or []],
        )


@dataclass
class InputStore:
    """Global toggle + per-device profiles + user presets."""
    master_enabled: bool = False
    profiles: dict[str, InputProfile] = field(default_factory=dict)
    presets: dict[str, SavedPreset] = field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "input_profiles.json"

    @classmethod
    def load(cls) -> "InputStore":
        try:
            raw = json.loads(cls.path().read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        profiles = {}
        for item in raw.get("profiles") or []:
            p = InputProfile.from_dict(item)
            if p.device_key:
                profiles[p.device_key] = p
        presets = {}
        for item in raw.get("presets") or []:
            sp = SavedPreset.from_dict(item)
            if sp.id:
                presets[sp.id] = sp
        return cls(
            master_enabled=bool(raw.get("master_enabled", False)),
            profiles=profiles,
            presets=presets,
        )

    def save(self) -> None:
        payload = {
            "master_enabled": self.master_enabled,
            "profiles": [asdict(p) for p in self.profiles.values()],
            "presets": [asdict(p) for p in self.presets.values()],
        }
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path())

    def ensure(self, dev: Device) -> InputProfile:
        key = device_key(dev)
        profile = self.profiles.get(key)
        if profile is None:
            # Migrate legacy MAC-keyed profile onto the stable identity.
            legacy = self._find_legacy(dev)
            if legacy is not None:
                old_key = legacy.device_key
                legacy.device_key = key
                self.profiles[key] = legacy
                if old_key != key:
                    self.profiles.pop(old_key, None)
                profile = legacy
            else:
                profile = InputProfile(device_key=key, kind=dev.kind.value, name=dev.name)
                self.profiles[key] = profile
        profile.name = dev.name or profile.name
        profile.kind = dev.kind.value
        return profile

    def _find_legacy(self, dev: Device) -> InputProfile | None:
        addr = (dev.address or "").upper()
        if addr and addr in self.profiles:
            return self.profiles[addr]
        # Also try colonless / hyphen forms.
        compact = re.sub(r"[^0-9A-F]", "", addr)
        if compact:
            for key, profile in self.profiles.items():
                if re.sub(r"[^0-9A-F]", "", key.upper()) == compact:
                    return profile
        return None

    def rekey_profile(self, from_keys: list[str], to_key: str) -> bool:
        """Move a profile from any legacy key onto stable_id."""
        if not to_key:
            return False
        if to_key in self.profiles:
            # Drop duplicates under old keys.
            for k in from_keys:
                if k and k != to_key:
                    self.profiles.pop(k, None)
            return False
        for k in from_keys:
            if not k or k == to_key:
                continue
            p = self.profiles.pop(k, None)
            if p is not None:
                p.device_key = to_key
                self.profiles[to_key] = p
                return True
        return False

    def save_preset_from_profile(self, profile: InputProfile, title: str) -> SavedPreset:
        pid = f"user_{uuid.uuid4().hex[:8]}"
        preset = SavedPreset(
            id=pid,
            title=title.strip() or f"{profile.name or '设备'} 方案",
            kind=profile.kind or "keyboard",
            rules=[RemapRule(from_code=r.from_code, to_codes=list(r.to_codes)) for r in profile.rules],
        )
        self.presets[pid] = preset
        return preset

    def apply_saved_preset(self, profile: InputProfile, preset_id: str) -> bool:
        preset = self.presets.get(preset_id)
        if preset is None:
            return False
        by_from = {r.from_code: r for r in profile.rules}
        for rule in preset.rules:
            by_from[rule.from_code] = RemapRule(from_code=rule.from_code, to_codes=list(rule.to_codes))
        profile.rules = list(by_from.values())
        self.profiles[profile.device_key] = profile
        return True

    def active_profiles(self) -> list[InputProfile]:
        if not self.master_enabled:
            return []
        return [p for p in self.profiles.values() if p.enabled]
