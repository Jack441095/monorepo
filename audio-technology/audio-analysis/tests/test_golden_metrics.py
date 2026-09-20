"""Golden-metrics regression guard for the analysis system.

Locks the scalar output of `analyze_wav` over a fixed deterministic corpus so
the upcoming efficiency refactors (shared spectral frontend, numpy/numba
loudness inner loop) can be proven to preserve every number they produce.

If this test fails, EITHER a refactor changed the analysis numbers (investigate
which metric moved and why — the failure message names each one), OR the change
was intentional, in which case regenerate the snapshot:

    python scripts/eval/golden_metrics.py --update

This is a regression guard, not a quality gate — it asserts the numbers did not
move, never that they are good.
"""

from __future__ import annotations

import pytest

golden_metrics = pytest.importorskip(
    "scripts.eval.golden_metrics",
    reason="golden_metrics harness requires the analysis package + numpy",
)


def test_analysis_metrics_match_golden_snapshot() -> None:
    current = golden_metrics._round(golden_metrics.compute_all())
    golden = golden_metrics.load_golden()

    # Bit-exact on the reference machine (same code, same libs, seeded input).
    diffs = golden_metrics.compare(current, golden, rel_tol=0.0, abs_tol=1e-9)

    assert not diffs, (
        "Analysis metrics drifted from the golden snapshot "
        f"({len(diffs)} difference(s)). If intentional, run "
        "`python scripts/eval/golden_metrics.py --update`.\n  "
        + "\n  ".join(diffs[:40])
        + ("\n  ..." if len(diffs) > 40 else "")
    )


def test_golden_snapshot_is_committed_and_nonempty() -> None:
    golden = golden_metrics.load_golden()
    assert golden, "golden snapshot is empty"
    assert set(golden) == set(golden_metrics.build_corpus()), (
        "golden snapshot clips do not match the corpus — run --update"
    )
    # Guard the curated surface: every clip must carry the core scalars the
    # efficiency refactors are most likely to disturb.
    core = {
        "technical_metrics.integrated_lufs",
        "metrics.true_peak_dbfs",
        "metrics.rms_dbfs_estimate",
        "metrics.bands.bass",
        "metrics.spectral_features.centroid_hz",
    }
    for clip, metrics in golden.items():
        missing = core - set(metrics)
        assert not missing, f"[{clip}] golden snapshot missing core metrics: {missing}"
