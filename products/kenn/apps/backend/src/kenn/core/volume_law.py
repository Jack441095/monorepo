"""Live's mixer volume fader law: dB <-> the raw 0..1 value Live stores.

Live's fader is not 10^(dB/20): raw 0.85 is 0 dB and raw 1.0 is +6 dB. KENN
converts through a table of Live's own display strings (``str_for_value`` on
the mixer volume parameter, read-only) written by
``tooling/scripts/measure_live_volume_law.py`` to ``live_volume_law.json``.

Until that table exists, KENN uses the Compressor Threshold table measured on
real Live on 2026-09-21 (device_units.py). It has the same range as the fader
(-inf..+6 dB, raw 0.85 = 0 dB), but that it shares the fader's taper is an
assumption, so ``law().measured`` is False and the source says so.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TABLE_PATH = Path(__file__).with_name("live_volume_law.json")
_DB_TEXT = re.compile(r"^\s*([-+]?(?:inf|\d+(?:\.\d+)?))\s*dB\s*$", re.IGNORECASE)

# (raw, dB) from the Compressor Threshold profile in device_units.py.
_PROVISIONAL = (
    (0.05, -57.2), (0.1, -48.6), (0.15, -41.0), (0.2, -34.4), (0.25, -28.8), (0.3, -24.2),
    (0.35, -20.6), (0.4, -18.0), (0.45, -16.0), (0.5, -14.0), (0.55, -12.0), (0.6, -10.0),
    (0.65, -8.0), (0.7, -6.0), (0.75, -4.0), (0.8, -2.0), (0.85, 0.0), (0.9, 2.0),
    (0.95, 4.0), (1.0, 6.0),
)


@dataclass(frozen=True)
class VolumeLaw:
    points: tuple[tuple[float, float], ...]  # (raw, dB), both strictly ascending, finite dB
    measured: bool
    source: str

    @property
    def max_db(self) -> float:
        return self.points[-1][1]

    @property
    def min_db(self) -> float:
        return self.points[0][1]


def parse_db(text: str) -> float | None:
    """Live's volume display ("-6.0 dB", "-inf dB") as a float, or None."""
    match = _DB_TEXT.match(str(text))
    if not match:
        return None
    value = match.group(1).lower()
    return -math.inf if value.endswith("inf") else float(value)


def clean_points(samples: list[tuple[float, str]]) -> list[tuple[float, float]]:
    """(raw, display) samples to strictly ascending (raw, dB) points.

    Live shows one decimal, so neighbouring raw values share a display; each
    run of equal displays becomes one point at the run's middle raw value.
    """
    runs: list[list[float]] = []
    run_db: list[float] = []
    for raw, text in sorted(samples):
        db = parse_db(text)
        if db is None or not math.isfinite(db):
            continue
        if run_db and run_db[-1] == db:
            runs[-1].append(raw)
        else:
            runs.append([raw])
            run_db.append(db)
    points: list[tuple[float, float]] = []
    for raws, db in zip(runs, run_db):
        raw = (raws[0] + raws[-1]) / 2.0
        if not points or (db > points[-1][1] and raw > points[-1][0]):
            points.append((round(raw, 6), db))
    return points


@lru_cache(maxsize=1)
def law() -> VolumeLaw:
    try:
        data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        points = tuple((float(raw), float(db)) for raw, db in data["points"])
        if len(points) >= 2 and all(b[0] > a[0] and b[1] > a[1] for a, b in zip(points, points[1:])):
            return VolumeLaw(points, True, f"measured in Live {data.get('live_version', '?')} on {data.get('measured_at', '?')}")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return VolumeLaw(_PROVISIONAL, False, "provisional: Compressor Threshold table, fader not yet measured")


def _interpolate(x: float, xs: list[float], ys: list[float]) -> float:
    for i in range(1, len(xs)):
        if x <= xs[i]:
            span = xs[i] - xs[i - 1]
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / span
    return ys[-1]


def db_to_raw(db: float) -> float | None:
    """Live's raw fader value for a dB level, or None outside the known table."""
    table = law()
    if not math.isfinite(db) or db < table.min_db or db > table.max_db:
        return None
    raws = [p[0] for p in table.points]
    dbs = [p[1] for p in table.points]
    return round(_interpolate(db, dbs, raws), 6)


def raw_to_db(raw: float) -> float | None:
    """The dB level Live shows for a raw fader value (-inf at 0), or None below the table."""
    table = law()
    if raw <= 0.0:
        return -math.inf
    if raw < table.points[0][0] or raw > table.points[-1][0]:
        return None
    raws = [p[0] for p in table.points]
    dbs = [p[1] for p in table.points]
    return _interpolate(raw, raws, dbs)


def unity_raw() -> float:
    """Raw fader value for 0 dB."""
    return db_to_raw(0.0) or 0.85
