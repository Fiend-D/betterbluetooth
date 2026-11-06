from __future__ import annotations

import sqlite3
import time
from pathlib import Path

RECORD_INTERVAL = 10 * 60


class BatteryHistory:
    def __init__(self, path: Path):
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS battery ("
            " address TEXT NOT NULL, ts INTEGER NOT NULL, level INTEGER NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_battery ON battery(address, ts)")
        self._db.commit()
        self._last: dict[str, tuple[int, int]] = {}

    def record(self, address: str, level: int, now: int | None = None) -> None:
        now = now or int(time.time())
        last = self._last.get(address)
        if last is None:
            row = self._db.execute(
                "SELECT ts, level FROM battery WHERE address=? ORDER BY ts DESC LIMIT 1", (address,)
            ).fetchone()
            last = (row[0], row[1]) if row else None
        if last and last[1] == level and now - last[0] < RECORD_INTERVAL:
            return
        self._db.execute("INSERT INTO battery VALUES (?, ?, ?)", (address, now, level))
        self._db.commit()
        self._last[address] = (now, level)

    def query(self, address: str, since: int) -> list[tuple[int, int]]:
        rows = self._db.execute(
            "SELECT ts, level FROM battery WHERE address=? AND ts>=? ORDER BY ts", (address, since)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def last_level(self, address: str) -> tuple[int, int] | None:
        row = self._db.execute(
            "SELECT ts, level FROM battery WHERE address=? ORDER BY ts DESC LIMIT 1", (address,)
        ).fetchone()
        return (row[0], row[1]) if row else None

    def prune(self, days: int) -> None:
        self._db.execute("DELETE FROM battery WHERE ts < ?", (int(time.time()) - days * 86400,))
        self._db.commit()

    def clear(self, address: str | None = None) -> None:
        if address:
            self._db.execute("DELETE FROM battery WHERE address=?", (address,))
            self._last.pop(address, None)
        else:
            self._db.execute("DELETE FROM battery")
            self._last.clear()
        self._db.commit()
        self._db.execute("VACUUM")

    def query_keys(self, keys: list[str], since: int) -> list[tuple[int, int]]:
        """Query history for any of the identity keys (stable_id + known MACs)."""
        keys = [k for k in keys if k]
        if not keys:
            return []
        if len(keys) == 1:
            return self.query(keys[0], since)
        placeholders = ",".join("?" * len(keys))
        rows = self._db.execute(
            f"SELECT ts, level FROM battery WHERE address IN ({placeholders}) AND ts>=? ORDER BY ts",
            (*keys, since),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def rekey(self, from_keys: list[str], to_key: str) -> int:
        """Move history rows from old address keys onto the stable identity key."""
        if not to_key:
            return 0
        moved = 0
        for key in from_keys:
            if not key or key == to_key:
                continue
            cur = self._db.execute(
                "UPDATE battery SET address=? WHERE address=?", (to_key, key)
            )
            moved += cur.rowcount or 0
            self._last.pop(key, None)
        if moved:
            self._db.commit()
        return moved

    def clear_keys(self, keys: list[str]) -> None:
        for key in keys:
            if key:
                self._db.execute("DELETE FROM battery WHERE address=?", (key,))
                self._last.pop(key, None)
        self._db.commit()


def estimate_remaining_hours(points: list[tuple[int, int]]) -> float | None:
    """Estimate hours until empty from the most recent continuous discharge run."""
    if len(points) < 3:
        return None
    run = [points[-1]]
    for ts, level in reversed(points[:-1]):
        prev_ts, prev_level = run[-1]
        if level < prev_level or prev_ts - ts > 3 * 3600:
            break
        run.append((ts, level))
    run.reverse()
    first, last = run[0], run[-1]
    dropped = first[1] - last[1]
    hours = (last[0] - first[0]) / 3600
    if dropped < 3 or hours < 0.25:
        return None
    rate = dropped / hours
    return last[1] / rate
