from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import APP_NAME

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


def config_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        path = base / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        path = base / APP_NAME.lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        path = base / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        path = base / APP_NAME.lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    refresh_interval: int = 30
    low_battery_threshold: int = 20
    notify_low_battery: bool = True
    notify_connection: bool = False
    theme: str = "system"          # system | light | dark
    tray_style: str = "number"     # see ui.tray.TRAY_STYLES
    tray_colored: bool = False
    flyout_pos: list[int] | None = None
    history_enabled: bool = True
    history_days: int = 30
    autostart: bool = False
    tray_devices: dict[str, bool] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    input_remap_enabled: bool = False

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(cls.path().read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path())

    def show_in_tray(self, address: str, stable_id: str = "") -> bool:
        if stable_id and stable_id in self.tray_devices:
            return self.tray_devices[stable_id]
        if address in self.tray_devices:
            return self.tray_devices[address]
        return True
