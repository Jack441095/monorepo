"""MAP family shape grammar (DS-I07 / R-CVD-1) — testable geometry utilities.

Frozen requirement (EMBER_CVD_VALIDATION_REPORT.md, owner decision OD-4):
  MAP family shape coding (● drums · ■ bass · ▲ synth · ○ vocal) is
  DEFAULT-ON at ALL zoom levels. Sub-categories inherit their family shape.
  Identification never depends on hue alone.

This module provides pure geometry (no JUCE dependency) so the grammar can be
unit-tested and reused by any renderer (JUCE path, web canvas, harness).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

FAMILY_SHAPES: dict[str, str] = {
    "drums": "circle",
    "bass": "square",
    "synth": "triangle",
    "vocal": "hollow-circle",
}

CATEGORY_FAMILY: dict[str, str] = {
    "kick": "drums",
    "snare": "drums",
    "clap": "drums",
    "hihat": "drums",
    "percussion": "drums",
    "bass": "bass",
    "synth": "synth",
    "vocal": "vocal",
}


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def shape_for_category(category: str) -> str:
    """Sub-categories inherit family shape; unknown is dashed-hollow."""
    if category == "unknown":
        return "dashed-hollow"
    family = CATEGORY_FAMILY.get(category)
    if family is None:
        raise KeyError(f"unknown category '{category}'")
    return FAMILY_SHAPES[family]


def shape_vertices(shape: str, centre: Point, size: float) -> list[Point]:
    """Return polygon vertices for a shape at a given point size (HiDPI-safe: vector).

    circle/hollow-circle return an approximation polygon (32 segments) sufficient
    for hit-testing and bounds; renderers may draw true arcs.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    r = size / 2.0
    cx, cy = centre.x, centre.y
    if shape in ("circle", "hollow-circle"):
        segs = 32
        return [
            Point(cx + r * math.cos(2 * math.pi * i / segs),
                  cy + r * math.sin(2 * math.pi * i / segs))
            for i in range(segs)
        ]
    if shape == "square":
        return [Point(cx - r, cy - r), Point(cx + r, cy - r),
                Point(cx + r, cy + r), Point(cx - r, cy + r)]
    if shape == "triangle":
        # Equilateral, apex up.
        return [
            Point(cx, cy - r),
            Point(cx - r * math.sin(math.pi / 3), cy + r * 0.5),
            Point(cx + r * math.sin(math.pi / 3), cy + r * 0.5),
        ]
    raise KeyError(f"unknown shape '{shape}'")


def shape_hit_test(shape: str, centre: Point, size: float, probe: Point) -> bool:
    """Point-in-shape test for dashed proposal handles and map points."""
    r = size / 2.0
    dx, dy = probe.x - centre.x, probe.y - centre.y
    if shape == "square":
        return abs(dx) <= r and abs(dy) <= r
    if shape == "triangle":
        verts = shape_vertices(shape, centre, size)
        # Barycentric-style sign test.
        def sign(p1, p2, p3):
            return (p1.x - p3.x) * (p2.y - p3.y) - (p2.x - p3.x) * (p1.y - p3.y)
        d1 = sign(probe, verts[0], verts[1])
        d2 = sign(probe, verts[1], verts[2])
        d3 = sign(probe, verts[2], verts[0])
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)
    # circles (incl. hollow — ring interior counts as inside for hit purposes)
    return dx * dx + dy * dy <= r * r


def shapes_pairwise_distinct() -> bool:
    """All four family shapes must be geometrically distinct (R-CVD-1 core claim)."""
    values = list(FAMILY_SHAPES.values())
    return len(set(values)) == len(values)


def small_size_legibility_floor_px() -> float:
    """Minimum point size at which shape identity remains readable (frozen comp token)."""
    return 7.0
