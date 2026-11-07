"""Find battery-like bytes in hid-capture.log.

Usage: python packaging/analyze_hid_capture.py hid-capture.log [vid:pid]

The record is split into sessions at connect/disconnect lines (and at gaps
longer than --gap minutes). A battery byte should:
  * change rarely between consecutive samples (sticks/buttons change a lot),
  * within a session mostly move one way (down while playing, up while charging),
  * take more than one value over the whole record.
Candidates are ranked per (device, report id, length, byte offset).
"""
from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict


def parse(path: str, want: str | None):
    sessions: dict[str, int] = defaultdict(int)
    last_ts: dict[str, dt.datetime] = {}
    rows = []  # (device, session, ts, rid, n, bytes)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            ts = dt.datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
            vidpid, rid, n, payload = parts[1], parts[2], parts[3], parts[4]
            if want and vidpid != want:
                continue
            dev = parts[6] if len(parts) > 6 else vidpid
            if payload.startswith(("connect", "disconnect")):
                dev = payload.split(" ", 1)[1]
                sessions[dev] += 1
                last_ts.pop(dev, None)
                continue
            if rid == "-" or not n.isdigit():
                continue
            prev = last_ts.get(dev)
            if prev is not None and (ts - prev).total_seconds() > ARGS.gap * 60:
                sessions[dev] += 1
            last_ts[dev] = ts
            rows.append((dev, sessions[dev], ts, rid, int(n), bytes.fromhex(payload)))
    return rows


def analyze(rows) -> None:
    # One value per sample burst: keep the first report of each (dev, ts, rid, n).
    series: dict[tuple, list] = defaultdict(list)
    seen = set()
    for dev, sess, ts, rid, n, data in rows:
        k = (dev, ts, rid, n)
        if k in seen:
            continue
        seen.add(k)
        series[(dev, rid, n)].append((sess, ts, data))

    for (dev, rid, n), samples in sorted(series.items()):
        if len(samples) < 4:
            continue
        span = samples[-1][1] - samples[0][1]
        n_sess = len({s for s, _, _ in samples})
        print(f"\n== {dev} report {rid} len {n}: {len(samples)} samples, "
              f"{n_sess} sessions, {span}")
        cands = []
        for off in range(1, n):
            vals = [(s, t, d[off]) for s, t, d in samples if off < len(d)]
            distinct = {v for _, _, v in vals}
            if len(distinct) < 2 or len(distinct) > 40:
                continue
            changes = sum(1 for a, b in zip(vals, vals[1:]) if a[0] == b[0] and a[2] != b[2])
            pairs = sum(1 for a, b in zip(vals, vals[1:]) if a[0] == b[0]) or 1
            churn = changes / pairs
            if churn > 0.35:
                continue
            # Within-session direction consistency.
            ups = downs = 0
            for a, b in zip(vals, vals[1:]):
                if a[0] != b[0] or a[2] == b[2]:
                    continue
                if b[2] > a[2]:
                    ups += 1
                else:
                    downs += 1
            moves = ups + downs
            mono = max(ups, downs) / moves if moves else 0.0
            score = mono * (1 - churn) * min(len(distinct), 10) / 10
            first, last = vals[0][2], vals[-1][2]
            cands.append((score, off, len(distinct), churn, ups, downs, first, last,
                          min(distinct), max(distinct)))
        cands.sort(reverse=True)
        if not cands:
            print("   no slow-moving bytes")
            continue
        print("   off  score distinct churn  up/down   first→last   range")
        for c in cands[:8]:
            score, off, nd, churn, ups, downs, first, last, lo, hi = c
            print(f"   {off:3d}  {score:5.2f} {nd:8d} {churn:5.2f}  {ups:3d}/{downs:<3d}  "
                  f"0x{first:02x}→0x{last:02x}   0x{lo:02x}-0x{hi:02x} ({lo}-{hi})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("device", nargs="?", help="vid:pid filter, e.g. 1949:0402")
    ap.add_argument("--gap", type=float, default=15.0, help="minutes without samples that start a new session")
    ARGS = ap.parse_args()
    analyze(parse(ARGS.log, ARGS.device))
