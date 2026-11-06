"""Stable device identity across re-pairs (Bluetooth MAC can change).

Historically BetterBluetooth keyed everything by the live Bluetooth address.
After remove+re-pair — especially BLE devices with random/resolvable addresses —
the OS often assigns a new MAC, so history and remap profiles looked like a new
device. This registry keeps a stable_id and links every address / fingerprint
seen for that physical device.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import config_dir
from .models import Device, normalize_address

_GENERIC_NAMES = frozenset({
    "keyboard", "mouse", "gamepad", "controller", "headset", "headphones",
    "bluetooth keyboard", "bluetooth mouse", "wireless keyboard", "wireless mouse",
    "bt keyboard", "bt mouse", "hid keyboard", "hid mouse", "unknown",
})


def _norm_addr(addr: str) -> str:
    if not addr:
        return ""
    if ":" in addr or "-" in addr or re.fullmatch(r"[0-9A-Fa-f]{12}", addr.replace(":", "")):
        try:
            return normalize_address(addr)
        except Exception:
            return addr.upper()
    return addr


def _is_generic_name(name: str) -> bool:
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    return len(n) < 3 or n in _GENERIC_NAMES


@dataclass
class IdentityRecord:
    stable_id: str
    addresses: list[str] = field(default_factory=list)  # newest first
    name: str = ""
    kind: str = ""
    system_name: str = ""
    vid: int | None = None
    pid: int | None = None
    serial: str = ""
    last_seen: float = 0.0
    merged_from: list[str] = field(default_factory=list)  # previous address keys absorbed

    @classmethod
    def from_dict(cls, raw: dict) -> "IdentityRecord":
        addrs = [_norm_addr(a) for a in (raw.get("addresses") or []) if a]
        return cls(
            stable_id=str(raw.get("stable_id") or ""),
            addresses=[a for a in addrs if a],
            name=str(raw.get("name") or ""),
            kind=str(raw.get("kind") or ""),
            system_name=str(raw.get("system_name") or ""),
            vid=raw.get("vid"),
            pid=raw.get("pid"),
            serial=str(raw.get("serial") or ""),
            last_seen=float(raw.get("last_seen") or 0),
            merged_from=[str(x) for x in (raw.get("merged_from") or [])],
        )


@dataclass
class IdentityStore:
    records: dict[str, IdentityRecord] = field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "identities.json"

    @classmethod
    def load(cls) -> "IdentityStore":
        try:
            raw = json.loads(cls.path().read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        records = {}
        for item in raw.get("records") or []:
            rec = IdentityRecord.from_dict(item)
            if rec.stable_id:
                records[rec.stable_id] = rec
        return cls(records=records)

    def save(self) -> None:
        payload = {"records": [asdict(r) for r in self.records.values()]}
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path())

    def by_address(self, address: str) -> IdentityRecord | None:
        addr = _norm_addr(address)
        if not addr:
            return None
        for rec in self.records.values():
            if addr in rec.addresses:
                return rec
        return None

    def all_keys(self, stable_id: str) -> list[str]:
        """stable_id + every known address (for history / settings migration)."""
        rec = self.records.get(stable_id)
        if not rec:
            return [stable_id]
        keys = [stable_id, *rec.addresses, *rec.merged_from]
        # Preserve order, drop empties/dupes.
        out: list[str] = []
        seen: set[str] = set()
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def resolve(self, dev: Device, present_addresses: set[str]) -> tuple[str, bool]:
        """Attach / create a stable_id for ``dev``.

        Returns (stable_id, merged) where merged=True if an orphan identity was
        reused (typical after re-pair with a new MAC).
        """
        addr = _norm_addr(dev.address)
        present = {_norm_addr(a) for a in present_addresses}
        now = time.time()
        vid = dev.extra.get("vid") if isinstance(dev.extra, dict) else None
        pid = dev.extra.get("pid") if isinstance(dev.extra, dict) else None
        serial = str((dev.extra or {}).get("serial") or "")

        # 1) Exact live address.
        rec = self.by_address(addr)
        if rec is not None:
            self._touch(rec, dev, addr, vid, pid, serial, now)
            return rec.stable_id, False

        # 2) HID fingerprint (vid+pid+serial) when serial is present.
        if serial and vid is not None and pid is not None:
            for candidate in self.records.values():
                if (
                    candidate.serial == serial
                    and candidate.vid == vid
                    and candidate.pid == pid
                ):
                    self._touch(candidate, dev, addr, vid, pid, serial, now)
                    return candidate.stable_id, True

        # 3) Orphan merge: same distinctive name+kind, none of its addresses currently present.
        name = (dev.name or "").strip()
        kind = dev.kind.value if hasattr(dev.kind, "value") else str(dev.kind)
        if name and not _is_generic_name(name):
            orphans = [
                r for r in self.records.values()
                if (r.name or "").strip().lower() == name.lower()
                and (r.kind or "") == kind
                and not any(a in present for a in r.addresses)
            ]
            if orphans:
                orphans.sort(key=lambda r: r.last_seen, reverse=True)
                best = orphans[0]
                self._touch(best, dev, addr, vid, pid, serial, now)
                return best.stable_id, True

        # 4) Fresh identity — seed stable_id with first address for readable migration.
        stable_id = f"dev_{uuid.uuid4().hex[:12]}"
        rec = IdentityRecord(
            stable_id=stable_id,
            addresses=[addr] if addr else [],
            name=name,
            kind=kind,
            system_name=dev.system_name or "",
            vid=vid if isinstance(vid, int) else None,
            pid=pid if isinstance(pid, int) else None,
            serial=serial,
            last_seen=now,
        )
        self.records[stable_id] = rec
        return stable_id, False

    def _touch(
        self,
        rec: IdentityRecord,
        dev: Device,
        addr: str,
        vid,
        pid,
        serial: str,
        now: float,
    ) -> None:
        if addr and addr not in rec.addresses:
            if rec.addresses:
                rec.merged_from.append(rec.addresses[0])
            rec.addresses.insert(0, addr)
            # Cap history of addresses.
            rec.addresses = rec.addresses[:8]
        if dev.name:
            rec.name = dev.name
        if getattr(dev, "system_name", ""):
            rec.system_name = dev.system_name
        rec.kind = dev.kind.value if hasattr(dev.kind, "value") else str(dev.kind)
        if isinstance(vid, int):
            rec.vid = vid
        if isinstance(pid, int):
            rec.pid = pid
        if serial:
            rec.serial = serial
        rec.last_seen = now

    def forget_address(self, address: str, drop_record: bool = False) -> None:
        """Forget a live address (after OS remove) but keep the identity for re-pair."""
        addr = _norm_addr(address)
        rec = self.by_address(addr)
        if rec is None:
            return
        if drop_record:
            self.records.pop(rec.stable_id, None)
            return
        # Keep address in list so history rekey still finds it; just don't require it live.
        rec.last_seen = time.time()
