"""Passive HID input-report recorder for gamepads without a known battery protocol.

Read-only: devices are opened and their input reports read; nothing is ever
written. Samples go to hid-capture.log so a byte that drifts with the battery
can be found later (packaging/analyze_hid_capture.py).

Pads come and go (power off, sleep, charging): every appearance/disappearance
is logged as a connect/disconnect line so analysis can split the record into
sessions, and the first sample is taken as soon as a pad reappears.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import hid

from ..config import data_dir

# Vendors whose battery we already parse from a documented protocol.
_SKIP_VIDS = frozenset({0x054C, 0x057E, 0x2DC8, 0x37D7})
_MIN_GAP = 55.0          # seconds between samples of one device
_READ_WINDOW = 0.4       # seconds of reports per sample
_PER_ID = 3              # reports kept per report id per sample
_MAX_BYTES = 20_000_000  # rotate after ~20 MB

_enabled = False
_lock = threading.Lock()
_last: dict[str, float] = {}
_present: dict[str, str] = {}  # device key → product name, as of the last scan


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)
    if not _enabled:
        _present.clear()
        _last.clear()


def enabled() -> bool:
    return _enabled


def capture_path() -> Path:
    return data_dir() / "hid-capture.log"


def _is_gamepad(entry: dict) -> bool:
    return int(entry.get("usage_page") or 0) == 1 and int(entry.get("usage") or 0) in (4, 5)


def sample(entries: list[dict]) -> None:
    """Record a short burst of input reports from each candidate gamepad."""
    if not _enabled:
        return
    now = time.monotonic()
    lines: list[str] = []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    candidates = []
    seen: dict[str, str] = {}
    for entry in entries:
        vid = int(entry.get("vendor_id") or 0)
        pid = int(entry.get("product_id") or 0)
        if vid in _SKIP_VIDS or not _is_gamepad(entry):
            continue
        serial = (entry.get("serial_number") or "").strip()
        key = f"{vid:04x}:{pid:04x}:{serial or (entry.get('path') or b'').hex()[-16:]}"
        name = (entry.get("product_string") or "").replace("\t", " ")
        seen[key] = name
        candidates.append((key, vid, pid, name, entry.get("path") or b""))
    changed = [k for k in seen if k not in _present] + [k for k in _present if k not in seen]
    for key in changed:
        state = "connect" if key in seen else "disconnect"
        lines.append(f"{stamp}\t{key[:9]}\t-\t-\t{state} {key}\t{seen.get(key) or _present.get(key, '')}")
        for k in [k for k in _last if k.startswith(key + "|")]:
            del _last[k]  # sample right away after a reconnect
    _present.clear()
    _present.update(seen)
    for key, vid, pid, name, path in candidates:
        # One pad can expose several gamepad collections; pace each separately.
        skey = f"{key}|{path.hex()[-12:]}"
        if now - _last.get(skey, 0.0) < _MIN_GAP:
            continue
        _last[skey] = now
        try:
            dev = hid.device()
            dev.open_path(path)
        except OSError as e:
            lines.append(f"{stamp}\t{vid:04x}:{pid:04x}\t-\t-\topen-failed {e}\t{name}")
            continue
        kept: dict[int, int] = {}
        try:
            deadline = time.monotonic() + _READ_WINDOW
            while time.monotonic() < deadline:
                data = dev.read(128, 40)
                if not data:
                    continue
                rid = data[0]
                if kept.get(rid, 0) >= _PER_ID:
                    continue
                kept[rid] = kept.get(rid, 0) + 1
                lines.append(f"{stamp}\t{vid:04x}:{pid:04x}\t{rid:02x}\t{len(data)}\t"
                             f"{bytes(data).hex()}\t{name}\t{key}")
        except OSError as e:
            lines.append(f"{stamp}\t{vid:04x}:{pid:04x}\t-\t-\tread-failed {e}\t{name}")
        finally:
            try:
                dev.close()
            except Exception:
                pass
        if not kept:
            lines.append(f"{stamp}\t{vid:04x}:{pid:04x}\t-\t0\t(no reports)\t{name}")
    if not lines:
        return
    try:
        with _lock:
            p = capture_path()
            if p.exists() and p.stat().st_size > _MAX_BYTES:
                p.replace(p.with_suffix(".log.old"))
            with p.open("a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
    except OSError:
        pass
