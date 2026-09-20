"""Real latency-SLO benchmark tests (KENN retrieval, TTS time-to-first-audio).

Unlike tests/test_release_health_check.py (which only exercises the pure
evaluate_latency() gate logic against fabricated sample arrays), these tests
run the actual measurement functions from scripts/eval/release_health_check.py
against a live KENN index / TTS worker -- the same functions
release_health_check.py itself calls.

Before this file existed, a real regression in either SLO had zero automated
coverage: it would only be caught if someone remembered to manually run
`python3 scripts/eval/release_health_check.py`. See
docs/PROJECT_ACTION_PLAN_2026-07-18.md section 4.2's investigation trail for
a concrete case -- a genuine, reproducible TTS SLO miss (2.01-2.14s vs. the
2.0s SLO, 10/11 runs) sat unconfirmed because nothing forced a re-check.

Deliberately marked `slow` and excluded from the default test run: both
measurements swing meaningfully with machine load (observed 1.5-2.35s for
the identical TTS code across different runs), so gating every commit on
them would make ordinary `pytest` runs flaky for reasons unrelated to the
change under test. Run explicitly with:

    pytest tests/test_release_health_latency.py -m slow

or as part of a scheduled/pre-release check, ideally on an otherwise-idle
machine (see the plan doc's note about Ableton/concurrent-process contention
inflating these numbers).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts" / "eval") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import release_health_check as rhc  # noqa: E402

pytestmark = pytest.mark.slow


def test_kenn_retrieval_latency_meets_slo():
    samples = rhc.measure_kenn_latency()
    result = rhc.evaluate_latency("kenn_retrieval_latency", samples, rhc.KENN_LATENCY_SLO_S)
    assert result["ok"], (
        f"{result['failures']} "
        f"(cold={result['cold_start_s']}, steady={result['steady_state_samples_s']}, "
        f"max={result['steady_state_max_s']}, slo={result['slo_s']})"
    )


def test_tts_time_to_first_audio_meets_slo():
    samples = rhc.measure_tts_latency()
    result = rhc.evaluate_latency("tts_latency", samples, rhc.TTS_LATENCY_SLO_S)
    assert result["ok"], (
        f"{result['failures']} "
        f"(cold={result['cold_start_s']}, steady={result['steady_state_samples_s']}, "
        f"max={result['steady_state_max_s']}, slo={result['slo_s']}). "
        "If this fails on an otherwise-idle machine (check `uptime` / Activity Monitor "
        "for CPU contention first -- these samples are noisy under load), it's a real "
        "regression, not flakiness: see docs/PROJECT_ACTION_PLAN_2026-07-18.md section 4.2."
    )
