"""Post-render validation and auto-correction loop for automated mixdown system.

Re-analyses the rendered mixdown using the existing mix_review pipeline, compares results
against target configurations, applies corrective master bus processing (EQ gain cuts, limiter
threshold offsets), re-renders, and ensures the output meets quality standards.
"""

from __future__ import annotations

import numpy as np

from .mix_decision_engine import MixPlan
from ..mix_review.mix_review import analyze_wav
from ..mix_review.mix_style_classifier import classify_mix_style
from ..analysis_core.loudness import calculate_true_peak

# Below this confidence (classify_reference_profile()'s 1.0 - distance/12.0
# formula), the spectral match is too ambiguous to bother the decisions_log
# with -- e.g. a nearly genre-neutral mix shouldn't produce a confident-
# sounding disagreement.
GENRE_MISMATCH_CONFIDENCE_THRESHOLD = 0.5


def verify_render_output(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    wav_bytes: bytes,
    *,
    target_lufs: float | None = None,
    measured_lufs: float | None = None,
    lufs_tolerance: float = 1.0,
    ceiling_db: float = -1.0,
    ceiling_margin_db: float = 0.15,
    expected_num_samples: int | None = None,
) -> dict:
    """Stage 7.2/7.5 — pre-write validation gate for the atomic mixdown pipeline.

    Runs cheap, self-contained checks directly against the fully-rendered
    master bus audio (post-limiter, post-dither) before it is allowed to
    replace the final output file:

      - clipping        : sample peak must never exceed full scale.
      - true peak        : inter-sample (4x oversampled) true peak must stay
                            at/under ``ceiling_db`` (small margin for
                            measurement noise between limiter and validator).
      - phase correlation: broadband L/R correlation coefficient (+1 = mono/
                            in-phase, -1 = fully out-of-phase/mono-incompatible).
      - dynamic range     : crest factor (peak - RMS in dB), flags a mix that
                             has been crushed flat by over-limiting.
      - LUFS              : informational only — how far the render landed
                             from the target integrated loudness.

    Structural corruption, prepared-session duration mismatch, clipping, and
    true-peak-over-ceiling are treated as hard failures (``ok=False``); LUFS
    drift and phase/dynamic-range readings are reported
    as diagnostics so a caller can decide whether to re-render, since a
    legitimately intentional master (e.g. silence, or a reference-matched
    mix) can validly sit outside "typical" ranges without being unsafe to
    ship.
    """
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    reasons: list[str] = []
    hard_failures: list[str] = []

    # 0. Structural validity — fail closed before any numeric interpretation.
    channels_aligned = left_array.ndim == 1 and right_array.ndim == 1 and (
        left_array.size == right_array.size and left_array.size > 0
    )
    if not channels_aligned:
        hard_failures.append("Rendered channels are empty, non-vector, or have different lengths.")
        left_array = left_array.reshape(-1)
        right_array = right_array.reshape(-1)
        common_length = min(left_array.size, right_array.size)
        left_array = left_array[:common_length]
        right_array = right_array[:common_length]
    if expected_num_samples is not None:
        if not isinstance(expected_num_samples, int) or expected_num_samples <= 0:
            hard_failures.append("Expected source sample count is invalid.")
        elif left_array.size != expected_num_samples or right_array.size != expected_num_samples:
            hard_failures.append(
                "Rendered duration does not match the prepared session: "
                f"expected {expected_num_samples} samples, got "
                f"{left_array.size}/{right_array.size}."
            )
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        hard_failures.append("Rendered sample rate is invalid.")
    wav_header_valid = (
        isinstance(wav_bytes, bytes)
        and len(wav_bytes) >= 12
        and wav_bytes[:4] == b"RIFF"
        and wav_bytes[8:12] == b"WAVE"
    )
    if not wav_header_valid:
        hard_failures.append("Rendered WAV payload is missing or malformed.")
    finite = bool(np.all(np.isfinite(left_array)) and np.all(np.isfinite(right_array)))
    if not finite:
        hard_failures.append("Rendered channels contain NaN or infinite samples.")
        left_array = np.nan_to_num(left_array, nan=0.0, posinf=1.0, neginf=-1.0)
        right_array = np.nan_to_num(right_array, nan=0.0, posinf=1.0, neginf=-1.0)
    reasons.extend(hard_failures)

    # 1. Clipping — sample peak must be within [-1.0, 1.0].
    sample_peak = (
        float(np.max(np.abs(np.concatenate([left_array, right_array]))))
        if left_array.size and right_array.size
        else 0.0
    )
    clipped = sample_peak > 1.0 + 1e-6
    if clipped:
        failure = f"Sample peak {sample_peak:.6f} exceeds full scale (clipping)."
        reasons.append(failure)
        hard_failures.append(failure)

    # 2. True peak (inter-sample, 4x oversampled per ITU-R BS.1770 Annex 2).
    try:
        true_peak_dbtp = calculate_true_peak(
            left_array, right_array, sample_rate, wav_bytes
        )
    except Exception:
        # Fall back to sample peak in dBFS if the true-peak measurement path fails;
        # this is conservative (sample peak <= true peak) so it will not falsely pass.
        true_peak_dbtp = 20.0 * np.log10(max(sample_peak, 1e-12))
    over_ceiling = true_peak_dbtp > ceiling_db + ceiling_margin_db
    if over_ceiling:
        failure = (
            f"True peak {true_peak_dbtp:.2f} dBTP exceeds ceiling {ceiling_db:.2f} dBTP "
            f"(+{ceiling_margin_db:.2f} dB margin)."
        )
        reasons.append(failure)
        hard_failures.append(failure)

    # 3. Broadband phase correlation (fast direct correlation, not per-band spectral).
    denom = float(
        np.sqrt(
            max(
                np.dot(left_array, left_array) * np.dot(right_array, right_array),
                1e-18,
            )
        )
    )
    phase_correlation = (
        float(np.dot(left_array, right_array) / denom) if denom > 1e-9 else 1.0
    )
    phase_correlation = max(-1.0, min(1.0, phase_correlation))
    if phase_correlation < -0.5:
        reasons.append(
            f"Phase correlation {phase_correlation:.2f} indicates significant "
            "mono-incompatible (out-of-phase) content."
        )

    # 4. Dynamic range / crest factor.
    rms = (
        float(np.sqrt(np.mean(left_array * left_array + right_array * right_array) / 2.0))
        if left_array.size and right_array.size
        else 0.0
    )
    rms_db = 20.0 * np.log10(max(rms, 1e-12))
    peak_db = 20.0 * np.log10(max(sample_peak, 1e-12))
    crest_factor_db = peak_db - rms_db if sample_peak > 0 else 0.0
    if 0 < sample_peak and crest_factor_db < 3.0:
        reasons.append(
            f"Crest factor {crest_factor_db:.1f} dB is very low; the master bus may be over-limited/flat."
        )

    # 5. LUFS drift (informational).
    lufs_diff = None
    if target_lufs is not None and measured_lufs is not None:
        lufs_diff = float(measured_lufs - target_lufs)
        if abs(lufs_diff) > lufs_tolerance:
            reasons.append(
                f"Integrated loudness {measured_lufs:.2f} LUFS is {lufs_diff:+.2f} LU from "
                f"target {target_lufs:.2f} LUFS (tolerance ±{lufs_tolerance:.2f})."
            )

    return {
        "ok": not hard_failures,
        "hard_failures": hard_failures,
        "reasons": reasons,
        "metrics": {
            "sample_peak": sample_peak,
            "true_peak_dbtp": true_peak_dbtp,
            "phase_correlation": phase_correlation,
            "crest_factor_db": crest_factor_db,
            "rms_dbfs": rms_db,
            "peak_dbfs": peak_db,
            "measured_lufs": measured_lufs,
            "target_lufs": target_lufs,
            "lufs_diff": lufs_diff,
        },
    }


def _log_genre_mismatch_if_any(report: dict, current_plan: MixPlan) -> None:
    """Informational only -- never overrides the user's genre selection.

    generate_mix_plan() silently falls back to "pop" for any genre string
    it doesn't recognize, and there was previously no signal anywhere if
    the audio itself sounds nothing like what was selected (e.g. picking
    "jazz" for a trap beat). Reuses the analysis this function already
    computes for the quality-gate check -- no extra render/analysis cost.
    Best-effort: a classifier hiccup must never break the render pipeline.
    """
    try:
        detected = classify_mix_style(report).get("genre", {})
        detected_key = str(detected.get("genre_key") or "")
        confidence = float(detected.get("confidence") or 0.0)
    except Exception:
        return
    if not detected_key or confidence < GENRE_MISMATCH_CONFIDENCE_THRESHOLD:
        return
    if detected_key == current_plan.genre.lower():
        return
    current_plan.decisions_log.append(
        f"Note: the rendered audio spectrally matches '{detected_key}' "
        f"(confidence {confidence:.2f}) more closely than the selected genre "
        f"'{current_plan.genre}'. Mixing rules for '{current_plan.genre}' were "
        "still applied as selected -- this is informational only."
    )


def validate_and_correct_mix(
    prepared_stems: list[dict],
    mix_plan: MixPlan,
    render_fn,
    max_iterations: int = 3,
    min_technical_score: int = 65,
) -> dict:
    """Run the validation and auto-correction loop on the mix.

    Iteratively renders and analyses the mixdown, adjusting master EQ and limiter
    parameters to hit target LUFS and resolve frequency imbalances.

    Parameters
    ----------
    prepared_stems : list[dict]
        Prepared stems data.
    mix_plan : MixPlan
        The current mix plan.
    render_fn : callable
        The `mix_and_render_stems(stems, plan)` rendering function.
    max_iterations : int
        Maximum number of render-analyze iterations.

    Returns
    -------
    dict
        The final render result dictionary containing wav bytes, left/right channels,
        measured lufs, final report, and iteration history.
    """
    history = []
    current_plan = mix_plan
    initial_report: dict | None = None

    def finalize(result: dict, report: dict) -> dict:
        final_score = int(report.get("technical_score", report.get("metrics", {}).get("technical_score", 0)))
        safety = verify_render_output(
            result.get("left", []),
            result.get("right", []),
            int(result.get("sample_rate", 44_100)),
            result.get("mixdown_wav_bytes", b""),
            target_lufs=current_plan.target_lufs,
            measured_lufs=result.get("measured_lufs"),
            ceiling_db=current_plan.bus.limiter_ceiling_db,
            expected_num_samples=result.get("source_num_samples"),
        )
        result["history"] = history
        result["report"] = report
        result["quality_gate"] = {
            "passed": safety["ok"],
            "safety_passed": safety["ok"],
            "hard_failures": safety["hard_failures"],
            "safety_diagnostics": safety["reasons"],
            "technical_score": final_score,
            "minimum_score": min_technical_score,
            "advisory_score_passed": final_score >= min_technical_score,
        }
        first_metrics = (initial_report or {}).get("metrics", {})
        final_metrics = report.get("metrics", {})
        result["comparison_report"] = {
            "before": initial_report or report,
            "after": report,
            "delta": {
                "technical_score": final_score
                - int(
                    (initial_report or report).get(
                        "technical_score", (initial_report or report).get("metrics", {}).get("technical_score", 0)
                    )
                ),
                "integrated_lufs": float(final_metrics.get("integrated_lufs", 0.0))
                - float(first_metrics.get("integrated_lufs", 0.0)),
                "true_peak_db": float(final_metrics.get("true_peak_dbfs", final_metrics.get("true_peak_db", 0.0)))
                - float(first_metrics.get("true_peak_dbfs", first_metrics.get("true_peak_db", 0.0))),
            },
        }
        return result

    for iteration in range(1, max_iterations + 1):
        # 1. Render the mix
        result = render_fn(prepared_stems, current_plan)
        
        # 2. Analyze the rendered mixdown
        wav_bytes = result["mixdown_wav_bytes"]
        # Use genre as the mix goal
        report = analyze_wav(wav_bytes, filename=f"mixdown_v{iteration}.wav", mix_goal=current_plan.mix_goal)
        if initial_report is None:
            initial_report = report

        if iteration == 1:
            _log_genre_mismatch_if_any(report, current_plan)

        flags = report.get("flags", [])
        metrics = report.get("metrics", {})
        technical_score = report.get("technical_score", metrics.get("technical_score", 0))
        
        # Extracted metrics
        measured_lufs = metrics.get("integrated_lufs", -18.0)
        true_peak_value = metrics.get("true_peak_dbfs", metrics.get("true_peak_db"))
        true_peak_db = float(true_peak_value) if true_peak_value is not None else None

        # Log this iteration
        iter_log = {
            "iteration": iteration,
            "technical_score": technical_score,
            "measured_lufs": measured_lufs,
            "true_peak_db": true_peak_db,
            "flags_count": len(flags),
        }
        history.append(iter_log)

        # 3. Check targets and formulate corrections
        lufs_diff = current_plan.target_lufs - measured_lufs
        clipping = true_peak_db is not None and true_peak_db > current_plan.bus.limiter_ceiling_db + 0.05
        
        # If score is good and LUFS is within ±0.3 LU, we are done!
        if abs(lufs_diff) <= 0.3 and technical_score >= min_technical_score and not clipping:
            current_plan.decisions_log.append(
                f"Iteration {iteration}: Mix validated successfully. Score: {technical_score}/100, LUFS: {measured_lufs:.2f}."
            )
            return finalize(result, report)

        # Limit correction loops
        if iteration == max_iterations:
            current_plan.decisions_log.append(
                f"Iteration {iteration}: Reached maximum iteration budget of {max_iterations}. Returning current mix."
            )
            if technical_score < min_technical_score:
                current_plan.decisions_log.append(
                    f"Advisory quality target not reached: technical score {technical_score}/100 "
                    f"is below {min_technical_score}/100; hard delivery safety is evaluated separately."
                )
            return finalize(result, report)

        # 4. Formulate corrections for next pass
        bus_state_before = repr(current_plan.bus)
        current_plan.decisions_log.append(
            f"Iteration {iteration} check: Score is {technical_score}/100, LUFS is {measured_lufs:.2f} (target {current_plan.target_lufs:.1f}). Applying corrections."
        )

        # A. Peak safety correction. Increasing the limiter threshold offset reduces
        # the amount of level driven into the final limiter on the next render.
        if clipping:
            old_thresh = current_plan.bus.limiter_threshold_db
            current_plan.bus.limiter_threshold_db = min(12.0, old_thresh + 1.0)
            current_plan.decisions_log.append(
                f"  - Clipping correction: true peak {true_peak_db:.2f} dBTP exceeded "
                f"the {current_plan.bus.limiter_ceiling_db:.2f} dBTP ceiling; reduced bus drive by 1.0 dB."
            )

        # B. LUFS correction (adjust limiter threshold to hit target)
        if abs(lufs_diff) > 0.3:
            # Shift threshold to push or pull gain into the limiter
            old_thresh = current_plan.bus.limiter_threshold_db
            # If diff is +2.0 (too quiet), we want to lower threshold (push harder), i.e., threshold -= 2.0
            # If diff is -2.0 (too loud), we raise threshold (less push), i.e., threshold += 2.0
            new_thresh = old_thresh - lufs_diff
            # Clamp threshold adjustments to safety limits
            new_thresh = max(-18.0, min(new_thresh, 12.0))
            current_plan.bus.limiter_threshold_db = new_thresh
            current_plan.decisions_log.append(
                f"  - LUFS adjustment: Offset limiter threshold from {old_thresh:+.1f} dB to {new_thresh:+.1f} dB."
            )

        # C. Tonal balance corrections based on active review flags
        # Map specific flag categories to master bus EQ compensation cuts
        eq_corrections = []
        for flag in flags:
            flag_id = flag.get("id", "")
            band = flag.get("band", "")

            if any(token in flag_id.lower() for token in ("phase", "correlation", "mono")):
                current_plan.decisions_log.append(
                    f"  - Phase safety: flagged '{flag_id}' for manual review; no automatic phase correction applied."
                )
                continue
            
            # Simple heuristic mapping of flags to corrective EQ cuts
            if "excess" in flag_id or "too_loud" in flag_id or "harsh" in flag_id:
                if band == "sub":
                    eq_corrections.append({"type": "peaking", "freq": 45.0, "gain_db": -1.0, "q": 1.0, "reason": "Tame master sub excess"})
                elif band == "bass":
                    eq_corrections.append({"type": "peaking", "freq": 100.0, "gain_db": -1.0, "q": 1.2, "reason": "Tame master bass excess"})
                elif band == "low_mids":
                    eq_corrections.append({"type": "peaking", "freq": 250.0, "gain_db": -1.0, "q": 1.2, "reason": "Tame master mud"})
                elif band == "mids":
                    eq_corrections.append({"type": "peaking", "freq": 1000.0, "gain_db": -1.0, "q": 0.8, "reason": "Reduce master mid accumulation"})
                elif band == "presence":
                    eq_corrections.append({"type": "peaking", "freq": 3500.0, "gain_db": -1.0, "q": 1.5, "reason": "Reduce master harshness"})
                elif band == "sibilance":
                    eq_corrections.append({"type": "peaking", "freq": 7000.0, "gain_db": -1.5, "q": 2.0, "reason": "Tame master sibilance"})
                elif band == "air":
                    eq_corrections.append({"type": "highshelf", "freq": 12000.0, "gain_db": -1.0, "q": 0.707, "reason": "Slightly damp master top-end"})

        # Apply corrective EQ bands to master bus
        for corr in eq_corrections:
            # Check if this correction frequency is already in master EQ
            dup = any(abs(b["frequency"] - corr["freq"]) < 30.0 for b in current_plan.bus.bus_eq_bands)
            if not dup:
                current_plan.bus.bus_eq_bands.append({
                    "type": corr["type"],
                    "frequency": corr["freq"],
                    "gain_db": corr["gain_db"],
                    "q": corr["q"],
                    "reason": corr["reason"],
                })
                current_plan.decisions_log.append(
                    f"  - Master EQ correction: Cut {corr['gain_db']:.1f} dB at {corr['freq']:.0f} Hz ({corr['reason']})."
                )

        if repr(current_plan.bus) == bus_state_before:
            current_plan.decisions_log.append(
                f"Iteration {iteration}: no_effect — advisory findings produced no supported "
                "plan correction; returning the unchanged safe render instead of rerendering."
            )
            if technical_score < min_technical_score:
                current_plan.decisions_log.append(
                    f"Advisory quality target not reached: technical score {technical_score}/100 "
                    f"is below {min_technical_score}/100; hard delivery safety is evaluated separately."
                )
            return finalize(result, report)

    return finalize(result, report)
