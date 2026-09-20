"""Isolated, lineaged A/B preview rendering for advisor shadow operations."""

from __future__ import annotations

import copy
import hashlib
import math
from typing import Any, Callable

import numpy as np

from audio_analysis.integration.kenn_advisor import apply_advisor_proposal
from audio_analysis.mixdown.mix_decision_engine import MixPlan

PREVIEW_SCHEMA = "audio-too.kenn-advisor-preview/v1"
MAX_PREVIEW_OPERATIONS = 3
PREVIEW_DURATION_SECONDS = 20.0
MAX_LOUDNESS_BIAS_LU = 0.5
MAX_ABSOLUTE_SAMPLE = 1.0
MIN_AUDIBLE_RMS_DELTA = 1e-7


class AdvisorPreviewError(ValueError):
    """Raised when an A/B render would be unsafe or non-comparable."""


def _densest_window(prepared_stems: list[dict], duration_seconds: float) -> list[dict]:
    if not prepared_stems:
        raise AdvisorPreviewError("No prepared stems are available for preview")
    sample_rate = int(prepared_stems[0].get("sample_rate", 0))
    if sample_rate <= 0:
        raise AdvisorPreviewError("Preview sample rate is invalid")
    lengths = {len(np.asarray(stem.get("samples", []))) for stem in prepared_stems}
    rates = {int(stem.get("sample_rate", 0)) for stem in prepared_stems}
    if len(lengths) != 1 or len(rates) != 1 or sample_rate not in rates:
        raise AdvisorPreviewError("Prepared stems are not aligned")
    total = next(iter(lengths))
    if total <= 0:
        raise AdvisorPreviewError("Prepared stems contain no samples")
    window = min(total, max(1, int(round(duration_seconds * sample_rate))))
    if window == total:
        start = 0
    else:
        envelope = np.zeros(total, dtype=np.float64)
        for stem in prepared_stems:
            samples = np.asarray(stem["samples"], dtype=np.float64)
            if not np.all(np.isfinite(samples)):
                raise AdvisorPreviewError("Prepared stems contain non-finite samples")
            envelope += np.abs(samples)
        block = max(1, sample_rate // 2)
        starts = range(0, total - window + 1, block)
        start = max(starts, key=lambda offset: float(np.mean(envelope[offset : offset + window])))
    result = []
    for stem in prepared_stems:
        item = dict(stem)
        samples = stem["samples"]
        sliced = np.asarray(samples)[start : start + window].copy()
        item["samples"] = sliced.tolist() if isinstance(samples, list) else sliced
        result.append(item)
    return result


def _validate_render(result: Any, label: str) -> tuple[np.ndarray, np.ndarray, float, int]:
    if not isinstance(result, dict) or not isinstance(result.get("mixdown_wav_bytes"), bytes):
        raise AdvisorPreviewError(f"{label} render is missing WAV bytes")
    left = np.asarray(result.get("left"), dtype=np.float64)
    right = np.asarray(result.get("right"), dtype=np.float64)
    if left.ndim != 1 or right.ndim != 1 or len(left) == 0 or len(left) != len(right):
        raise AdvisorPreviewError(f"{label} render channel shape is invalid")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        raise AdvisorPreviewError(f"{label} render contains non-finite samples")
    peak = float(max(np.max(np.abs(left)), np.max(np.abs(right))))
    if peak > MAX_ABSOLUTE_SAMPLE + 1e-9:
        raise AdvisorPreviewError(f"{label} render exceeds the finite sample ceiling")
    loudness = float(result.get("measured_lufs"))
    sample_rate = int(result.get("sample_rate", 0))
    if not math.isfinite(loudness) or sample_rate <= 0:
        raise AdvisorPreviewError(f"{label} render metadata is invalid")
    return left, right, loudness, sample_rate


def _render_with_rng_state(render_fn: Callable, stems: list[dict], plan: MixPlan, rng_state):
    process_state = np.random.get_state()
    np.random.set_state(rng_state)
    try:
        return render_fn(stems, plan)
    finally:
        np.random.set_state(process_state)


def render_advisor_previews(
    prepared_stems: list[dict],
    source_plan: MixPlan,
    proposal: dict,
    *,
    render_fn: Callable = None,
    duration_seconds: float = PREVIEW_DURATION_SECONDS,
    max_operations: int = MAX_PREVIEW_OPERATIONS,
) -> dict[str, Any]:
    """Render a shared baseline and safe one-operation candidates."""
    if render_fn is None:
        from audio_analysis.mixdown.mix_renderer import mix_and_render_stems

        render_fn = mix_and_render_stems
    operations = proposal.get("operations") if isinstance(proposal, dict) else None
    if not isinstance(operations, list) or not operations:
        raise AdvisorPreviewError("Preview proposal has no operations")
    if max_operations < 1:
        raise AdvisorPreviewError("max_operations must be positive")
    window = _densest_window(prepared_stems, duration_seconds)
    revision = str(proposal.get("source_plan_revision", ""))
    seed = int.from_bytes(hashlib.sha256(revision.encode()).digest()[:4], "big")
    comparison_rng_state = np.random.RandomState(seed).get_state()
    baseline = _render_with_rng_state(
        render_fn, window, copy.deepcopy(source_plan), comparison_rng_state
    )
    base_l, base_r, base_lufs, sample_rate = _validate_render(baseline, "baseline")
    candidates = []
    rejected = []
    for index, operation in enumerate(operations[:max_operations]):
        single = {
            **proposal,
            "operations": [copy.deepcopy(operation)],
        }
        try:
            advised_plan = apply_advisor_proposal(source_plan, single)
            candidate = _render_with_rng_state(
                render_fn, window, advised_plan, comparison_rng_state
            )
            cand_l, cand_r, cand_lufs, candidate_rate = _validate_render(
                candidate, f"candidate {index}"
            )
            if candidate_rate != sample_rate or len(cand_l) != len(base_l):
                raise AdvisorPreviewError("Candidate duration/sample rate differs from baseline")
            loudness_bias = cand_lufs - base_lufs
            if abs(loudness_bias) > MAX_LOUDNESS_BIAS_LU:
                raise AdvisorPreviewError(
                    f"Candidate loudness bias {loudness_bias:+.2f} LU exceeds "
                    f"{MAX_LOUDNESS_BIAS_LU:.2f} LU"
                )
            rms_delta = float(
                np.sqrt(
                    np.mean(
                        np.concatenate((cand_l - base_l, cand_r - base_r)) ** 2
                    )
                )
            )
            if rms_delta <= MIN_AUDIBLE_RMS_DELTA:
                raise AdvisorPreviewError("Candidate is effectively identical to baseline")
            candidates.append(
                {
                    "operation_index": index,
                    "operation": copy.deepcopy(operation),
                    "render": candidate,
                    "measured_lufs": cand_lufs,
                    "loudness_bias_lu": round(loudness_bias, 4),
                    "rms_delta": rms_delta,
                }
            )
        except Exception as exc:
            rejected.append({"operation_index": index, "reason": str(exc)})
    return {
        "schema": PREVIEW_SCHEMA,
        "source_plan_revision": proposal.get("source_plan_revision", ""),
        "sample_rate": sample_rate,
        "duration_samples": len(base_l),
        "baseline": baseline,
        "baseline_lufs": base_lufs,
        "candidates": candidates,
        "rejected": rejected,
        "truncated_operations": max(0, len(operations) - max_operations),
    }
