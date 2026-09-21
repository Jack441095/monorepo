"""The KENN Mix Review beta's only qualified fault-detection logic.

Provenance
----------
This module is a faithful, frozen copy of the detector and gate logic that
was actually evaluated and qualified in V2-D, promoted from the evaluation-only
submodule into this product boundary so the beta can run it directly instead
of importing an evaluation submodule at runtime.

- Detector math copied from
  ``products/kenn-evaluation/benchmark/measured_candidates_v2c.py``
- Gate policy copied from
  ``products/kenn-evaluation/benchmark/recommendation_gate.py``
- Frozen thresholds copied from
  ``products/kenn-evaluation/results/KENN_V2B_gate_config.json`` (gate_version
  ``v2b.1``)
- The scope/confounder overrides in ``decide_family`` mirror ``v2c_decide`` in
  ``products/kenn-evaluation/benchmark/run_audio_holdout_v2c.py``.
- Promoted at ``kenn-evaluation`` submodule commit
  ``7f76f620d9185d0f913e577dbfa2af8012529509`` (2026-08-25).
- Qualification evidence: ``products/kenn-evaluation/reports/KENN_V2D_FINAL_REPORT.md``
  — 100%/100% precision/recall and 0% healthy false-positive rate on the
  target holdout for exactly these three fault families, using this exact
  decision logic. No other fault family has this evidence.

Do not extend this file to cover additional fault families, and do not change
its math or thresholds, without first re-running the V2-D-style qualification
harness against the change. An unqualified edit here silently invalidates the
beta's only evidence-backed claims.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum

import numpy as np

ANALYSIS_VERSION = "kenn.measured_candidates.v2c.1"
GATE_VERSION = "v2b.1"

# Frozen from KENN_V2B_gate_config.json (gate_version v2b.1). Copied as data,
# not read from the evaluation submodule at runtime, so the beta's behaviour
# cannot silently drift if that submodule changes.
FROZEN_GATE_CONFIG: dict[str, dict[str, float]] = {
    "default": {"observe": 0.47, "recommend": 0.70, "strong": 0.88},
    "clipping": {"observe": 0.28, "recommend": 0.48, "strong": 0.74},
    "headroom": {"observe": 0.32, "recommend": 0.54, "strong": 0.80},
    "lr_imbalance": {"observe": 0.34, "recommend": 0.56, "strong": 0.82},
}

QUALIFIED_FAULT_FAMILIES = ("clipping", "headroom", "lr_imbalance")


@dataclass(frozen=True)
class MeasuredIssueCandidate:
    issue_type: str
    measured_value: float
    unit: str
    score: float
    severity: str
    confidence_kind: str
    confidence_bucket: str
    persistence: float
    affected_channels: tuple[str, ...]
    analysis_scope: str
    evidence: dict
    limitations: tuple[str, ...]
    analysis_version: str = ANALYSIS_VERSION

    def payload(self) -> dict:
        return asdict(self)


class GateAction(StrEnum):
    ABSTAIN = "abstain"
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    STRONG_RECOMMEND = "strong_recommend"


class RecommendationState(StrEnum):
    NO_ACTION_RECOMMENDED = "no_action_recommended"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONTEXT_REQUIRED = "context_required"
    OBSERVATION_ONLY = "observation_only"
    RECOMMENDATION_JUSTIFIED = "recommendation_justified"


@dataclass(frozen=True)
class GateDecision:
    issue_type: str
    state: RecommendationState
    action: GateAction
    reason: str
    confidence: float


def _db(value: float) -> float:
    return 20 * math.log10(max(value, 1e-12))


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def _sev(score: float) -> str:
    return "severe" if score >= 0.85 else "strong" if score >= 0.65 else "moderate" if score >= 0.45 else "mild"


def clipping_candidate(audio: np.ndarray, scope: str = "unknown") -> MeasuredIssueCandidate:
    if audio.size == 0:
        return MeasuredIssueCandidate(
            "clipping", 0.0, "linear_peak", 0.0, "mild", "measured", "low", 0.0, (), scope,
            {"category": "no_clipping", "empty": True},
            ("Empty audio has insufficient evidence.",),
        )
    peak = float(np.max(np.abs(audio)))
    near = np.abs(audio) >= 0.999
    plateaus = 0
    affected: list[str] = []
    for c in range(audio.shape[1]):
        runs = np.diff(np.r_[False, near[:, c], False].astype(np.int8))
        starts = np.where(runs == 1)[0]
        ends = np.where(runs == -1)[0]
        events = sum((ends - starts) >= 2)
        plateaus += int(events)
        if events:
            affected.append("L" if c == 0 else "R")
    density = float(np.mean(near))
    score = min(1.0, 0.15 + min(0.45, density * 30) + min(0.45, plateaus * 0.12)) if plateaus else max(0.0, (peak - 0.999) * 120)
    category = (
        "likely_hard_clipping" if plateaus >= 2
        else "likely_sample_clipping" if plateaus
        else "near_full_scale" if peak >= 0.98
        else "no_clipping"
    )
    return MeasuredIssueCandidate(
        "clipping", peak, "linear_peak", score, _sev(score), "measured",
        "high" if plateaus else "medium", min(1.0, plateaus / 4), tuple(affected), scope,
        {
            "category": category,
            "max_sample_peak": peak,
            "peak_dbfs": _db(peak),
            "near_full_scale_samples": int(near.sum()),
            "plateau_events": plateaus,
            "event_density": density,
        },
        ("Sample-domain detector; it cannot identify all analogue/soft distortion.",),
    )


def headroom_candidate(audio: np.ndarray, scope: str = "unknown") -> MeasuredIssueCandidate:
    if audio.size == 0:
        return MeasuredIssueCandidate(
            "headroom", 0.0, "dBFS_margin", 0.0, "mild", "derived", "low", 0.0, (), scope,
            {"empty": True},
            ("Empty audio has insufficient evidence.",),
        )
    per = [float(np.max(np.abs(audio[:, c]))) for c in range(audio.shape[1])]
    peak = max(per)
    margin = -_db(peak)
    score = min(1.0, max(0.0, (9 - margin) / 9))
    return MeasuredIssueCandidate(
        "headroom", margin, "dBFS_margin", score, _sev(score), "derived", "high", 1.0,
        tuple("L" if i == 0 else "R" for i, p in enumerate(per) if p == peak), scope,
        {
            "max_sample_peak_dbfs": _db(peak),
            "headroom_db": margin,
            "channel_peaks_dbfs": [_db(p) for p in per],
        },
        ("Sample-peak margin is not a universal mastering target; true peak is not estimated.",),
    )


def lr_imbalance_candidate(audio: np.ndarray, sr: int, scope: str = "unknown") -> MeasuredIssueCandidate:
    if audio.size == 0:
        return MeasuredIssueCandidate(
            "lr_imbalance", 0.0, "dB", 0.0, "mild", "measured", "low", 0.0, (), scope,
            {"empty": True},
            ("Empty audio has insufficient evidence.",),
        )
    if audio.shape[1] == 1:
        return MeasuredIssueCandidate(
            "lr_imbalance", 0.0, "dB", 0.0, "mild", "measured", "high", 1.0, (), scope,
            {"channel_delta_db": 0.0, "window_count": 0},
            ("Mono material has no L/R balance judgment.",),
        )
    size = max(128, int(sr * 0.1))
    vals: list[float] = []
    for start in range(0, len(audio), size):
        frame = audio[start:start + size]
        if len(frame) >= 32:
            vals.append(_db(_rms(frame[:, 0])) - _db(_rms(frame[:, 1])))
    values = np.asarray(vals) if vals else np.array([0.0])
    median = float(np.median(values))
    persistent = float(np.mean(np.sign(values) == np.sign(median))) if abs(median) > 0.1 else 1.0
    p95 = float(np.percentile(np.abs(values), 95))
    overall = _db(_rms(audio[:, 0])) - _db(_rms(audio[:, 1]))
    score = min(1.0, max(0.0, (abs(median) - 1.5) / 6) * persistent + max(0.0, (p95 - 3) / 12) * 0.2)
    return MeasuredIssueCandidate(
        "lr_imbalance", median, "dB", score, _sev(score), "measured",
        "high" if len(values) >= 5 else "medium", persistent, ("L", "R"), scope,
        {
            "channel_delta_db": overall,
            "median_window_delta_db": median,
            "p95_abs_window_delta_db": p95,
            "direction_consistency": persistent,
            "window_count": len(values),
        },
        ("A stereo render cannot distinguish persistent mix imbalance from an intentional arrangement without context.",),
    )


def decide_family(candidate: MeasuredIssueCandidate) -> GateDecision:
    """Frozen V2-D decision policy: score + scope/persistence overrides.

    Mirrors ``v2c_decide`` in ``run_audio_holdout_v2c.py`` exactly, including
    the per-family overrides that were part of what got qualified.
    """
    score = min(1.0, max(0.0, candidate.score))
    rules = FROZEN_GATE_CONFIG.get(candidate.issue_type, FROZEN_GATE_CONFIG["default"])

    if candidate.issue_type == "headroom" and candidate.analysis_scope != "mix_in_progress":
        return GateDecision(
            candidate.issue_type, RecommendationState.OBSERVATION_ONLY, GateAction.OBSERVE,
            "Headroom judgment requires an explicit mix-in-progress scope; treat as informational only.",
            score,
        )
    if candidate.issue_type == "lr_imbalance" and candidate.persistence < 0.7:
        return GateDecision(
            candidate.issue_type, RecommendationState.CONTEXT_REQUIRED, GateAction.ABSTAIN,
            "Imbalance is not persistent enough to rule out an intentional arrangement (e.g. alternating pan).",
            score,
        )

    if score < rules["observe"]:
        return GateDecision(
            candidate.issue_type, RecommendationState.NO_ACTION_RECOMMENDED, GateAction.ABSTAIN,
            "No material issue exceeds the calibrated observation boundary.", score,
        )
    if score < rules["recommend"]:
        return GateDecision(
            candidate.issue_type, RecommendationState.OBSERVATION_ONLY, GateAction.OBSERVE,
            "Measured deviation is near the boundary; inspect in context before changing it.", score,
        )
    if score < rules["strong"]:
        return GateDecision(
            candidate.issue_type, RecommendationState.RECOMMENDATION_JUSTIFIED, GateAction.RECOMMEND,
            "Persistent measured deviation exceeds the calibrated intervention boundary.", score,
        )
    return GateDecision(
        candidate.issue_type, RecommendationState.RECOMMENDATION_JUSTIFIED, GateAction.STRONG_RECOMMEND,
        "Persistent measured deviation is severe and meets the strong-intervention boundary.", score,
    )


def evaluate_qualified_families(
    audio: np.ndarray, sr: int, *, scope: str = "unknown"
) -> list[tuple[MeasuredIssueCandidate, GateDecision]]:
    """Run all three qualified detectors and their frozen gate decisions.

    Applies the same "clipping subsumes headroom in presentation" rule used
    during qualification: if clipping reaches recommend/strong_recommend,
    headroom is still measured and returned, but its decision is downgraded
    to OBSERVE so the beta never presents two competing top-line findings for
    what is usually the same underlying gain-staging problem.
    """
    candidates = [
        clipping_candidate(audio, scope),
        headroom_candidate(audio, scope),
        lr_imbalance_candidate(audio, sr, scope),
    ]
    decisions = [decide_family(c) for c in candidates]

    clipping_decision = next((d for d in decisions if d.issue_type == "clipping"), None)
    if clipping_decision and clipping_decision.action in (GateAction.RECOMMEND, GateAction.STRONG_RECOMMEND):
        decisions = [
            d if d.issue_type != "headroom" else GateDecision(
                "headroom", RecommendationState.OBSERVATION_ONLY, GateAction.OBSERVE,
                "Clipping is the higher-priority finding; headroom is measured but not presented as a separate top-line issue.",
                d.confidence,
            )
            for d in decisions
        ]

    return list(zip(candidates, decisions))
