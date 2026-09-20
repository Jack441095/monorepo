"""Synthetic SLO search/MAP benchmark.

This is an isolated proxy, not a production SLO measurement. It compares the
observed substring scan with a small token inverted index and compares full
point hit-testing with viewport-cell culling. Inputs are deterministic so the
results can be rerun and compared across machines.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmarks" / "search_and_map_results.json"
SIZES = (500, 2_000, 5_000, 10_000, 25_000)
REPEATS = 9
SEED = 20260822
QUERIES = ("kick", "dark", "vocal", "120", "texture")
VOCABULARY = (
    "kick", "snare", "clap", "hat", "bass", "vocal", "texture", "dark",
    "bright", "warm", "drum", "loop", "one", "shot", "120", "128",
)


def make_samples(count: int) -> list[dict[str, object]]:
    random.seed(SEED + count)
    samples = []
    for index in range(count):
        words = random.sample(VOCABULARY, 5)
        samples.append({
            "name": f"{words[0]}_{index:05d}",
            "key": words[1],
            "category": words[2],
            "tags": " ".join(words[3:]),
            "bpm": words[4],
        })
    return samples


def searchable(sample: dict[str, object]) -> str:
    return " ".join(str(sample[field]) for field in ("name", "key", "category", "tags", "bpm")).lower()


def linear_search(samples: list[dict[str, object]], query: str) -> list[int]:
    query = query.lower()
    return [index for index, sample in enumerate(samples) if query in searchable(sample)]


def build_token_index(samples: list[dict[str, object]]) -> dict[str, set[int]]:
    index: dict[str, set[int]] = {}
    for sample_index, sample in enumerate(samples):
        for token in searchable(sample).replace("_", " ").split():
            index.setdefault(token, set()).add(sample_index)
    return index


def indexed_search(index: dict[str, set[int]], query: str) -> list[int]:
    tokens = query.lower().split()
    if not tokens:
        return []
    candidates = set.intersection(*(index.get(token, set()) for token in tokens))
    return sorted(candidates)


def measure(callable_, *args) -> float:
    start = time.perf_counter_ns()
    callable_(*args)
    return (time.perf_counter_ns() - start) / 1_000_000


def map_full_scan(points: list[tuple[float, float]], viewport: tuple[float, float, float, float]) -> int:
    left, top, right, bottom = viewport
    return sum(left <= x <= right and top <= y <= bottom for x, y in points)


def map_cell_cull(cells: dict[tuple[int, int], list[tuple[float, float]]], viewport: tuple[float, float, float, float], cell_size: float) -> int:
    left, top, right, bottom = viewport
    first_x, last_x = int(left // cell_size), int(right // cell_size)
    first_y, last_y = int(top // cell_size), int(bottom // cell_size)
    visible = 0
    for cell_x in range(first_x, last_x + 1):
        for cell_y in range(first_y, last_y + 1):
            for x, y in cells.get((cell_x, cell_y), ()):
                visible += left <= x <= right and top <= y <= bottom
    return visible


def make_points(count: int) -> list[tuple[float, float]]:
    random.seed(SEED + count + 100)
    return [(random.random() * 1000, random.random() * 1000) for _ in range(count)]


def benchmark_size(count: int) -> dict[str, object]:
    samples = make_samples(count)
    index = build_token_index(samples)
    search_rows = []
    for query in QUERIES:
        linear_times = [measure(linear_search, samples, query) for _ in range(REPEATS)]
        indexed_times = [measure(indexed_search, index, query) for _ in range(REPEATS)]
        linear_result = linear_search(samples, query)
        indexed_result = indexed_search(index, query)
        # Token lookup is intentionally measured as exact-token retrieval. It is
        # a candidate architecture check, not a claim of semantic equivalence.
        search_rows.append({
            "query": query,
            "linear_matches": len(linear_result),
            "indexed_matches": len(indexed_result),
            "linear_median_ms": round(statistics.median(linear_times), 4),
            "indexed_median_ms": round(statistics.median(indexed_times), 4),
            "indexed_speedup": round(statistics.median(linear_times) / max(statistics.median(indexed_times), 0.000001), 2),
        })

    points = make_points(count)
    cells: dict[tuple[int, int], list[tuple[float, float]]] = {}
    cell_size = 50.0
    for point in points:
        cells.setdefault((int(point[0] // cell_size), int(point[1] // cell_size)), []).append(point)
    viewport = (400.0, 400.0, 600.0, 600.0)
    full_times = [measure(map_full_scan, points, viewport) for _ in range(REPEATS)]
    culled_times = [measure(map_cell_cull, cells, viewport, cell_size) for _ in range(REPEATS)]
    full_visible = map_full_scan(points, viewport)
    culled_visible = map_cell_cull(cells, viewport, cell_size)
    return {
        "sample_count": count,
        "search": search_rows,
        "map": {
            "viewport_area_fraction": 0.04,
            "visible_points": full_visible,
            "culled_visible_points": culled_visible,
            "full_scan_median_ms": round(statistics.median(full_times), 4),
            "cell_cull_median_ms": round(statistics.median(culled_times), 4),
            "cell_cull_speedup": round(statistics.median(full_times) / max(statistics.median(culled_times), 0.000001), 2),
        },
    }


def main() -> None:
    result = {
        "version": "px-slo-search-map-v1",
        "environment": "Python synthetic proxy; deterministic random fixtures",
        "seed": SEED,
        "repeats": REPEATS,
        "sizes": [benchmark_size(size) for size in SIZES],
        "limitations": [
            "Does not invoke JUCE, the production HNSW index, or the production QuadTree.",
            "Indexed search uses exact tokens and therefore is not behaviorally identical to substring search.",
            "Use results for architecture direction only; validate with a production-shaped fixture before promotion.",
        ],
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
