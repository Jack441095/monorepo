#!/usr/bin/env python3
"""
Summarize realtime playback health from logs/runtime.log.

Usage:
  python tools/rt_log_health.py
  python tools/rt_log_health.py --log logs/runtime.log
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_RE_SLOW = re.compile(r"Slow bar render: ([0-9.]+)ms \(bar=([0-9.]+)ms\)")


def _safe_ratio(a: float, b: float) -> float:
    if b <= 1e-9:
        return 0.0
    return float(a / b)


def summarize_runtime_log(path: Path) -> dict:
    stats = {
        "lines": 0,
        "sessions": 0,
        "buffer_underruns": 0,
        "callback_underflows": 0,
        "portaudio_underflows": 0,
        "slow_bar_count": 0,
        "slow_bar_max_ratio": 0.0,
        "slow_bar_avg_ratio": 0.0,
        "first_ts": "",
        "last_ts": "",
    }
    slow_ratios = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stats["lines"] += 1
        line = str(raw or "")
        m_ts = _TS_RE.match(line)
        if m_ts:
            ts = str(m_ts.group(1))
            if not stats["first_ts"]:
                stats["first_ts"] = ts
            stats["last_ts"] = ts
        if "Startup mode selected" in line:
            stats["sessions"] += 1
        if "BUFFER UNDERRUN #" in line:
            stats["buffer_underruns"] += 1
        if "PortAudio output_underflow" in line:
            stats["portaudio_underflows"] += 1
            stats["callback_underflows"] += 1
        m_slow = _RE_SLOW.search(line)
        if m_slow:
            stats["slow_bar_count"] += 1
            try:
                render_ms = float(m_slow.group(1))
                bar_ms = float(m_slow.group(2))
                ratio = _safe_ratio(render_ms, bar_ms)
            except Exception:
                ratio = 0.0
            slow_ratios.append(ratio)
    if slow_ratios:
        stats["slow_bar_max_ratio"] = float(max(slow_ratios))
        stats["slow_bar_avg_ratio"] = float(sum(slow_ratios) / len(slow_ratios))
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="logs/runtime.log", help="Path to runtime log file")
    args = ap.parse_args()
    log_path = Path(str(args.log)).expanduser().resolve()
    if not log_path.exists():
        print(f"log_not_found={log_path}")
        return 1
    s = summarize_runtime_log(log_path)
    print(f"log_path={log_path}")
    print(f"time_range={s['first_ts']} -> {s['last_ts']}")
    print(f"lines={s['lines']} sessions={s['sessions']}")
    print(
        "underruns="
        f"{s['buffer_underruns']} callback_underflows={s['callback_underflows']} "
        f"portaudio_underflows={s['portaudio_underflows']}"
    )
    print(
        "slow_bars="
        f"{s['slow_bar_count']} avg_ratio={s['slow_bar_avg_ratio']:.2f}x "
        f"max_ratio={s['slow_bar_max_ratio']:.2f}x"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
