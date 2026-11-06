"""System-wide per-device input testing and remapping."""
from .codes import PRESETS, label
from .engine import InputMapService
from .profile import INPUT_KINDS, InputProfile, RemapRule, device_key, supports_input

__all__ = [
    "INPUT_KINDS",
    "InputMapService",
    "InputProfile",
    "PRESETS",
    "RemapRule",
    "device_key",
    "label",
    "supports_input",
]
