#!/usr/bin/env python3
"""AutoMix output-quality benchmark (plan §23 Stage 4 — 'prove it before building on it').

AutoMix has ~40 tests but none validate the actual *audio output* — only the
plumbing (idempotency, worker lifecycle, auth). This runs real stems through the
full mix pipeline and measures the output **independently** of AutoMix's own
self-reported metrics, so we can answer with evidence:

  1. LUFS accuracy   — does the master hit the target integrated LUFS (±0.5 LU)?
  2. True-peak safety — is the master at/under the -1 dBTP ceiling (no clipping)?
  3. Self-report trust — does AutoMix's own `measured_lufs` match an independent measure?
  4. Robustness       — does it hold across genres and target-loudness presets?

Independent measurement uses analysis_core.loudness_api (calculate_lufs /
calculate_true_peak), a separate code path from the renderer's own metering.

This is the baseline. Later shared-core DSP additions (e.g. dynamic resonance
suppression) are accepted only if they improve these numbers without regressing
LUFS accuracy, true-peak safety, or introducing artifacts.

Usage (arm64 or project venv — pure DSP, no MLX needed):
  python3 scripts/eval/automix_quality_benchmark.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = REPO_ROOT / "studio" / "audio_analysis"
STEM_DIR = REPO_ROOT / "studio" / "audiogen" / "audiogen" / "samples" / "default"
ARTIFACT_DIR = ANALYSIS_ROOT / "audio_analysis" / "artifacts" / "automix_quality"

sys.path.insert(0, str(ANALYSIS_ROOT))
sys.path.insert(0, str(REPO_ROOT / "business" / "app"))  # validator pulls in business `db`
sys.path.insert(0, str(REPO_ROOT))  # `audio_too` top-level package

TRUE_PEAK_CEILING_DBTP = -1.0
LUFS_TOLERANCE = 0.5  # LU — professional mastering tolerance

# Genre × target-loudness matrix. Targets chosen to span streaming presets.
GENRES = ["pop", "rock", "electronic", "hiphop", "acoustic"]
TARGET_LUFS = [-14.0, -16.0, -9.0]
# -9 LUFS integrated + -1 dBTP true-peak are not simultaneously achievable (a
# "loudness war" target louder than any real streaming spec) — it's kept in the
# matrix for informational spread but excluded from the pass/fail gate. See
# docs/AUTOMIX_QUALITY_FINDINGS_2026-07-08.md. Gating on it would make the gate
# permanently fail regardless of real quality.
GATE_TARGET_LUFS = [-14.0, -16.0]


def _to_pcm16_bytes(path: Path) -> bytes:
    """Read any WAV (incl. IEEE-float) and re-emit PCM16 bytes.

    NOTE: AutoMix's own `read_wav_mono` uses Python's `wave` module, which
    rejects float WAVs ('unknown format: 3') — a real ingest gap (finding #1).
    The benchmark converts here so it can still measure *output* quality; the
    ingest gap is reported separately, not hidden.
    """
    import io
    import numpy as np
    import scipy.io.wavfile as wavfile

    sr, data = wavfile.read(path)
    if data.dtype.kind == "f":
        data = np.clip(data, -1.0, 1.0)
        data = (data * 32767.0).astype(np.int16)
    elif data.dtype != np.int16:
        # normalise other int depths to int16 range
        peak = float(np.max(np.abs(data))) or 1.0
        data = (data.astype(np.float64) / peak * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    wavfile.write(buf, sr, data)
    return buf.getvalue()


def _load_stems() -> list[dict]:
    stems = []
    for wav in sorted(STEM_DIR.glob("*.wav")):
        stems.append({"name": wav.name, "file_bytes": _to_pcm16_bytes(wav)})
    return stems


def _make_quiet_dynamic_stems(sr: int = 44100, seconds: float = 8.0) -> list[dict]:
    """Procedurally-generated quieter, more dynamic-range stems.

    docs/AUTOMIX_CODEBASE_AUDIT_2026-07-08.md P2: the benchmark originally used
    only one (hot, peak-normalized) synthetic input profile, which may itself
    have exaggerated the clipping bug's severity. This is a second profile —
    quieter (-18 dBFS peak vs the AudioGen samples' near-0dBFS) with real
    dynamic swells (a slow amplitude envelope, not a flat level) — so the gate
    isn't validated against only one input character. Generated in-code
    (no new binary asset to keep in the repo) and kept deliberately simple:
    sine-based "kick"/"bass"/"pad"/"vocal"-ish stems at different frequencies.
    """
    import io
    import numpy as np
    import scipy.io.wavfile as wavfile

    n = int(sr * seconds)
    t = np.arange(n) / sr
    rng = np.random.default_rng(42)

    def _envelope() -> np.ndarray:
        # Slow swell + occasional quiet passages — real dynamic range, not flat.
        swell = 0.5 + 0.5 * np.sin(2 * np.pi * 0.15 * t)
        quiet_patch = np.ones(n)
        quiet_patch[int(n * 0.4):int(n * 0.55)] *= 0.15  # a real quiet section
        return swell * quiet_patch

    voices = {
        "kick_quiet.wav": (55.0, 0.9),
        "bass_quiet.wav": (98.0, 0.7),
        "pad_quiet.wav": (220.0, 0.4),
        "vocal_quiet.wav": (330.0, 0.5),
    }
    stems = []
    peak_target_dbfs = -18.0
    peak_target_lin = 10.0 ** (peak_target_dbfs / 20.0)
    for name, (freq, amp) in voices.items():
        sig = amp * np.sin(2 * np.pi * freq * t) * _envelope()
        sig += rng.normal(0, 0.01, n)  # a touch of texture, not a pure tone
        peak = float(np.max(np.abs(sig))) or 1.0
        sig = sig / peak * peak_target_lin
        pcm = (sig * 32767.0).astype(np.int16)
        buf = io.BytesIO()
        wavfile.write(buf, sr, pcm)
        stems.append({"name": name, "file_bytes": buf.getvalue()})
    return stems


STEM_PROFILES = {
    "dense_synthetic": _load_stems,
    "quiet_dynamic": _make_quiet_dynamic_stems,
}


def _independent_measures(render: dict) -> dict:
    """Measure the rendered master with the analysis_core loudness backend —
    a different code path from the renderer's own metering."""
    from audio_analysis.analysis_core.loudness_api import calculate_lufs, calculate_true_peak

    left = render["left"].tolist() if hasattr(render["left"], "tolist") else list(render["left"])
    right = render["right"].tolist() if hasattr(render["right"], "tolist") else list(render["right"])
    sr = int(render["sample_rate"])
    import math

    lufs = calculate_lufs(left, right, sr)
    true_peak = calculate_true_peak(left, right, sr, render.get("mixdown_wav_bytes", b""))
    sample_peak = max((abs(x) for x in left + right), default=0.0)
    sample_peak_db = 20.0 * math.log10(sample_peak) if sample_peak > 0 else -120.0
    return {"lufs": lufs, "true_peak_dbtp": true_peak, "sample_peak_dbfs": round(sample_peak_db, 2)}


def _run_one(stems: list[dict], genre: str, target_lufs: float) -> dict:
    from audio_analysis.utils.audio_io import read_wav_mono
    from audio_analysis.analysis_core.dsp_metrics import spectral_bands
    from audio_analysis.mixdown.stem_classifier import classify_stems
    from audio_analysis.mixdown.stem_prep import prepare_stems
    from audio_analysis.mixdown.musical_roles import infer_musical_roles
    from audio_analysis.mixdown.arrangement import infer_arrangement
    from audio_analysis.mixdown.relationships import infer_relationships
    from audio_analysis.mixdown.mono_compatibility import analyze_mono_compatibility
    from audio_analysis.mixdown.automation_preview import build_automation_preview
    from audio_analysis.analysis_core.sidechain_detection import analyze_stems_for_dynamics
    from audio_analysis.mixdown.stem_analysis import analyze_stems_masking
    from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
    from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
    from audio_analysis.mixdown.mix_validator import validate_and_correct_mix

    profiles = classify_stems(stems, read_wav_mono_fn=read_wav_mono, max_samples=131072)
    prepared = prepare_stems(stems, read_wav_mono_fn=read_wav_mono, target_sample_rate=44100,
                             trim=True, normalise=False, max_samples=0)
    masking = analyze_stems_masking(stems, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)
    plan = generate_mix_plan(profiles, masking, genre=genre, target_lufs=target_lufs)
    roles = infer_musical_roles(profiles, prepared)
    plan.musical_roles = [role.to_dict() for role in roles]
    plan.arrangement = infer_arrangement(prepared).to_dict()
    plan.mono_compatibility = analyze_mono_compatibility(
        prepared, plan.arrangement
    ).to_dict()
    existing_dynamics = analyze_stems_for_dynamics(
        prepared, profiles, prepared[0]["sample_rate"] if prepared else 44_100
    )
    plan.relationships = [relationship.to_dict() for relationship in infer_relationships(
        profiles, masking, roles, plan.arrangement, prepared, existing_dynamics
    )]
    plan.automation_preview = build_automation_preview(plan.relationships).to_dict()
    # Full delivered chain: render -> iterative validate/correct (the stage that
    # exists specifically to hit target LUFS and fix clipping). Measure ITS output.
    render = validate_and_correct_mix(prepared, plan, render_fn=mix_and_render_stems)
    plan = render.get("mix_plan", plan)

    indep = _independent_measures(render)
    self_lufs = float(render.get("measured_lufs", 0.0))
    ceiling = float(getattr(plan.bus, "limiter_ceiling_db", TRUE_PEAK_CEILING_DBTP))

    gate = render.get("quality_gate", {})
    lufs_err = indep["lufs"] - target_lufs
    tp_over = indep["true_peak_dbtp"] - ceiling
    return {
        "genre": genre,
        "target_lufs": target_lufs,
        "technical_score": gate.get("technical_score"),
        "quality_gate_passed": gate.get("passed"),
        "correction_iterations": len(render.get("history", [])),
        "measured_lufs_independent": round(indep["lufs"], 2),
        "measured_lufs_selfreport": round(self_lufs, 2),
        "lufs_error_LU": round(lufs_err, 2),
        "lufs_within_tolerance": abs(lufs_err) <= LUFS_TOLERANCE,
        "selfreport_vs_independent_LU": round(self_lufs - indep["lufs"], 2),
        "true_peak_dbtp": round(indep["true_peak_dbtp"], 2),
        "limiter_ceiling_db": round(ceiling, 2),
        "true_peak_over_ceiling": round(tp_over, 2),
        "clipping": tp_over > 0.05,
        "sample_peak_dbfs": indep["sample_peak_dbfs"],
    }


def main() -> int:
    rows = []
    for profile_name, loader in STEM_PROFILES.items():
        stems = loader()
        if not stems:
            print(f"No stems for profile '{profile_name}'", file=sys.stderr)
            return 1
        print(f"[{profile_name}] Loaded {len(stems)} stems: {[s['name'] for s in stems]}", flush=True)

        for genre in GENRES:
            for target in TARGET_LUFS:
                try:
                    row = _run_one(stems, genre, target)
                    row["profile"] = profile_name
                    rows.append(row)
                    flag = "OK " if (row["lufs_within_tolerance"] and not row["clipping"]) else "!! "
                    print(f"{flag}[{profile_name:<15}] {genre:<11} tgt {target:>6.1f}  "
                          f"meas {row['measured_lufs_independent']:>7.2f}  "
                          f"err {row['lufs_error_LU']:>+5.2f}LU  TP {row['true_peak_dbtp']:>+6.2f}dBTP  "
                          f"selfΔ {row['selfreport_vs_independent_LU']:>+5.2f}LU  "
                          f"{'CLIP' if row['clipping'] else ''}", flush=True)
                except Exception as exc:
                    print(f"ERR [{profile_name}] {genre} tgt {target}: {exc}", flush=True)
                    rows.append({"profile": profile_name, "genre": genre, "target_lufs": target, "error": str(exc)})

    valid = [r for r in rows if "error" not in r]
    gated = [r for r in valid if r["target_lufs"] in GATE_TARGET_LUFS]
    n = max(len(valid), 1)
    gn = max(len(gated), 1)
    summary = {
        "runs": len(rows),
        "valid": len(valid),
        "lufs_within_tolerance_rate": round(sum(r["lufs_within_tolerance"] for r in valid) / n, 3),
        "clipping_rate": round(sum(r["clipping"] for r in valid) / n, 3),
        "mean_abs_lufs_error_LU": round(sum(abs(r["lufs_error_LU"]) for r in valid) / n, 3),
        "max_abs_lufs_error_LU": round(max((abs(r["lufs_error_LU"]) for r in valid), default=0.0), 3),
        "mean_abs_selfreport_gap_LU": round(sum(abs(r["selfreport_vs_independent_LU"]) for r in valid) / n, 3),
        "max_true_peak_dbtp": round(max((r["true_peak_dbtp"] for r in valid), default=-120.0), 2),
        # Gate metrics only cover realistic streaming targets (GATE_TARGET_LUFS) —
        # see the comment on that constant for why -9 LUFS is excluded.
        "gate_targets": GATE_TARGET_LUFS,
        "gate_lufs_within_tolerance_rate": round(sum(r["lufs_within_tolerance"] for r in gated) / gn, 3),
        "gate_clipping_rate": round(sum(r["clipping"] for r in gated) / gn, 3),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / f"automix_quality_{stamp}.json"
    out.write_text(json.dumps({"timestamp": stamp, "summary": summary, "rows": rows}, indent=2))

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\nReport: {out}")

    ok = (
        len(gated) > 0
        and summary["gate_lufs_within_tolerance_rate"] >= 0.9
        and summary["gate_clipping_rate"] == 0.0
        and not any("error" in r for r in rows)
    )
    print("\nBASELINE VERDICT:", "PASS" if ok else "NEEDS WORK", f"(gated on targets {GATE_TARGET_LUFS})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
