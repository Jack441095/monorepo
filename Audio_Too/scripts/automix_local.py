#!/usr/bin/env python3
"""Stage O1 — local/offline AutoMix: point at a folder of stems, get a mixed
file back, with no DB, job queue, or HTTP upload involved.

Runs the exact same core pipeline business/app/automix_worker.py's
_process_job() already orchestrates (classify -> prepare -> polarity
correction -> masking analysis -> generate_mix_plan() -> render -> validate
-> package) synchronously, in-process, reading stems from a local folder
instead of an uploaded zip. This is the product-facing entry point Stage O1
scoped: the async job-queue wrapper around this pipeline is real and stays
where it is for Jack's own web workflow, but the pipeline itself was always
a pure, callable library underneath it -- this is that same library, called
directly.

Deliberately does not include: KENN's autonomous advisor (Stage H, needs a
DB-backed style_prefs flag), Stage J's project-feature capture (needs a DB
to write training rows to), or M8.2's multi-pass feedback-learned refinement
(needs a DB of past feedback). All three are online-job-only features, not
part of a from-scratch local mixdown -- their absence here does not change
the resulting mix's quality gate or safety guarantees, which are identical
to the online path (same generate_mix_plan(), same render/validate chain,
same true-peak-safe limiter).

Usage:
    python scripts/automix_local.py <stems-dir> --genre pop --target-lufs -14
    python scripts/automix_local.py <stems-dir> --output ./my-mix
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server" / "app"))

from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402
from audio_analysis.analysis_core.dsp_metrics import spectral_bands  # noqa: E402
from audio_analysis.analysis_core.phase_polarity_detection import correct_stem_polarity  # noqa: E402
from audio_analysis.mixdown.stem_classifier import classify_stems  # noqa: E402
from audio_analysis.mixdown.stem_prep import prepare_stems  # noqa: E402
from audio_analysis.mixdown.musical_roles import (  # noqa: E402
    apply_role_corrections,
    infer_musical_roles,
    validate_role_correction_payload,
)
from audio_analysis.mixdown.arrangement import (  # noqa: E402
    apply_arrangement_corrections,
    infer_arrangement,
    validate_arrangement_correction_payload,
)
from audio_analysis.mixdown.relationships import infer_relationships  # noqa: E402
from audio_analysis.mixdown.mono_compatibility import analyze_mono_compatibility  # noqa: E402
from audio_analysis.mixdown.automation_preview import build_automation_preview  # noqa: E402
from audio_analysis.analysis_core.sidechain_detection import analyze_stems_for_dynamics  # noqa: E402
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking  # noqa: E402
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan  # noqa: E402
from audio_analysis.mixdown.spectral_match import (  # noqa: E402
    compute_reference_match_bands as _compute_reference_match_bands,
    compute_reference_dynamics_comp as _compute_reference_dynamics_comp,
    compute_reference_width_factor as _compute_reference_width_factor,
)
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems  # noqa: E402
from audio_analysis.mixdown.mix_validator import validate_and_correct_mix  # noqa: E402
from audio_analysis.mixdown.mix_delivery import package_mixdown_delivery  # noqa: E402

AUDIO_SUFFIXES = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}


def _find_stem_files(stems_dir: Path) -> list[Path]:
    paths = [
        p for p in sorted(stems_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES
        and not p.name.startswith(".") and not p.name.startswith("._")
    ]
    return paths


def run_local_automix(
    stems_dir: Path,
    *,
    genre: str = "pop",
    target_lufs: float | None = None,
    output_dir: Path,
    project_id: str = "local-mix",
    role_corrections: dict | None = None,
    arrangement_corrections: dict | None = None,
    apply_masking: bool = False,
    apply_mono_compat_correction: bool = False,
    apply_proactive_crest_reduction: bool = False,
    extra_bus_eq_bands: list[dict] | None = None,
    bus_compressor_override: dict | None = None,
    export_stems: bool = False,
    reference_track: Path | None = None,
    bass_boost_db: float = 0.0,
    bass_boost_hz: float = 120.0,
    match_reference: bool = False,
    match_dynamics: bool = False,
    match_width: bool = False,
) -> dict:
    """Run the full AutoMix pipeline against local stems and package the
    result. Returns package_mixdown_delivery()'s status dict.

    ``apply_masking`` opts into the relationship-driven dynamic-EQ de-mask
    stage (default off, listening-gated — see docs/DETECT_CORRECT_CHAIN_MAP).
    ``bus_compressor_override`` replaces the master glue compressor's default
    settings ({"ratio","attack_ms","release_ms","threshold_db","makeup_gain_db"})
    — e.g. for testing reference_track_comparison.py's dynamics_comparison()
    suggested settings to close a measured density/crest-factor gap. Default
    None = keep the decision engine's own choice.
    ``extra_bus_eq_bands`` appends caller-supplied bands (same shape as the
    verbal-feedback correction mechanism in mix_decision_engine.py:
    {"type", "frequency", "gain_db", "q"}) to the master bus EQ — e.g. for
    testing a reference-track-derived tonal correction
    (scripts/eval/reference_track_comparison.py) without changing production
    defaults. Default None = no change.
    ``apply_mono_compat_correction`` opts into a bounded stereo-narrowing pass
    on stems the mono-compatibility detector flagged warning/critical (default
    off, listening-gated — see docs/audits/2026-07-17-stranger-v6-listening-findings.md).
    ``apply_proactive_crest_reduction`` opts into density correction before the
    final LUFS gain solve when the measured crest factor is unusually wide
    (default off, listening-gated — see docs/PROJECT_ACTION_PLAN_2026-07-18.md
    §10.4). Distinct from the always-on reachability-gated crest reduction:
    this engages on measured density, not on whether the target is reachable.
    ``export_stems`` also writes each fully-processed stem as a WAV under
    ``stems_v{version}/`` so per-stem corrections can be auditioned in isolation.
    ``reference_track`` opts into an automatic end-of-render spectrum
    comparison chart (mid/side, +3dB/oct tilt) against the given audio file,
    saved under ``spectrum_comparison/`` in the delivery folder — best-effort:
    a missing matplotlib/scipy or decode failure never fails the render, it
    just skips the chart and prints a warning. Default None = no chart."""
    audio_paths = _find_stem_files(stems_dir)
    if not audio_paths:
        raise ValueError(f"No audio stems found in {stems_dir} (looked for {sorted(AUDIO_SUFFIXES)}).")

    print(f"Found {len(audio_paths)} stem(s) in {stems_dir}.")
    stems_raw = [{"name": p.name, "file_bytes": p.read_bytes()} for p in audio_paths]

    print("Classifying stems...")
    profiles = classify_stems(stems_raw, read_wav_mono_fn=read_wav_mono, max_samples=131072)

    print("Preparing and aligning stems...")
    prepared_stems = prepare_stems(
        stems_raw, read_wav_mono_fn=read_wav_mono,
        target_sample_rate=44100, trim=True, normalise=False, max_samples=0,
        masking_preview_max_samples=65536,  # piggyback analyze_stems_masking's preview onto this decode
    )
    # Captured before correct_stem_polarity mutates prepared_stems, so masking
    # analysis keeps seeing pre-correction audio -- same as the independent
    # re-decode it replaces.
    _preview_by_name = {
        s["name"]: (s.get("masking_preview_samples"), s.get("masking_preview_sample_rate"))
        for s in prepared_stems
    }
    for _s in stems_raw:
        _preview = _preview_by_name.get(_s.get("name"))
        if _preview and _preview[0] is not None:
            _s["masking_preview_samples"], _s["masking_preview_sample_rate"] = _preview

    try:
        polarity_sr = prepared_stems[0].get("sample_rate", 44100) if prepared_stems else 44100
        prepared_stems, polarity_report = correct_stem_polarity(prepared_stems, polarity_sr)
        for name, entry in polarity_report.items():
            fixes = []
            if entry["polarity_flipped"]:
                fixes.append(f"polarity flipped (rel. '{entry['inverted_relative_to']}')")
            if entry["time_shifted"]:
                fixes.append(f"delayed {entry['lag_samples_corrected']} samples (aligned to '{entry['aligned_to']}')")
            print(f"Corrected '{name}': {', '.join(fixes)}.")
    except Exception as exc:
        print(f"Phase/polarity correction failed; continuing without it: {exc}")

    print("Analyzing masking...")
    masking_results = analyze_stems_masking(stems_raw, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)

    print("Generating mix plan...")
    plan = generate_mix_plan(profiles, masking_results, genre=genre, target_lufs=target_lufs)
    roles = apply_role_corrections(
        infer_musical_roles(profiles, prepared_stems), role_corrections
    )
    plan.musical_roles = [role.to_dict() for role in roles]
    plan.arrangement = apply_arrangement_corrections(
        infer_arrangement(prepared_stems),
        arrangement_corrections,
        [str(stem.get("name")) for stem in prepared_stems],
    ).to_dict()
    plan.mono_compatibility = analyze_mono_compatibility(
        prepared_stems, plan.arrangement
    ).to_dict()
    existing_dynamics = analyze_stems_for_dynamics(
        prepared_stems, profiles,
        prepared_stems[0]["sample_rate"] if prepared_stems else 44_100,
    )
    plan.relationships = [relationship.to_dict() for relationship in infer_relationships(
        profiles, masking_results, roles, plan.arrangement, prepared_stems,
        existing_dynamics,
    )]
    plan.automation_preview = build_automation_preview(plan.relationships).to_dict()
    plan.apply_masking_corrections = apply_masking
    if apply_masking:
        actionable = sum(1 for r in plan.relationships if r.get("status") == "candidate")
        print(f"Masking corrections ENABLED — {actionable} actionable relationship(s) available.")

    plan.apply_mono_compat_correction = apply_mono_compat_correction
    if apply_mono_compat_correction:
        flagged = sum(1 for s in plan.mono_compatibility.get("stems", []) if s.get("severity") in ("warning", "critical"))
        print(f"Mono-compatibility correction ENABLED — {flagged} flagged stem(s) available.")

    plan.apply_proactive_crest_reduction = apply_proactive_crest_reduction
    if apply_proactive_crest_reduction:
        print("Proactive crest-factor reduction ENABLED.")

    if extra_bus_eq_bands:
        plan.bus.bus_eq_bands.extend(extra_bus_eq_bands)
        print(f"Extra master bus EQ bands ENABLED — {len(extra_bus_eq_bands)} band(s) appended.")

    # OPT-IN boost-only low-end lift. The default local render leaves the low end
    # ~5-6x under a commercial master (no active low-end target -- see
    # docs/audits/2026-07-23-render-speed-and-bass-findings.md). A single
    # BOOST-ONLY master low-shelf is the approach prior blind listening ACCEPTED
    # ("B is great" at +4.5 dB), where the cut-heavy multi-band reference-match was
    # rejected for dulling the mix (see the reference-track-comparison history).
    # Perceptual change -> opt-in only, listening-gate before any default.
    if bass_boost_db and bass_boost_db > 0.0:
        plan.bus.bus_eq_bands.append({
            "type": "lowshelf",
            "frequency": float(bass_boost_hz),
            "gain_db": float(bass_boost_db),
            "q": 0.707,
            "reason": f"Bass boost: +{bass_boost_db:.1f} dB low-shelf @ {bass_boost_hz:.0f} Hz "
                      f"(boost-only low-end lift, opt-in).",
        })
        print(f"Bass boost ENABLED — +{bass_boost_db:.1f} dB low-shelf @ {bass_boost_hz:.0f} Hz (boost-only).")

    if bus_compressor_override:
        plan.bus.bus_compressor = bus_compressor_override
        print(f"Bus compressor OVERRIDDEN — {bus_compressor_override}")

    render_fn = (
        functools.partial(mix_and_render_stems, capture_stem_audio=True)
        if export_stems else mix_and_render_stems
    )

    # OPT-IN static reference match: measure a PROBE render's spectrum vs the
    # reference on log bands, derive a boost-biased/deadbanded master match-EQ
    # (+ optional dynamics), fold it into the plan, then run the validated render
    # ONCE with the match already applied. #4: one probe render + one validate
    # loop replaces two full validate loops (the match is still quality-gated --
    # it goes through the same validate_and_correct_mix below). The probe's
    # spectral SHAPE equals the final render's (the gain solve is uniform gain).
    if match_reference:
        if reference_track is None:
            raise ValueError("match_reference=True requires a reference_track.")
        print("Probe render to measure the mix spectrum for reference matching...")
        probe = mix_and_render_stems(prepared_stems, plan)
        match_bands = _compute_reference_match_bands(
            probe["mixdown_wav_bytes"], Path(reference_track),
        )
        if match_bands:
            plan.bus.bus_eq_bands.extend(match_bands)
            lo = [b for b in match_bands if b["frequency"] < 300 and b["gain_db"] > 0]
            low_lift = max((b["gain_db"] for b in lo), default=0.0)
            print(f"Reference match ENABLED — {len(match_bands)} master EQ band(s) "
                  f"(peak low-end lift +{low_lift:.1f} dB).")
        if match_dynamics:
            comp = _compute_reference_dynamics_comp(
                probe["mixdown_wav_bytes"], Path(reference_track),
            )
            if comp:
                plan.bus.bus_compressor = comp
                print(f"Dynamics match ENABLED — bus glue comp ratio {comp['ratio']:.1f}:1, "
                      f"attack {comp['attack_ms']:.0f}ms, release {comp['release_ms']:.0f}ms, "
                      f"threshold {comp['threshold_db']:.1f} dBFS (mix more dynamic than reference).")
            else:
                print("Dynamics match: mix already at/below the reference's density; no compression added.")
        if match_width:
            # Re-probe with the spectral-match EQ (if any) already folded into
            # the plan: a low-end boost is heavily mid/mono-weighted and
            # mechanically drags the broadband side/mid width ratio down as a
            # side effect (measured ~33% relative on a real render), so
            # deciding width from the PRE-EQ probe above would judge against
            # a width the delivered mix won't actually have.
            width_probe = mix_and_render_stems(prepared_stems, plan) if match_bands else probe
            width_factor = _compute_reference_width_factor(
                width_probe["mixdown_wav_bytes"], Path(reference_track),
            )
            if width_factor is not None:
                plan.bus.reference_width_factor = width_factor
                print(f"Width match ENABLED — nudged x{width_factor:.3f} toward the reference's stereo width "
                      f"(similar-to, not matched -- see compute_reference_width_factor for the safety bounds).")
            else:
                print("Width match: mix already within the deadband of the reference's width, or no stereo "
                      "content to compare; no width change.")

    print("Rendering and validating (this can take a while)...")
    render_result = validate_and_correct_mix(
        prepared_stems, plan, render_fn=render_fn, max_iterations=3,
    )

    gate = render_result.get("quality_gate", {})
    if not gate.get("passed", False):
        failures = gate.get("hard_failures") or ["render safety was not established"]
        raise RuntimeError("Mix failed delivery safety gate: " + "; ".join(map(str, failures)))

    print("Packaging delivery...")
    delivery = package_mixdown_delivery(
        project_id=project_id, render_result=render_result, output_dir=output_dir,
    )

    # Spectrum chart needs a single audio file; a genre-folder reference (used
    # for matching) has no single spectrum to chart, so skip it cleanly.
    if reference_track is not None and Path(reference_track).is_file():
        try:
            chart_path = _render_reference_spectrum_chart(
                mixdown_wav_path=Path(delivery["wav_path"]),
                reference_track=Path(reference_track),
                output_dir=Path(delivery["wav_path"]).parent / "spectrum_comparison",
                version=delivery.get("version"),
                mix_label=project_id,
            )
            delivery["spectrum_comparison_path"] = str(chart_path)
            print(f"Spectrum comparison chart -> {chart_path}")
        except Exception as exc:
            print(f"Spectrum comparison chart skipped (non-fatal): {exc}")

    return delivery


def _render_reference_spectrum_chart(
    *, mixdown_wav_path: Path, reference_track: Path, output_dir: Path,
    version: int | None, mix_label: str,
) -> Path:
    """Best-effort end-of-render spectrum-vs-reference chart. Imported
    lazily (matplotlib/scipy are eval-tier deps, not part of the core
    pipeline's requirements) so a missing dependency degrades to a skipped
    chart, never a failed render."""
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))
    from spectrum_plot import render_mid_side_spectrum_comparison  # noqa: E402

    mix_data = read_wav_mono(mixdown_wav_path.read_bytes(), max_samples=0, as_arrays=True)
    ref_data = read_wav_mono(reference_track.read_bytes(), max_samples=0, as_arrays=True)

    def _lr(data: dict) -> tuple:
        left = data["left_samples"] if data["left_samples"] is not None and len(data["left_samples"]) else data["samples"]
        right = data["right_samples"] if data["right_samples"] is not None and len(data["right_samples"]) else data["samples"]
        return left, right

    mix_l, mix_r = _lr(mix_data)
    ref_l, ref_r = _lr(ref_data)

    version_suffix = f"_v{version}" if version is not None else ""
    output_path = output_dir / f"mixdown{version_suffix}_vs_{reference_track.stem}.png"
    return render_mid_side_spectrum_comparison(
        mix_left=mix_l, mix_right=mix_r, mix_sr=mix_data["sample_rate"],
        ref_left=ref_l, ref_right=ref_r, ref_sr=ref_data["sample_rate"],
        mix_label=mix_label, ref_label=reference_track.stem,
        output_path=output_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stems_dir", help="Folder containing stem audio files.")
    parser.add_argument("--genre", default="pop", help="Genre modifier (default: pop).")
    parser.add_argument("--target-lufs", type=float, default=None, help="Target integrated loudness (default: genre-appropriate).")
    parser.add_argument("--output", default="./automix-output", help="Output directory (default: ./automix-output).")
    parser.add_argument("--project-id", default="local-mix", help="Label used for output filenames (default: local-mix).")
    parser.add_argument(
        "--role-corrections",
        help="JSON file mapping exact stem names to {role, priority} corrections.",
    )
    parser.add_argument(
        "--arrangement-corrections",
        help="JSON file containing a complete audio-too.arrangement-correction.v1 timeline.",
    )
    parser.add_argument(
        "--apply-masking",
        action="store_true",
        help="Apply relationship-driven dynamic-EQ de-mask corrections (default off, listening-gated).",
    )
    parser.add_argument(
        "--apply-mono-compat-correction",
        action="store_true",
        help="Apply bounded stereo-narrowing to stems flagged by the mono-compatibility detector (default off, listening-gated).",
    )
    parser.add_argument(
        "--apply-proactive-crest-reduction",
        action="store_true",
        help="Apply density correction before the final LUFS gain solve when measured crest factor is unusually wide (default off, listening-gated).",
    )
    parser.add_argument(
        "--export-stems",
        action="store_true",
        help="Also write each fully-processed stem as a WAV under stems_v{version}/ for isolated auditioning.",
    )
    parser.add_argument(
        "--reference-track",
        help="Audio file (or, with --match-reference, a DIRECTORY of same-genre references for a robust median genre-average target) to match/compare against. Writes a mid/side spectrum comparison chart under spectrum_comparison/ (best-effort, requires matplotlib+scipy).",
    )
    parser.add_argument(
        "--bass-boost", type=float, default=0.0, metavar="DB",
        help="Apply a BOOST-ONLY master low-shelf of DB dB to lift the low end (the default render lands ~5-6x under a commercial master). Prior blind listening accepted ~+4.5 dB. Perceptual -- opt-in, A/B before trusting as default. Off (0.0) by default.",
    )
    parser.add_argument(
        "--bass-boost-hz", type=float, default=120.0, metavar="HZ",
        help="Corner frequency for --bass-boost low-shelf (default 120 Hz).",
    )
    parser.add_argument(
        "--match-reference", action="store_true",
        help="Static, boost-biased spectral match to --reference-track (two-pass: render, measure log-band gap, apply a deadbanded/boost-biased master match-EQ, re-render). Moves the mix's spectral balance toward the reference for its genre. Perceptual -- opt-in; validate by the reference-comparison score.",
    )
    parser.add_argument(
        "--match-dynamics", action="store_true",
        help="With --match-reference: also match density -- if the mix is more dynamic (higher crest) than the reference, add the bus glue compression dynamics_comparison suggests to bring loudness density closer. Perceptual -- opt-in.",
    )
    parser.add_argument(
        "--match-width", action="store_true",
        help="With --match-reference: also nudge the master stereo width toward the reference's own width. Deliberately gentle -- similar-to, not matched-to (35%% of the way, +/-15%% hard clamp, 15%% deadband) to avoid the phase/mono-compatibility risk of a hard M/S width match. Perceptual -- opt-in.",
    )
    args = parser.parse_args()

    stems_dir = Path(args.stems_dir).expanduser().resolve()
    if not stems_dir.is_dir():
        print(f"FAILED: {stems_dir} is not a directory.")
        return 1

    output_dir = Path(args.output).expanduser().resolve()
    try:
        role_corrections = None
        if args.role_corrections:
            correction_path = Path(args.role_corrections).expanduser().resolve()
            role_corrections = validate_role_correction_payload(
                json.loads(correction_path.read_text(encoding="utf-8"))
            )
        arrangement_corrections = None
        if args.arrangement_corrections:
            correction_path = Path(args.arrangement_corrections).expanduser().resolve()
            arrangement_corrections = validate_arrangement_correction_payload(
                json.loads(correction_path.read_text(encoding="utf-8"))
            )
        delivery = run_local_automix(
            stems_dir, genre=args.genre, target_lufs=args.target_lufs,
            output_dir=output_dir, project_id=args.project_id,
            role_corrections=role_corrections,
            arrangement_corrections=arrangement_corrections,
            apply_masking=args.apply_masking,
            apply_mono_compat_correction=args.apply_mono_compat_correction,
            apply_proactive_crest_reduction=args.apply_proactive_crest_reduction,
            export_stems=args.export_stems,
            reference_track=Path(args.reference_track).expanduser().resolve() if args.reference_track else None,
            bass_boost_db=args.bass_boost,
            bass_boost_hz=args.bass_boost_hz,
            match_reference=args.match_reference,
            match_dynamics=args.match_dynamics,
            match_width=args.match_width,
        )
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1

    print(f"OK: mix package written to {delivery.get('zip_path')}")
    stem_paths = delivery.get("stem_paths") or {}
    if stem_paths:
        first = next(iter(stem_paths.values()))
        print(f"    {len(stem_paths)} processed stems written to {Path(first).parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
