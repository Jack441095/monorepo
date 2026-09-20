from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.analysis_core.analysis_core import AnalysisContext, analyze_wav as core_analyze_wav  # noqa: E402
from audio_analysis.analysis_core.analysis_features import (  # noqa: E402
    analyze_spectrum_and_correlation,
    dynamic_profile,
    stereo_field_summary,
    tonal_balance_summary,
)
from audio_analysis.analysis_core.analysis_interpretation import priority_actions, review_flags  # noqa: E402
from audio_analysis.analysis_core.audio_scanner import ScanContext, scan_audio_files  # noqa: E402
from audio_analysis.mix_review.review_workflow import ReviewWorkflowContext, apply_version_and_reference_context  # noqa: E402


def test_analysis_core_uses_typed_context() -> None:
    samples = [0.0, 0.2, -0.2, 0.1] * 32

    def diagnostic_lufs(left, right, sample_rate, *, diagnostics=None):
        if diagnostics is not None:
            diagnostics.append("LUFS fallback used in test.")
        return -18.0

    context = AnalysisContext(
        ableton_repair_chain_export=lambda report: {"chains": []},
        ableton_repair_templates=lambda flags, metrics: [],
        advice_from_metrics=lambda metrics, flags, **kwargs: ["advice"],
        analyze_spectrum_and_correlation=lambda left, right, sample_rate: ({}, {}, {}),
        annotate_flags=lambda flags: flags,
        band_ratios=lambda magnitudes, sample_rate, n, perceptual=False, **kwargs: {"sub": 0.01, "bass": 0.02, "low_mids": 0.03, "mids": 0.5, "presence": 0.2, "sibilance": 0.1, "air": 0.14},
        calculate_lufs=diagnostic_lufs,
        calculate_true_peak=lambda left, right, sample_rate, raw_bytes: -2.0,
        closed_loop_action_plan=lambda report: {"steps": []},
        decode_audio_bytes=lambda file_bytes, filename: {"wav_bytes": b"wav", "decoder": "wave", "source_format": "wav"},
        detect_chords_and_key=lambda samples, sample_rate: {"estimated_key": "C Major", "progression": []},
        dynamic_profile=lambda samples, sample_rate, peak_db, rms_db, window_values: {"profile": "Controlled"},
        frequency_repair_map=lambda metrics, flags, **kwargs: [],
        goal_target_checks=lambda metrics, **kwargs: {"checks": []},
        leading_silence_seconds=lambda samples, sample_rate: 0.0,
        lesson_cards=lambda flags, goal: [],
        loudness_profile=lambda left, right, sample_rate: {"integrated_lufs": -18.0, "momentary_max_lufs": -16.0, "short_term_max_lufs": -17.0, "loudness_range_lu": 5.0},
        mix_goal_info=lambda value: {"key": value, "label": "Premaster"},
        perceptual_summary=lambda perceived, **kwargs: {"dominant_band": "mids"},
        priority_actions=lambda metrics, flags: [{"rank": 1, "action": "listen"}],
        rating_from_score=lambda score: "Clean technical pass",
        read_wav_mono=lambda wav_bytes, max_samples=65536: {
            "samples": samples,
            "left_samples": samples,
            "right_samples": samples,
            "sample_rate": 44100,
            "analysis_sample_rate": 44100,
            "channels": 2,
            "duration_seconds": 1.0,
            "peak": 0.2,
            "left_peak": 0.2,
            "right_peak": 0.2,
            "clipped_frames_estimate": 0,
            "stereo_balance": 1.0,
        },
        refresh_report_interpretation=lambda report: report.update({"judgment": {"ok": True}}),
        report_summary=lambda metrics, flags: "summary",
        review_flags=lambda metrics: [],
        revision_lesson=lambda report: {"steps": []},
        section_analysis=lambda samples, left, right, sample_rate: {"sections": []},
        source_hypotheses=lambda metrics, flags: [],
        spectral_features=lambda magnitudes, sample_rate, n: {"centroid_hz": 1000},
        spectrum_magnitudes=lambda samples, sample_rate: ([1.0, 0.5], 4),
        ms_band_ratio=lambda mid, side: {k: 0.5 for k in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air")},
        stereo_correlation_timeline=lambda left, right, sr: {"window_seconds": 0.1, "timestamps": [], "correlation": [], "balance": [], "dip_events": [], "vectorscope_points": []},
        stereo_field_summary=lambda metrics: {"image": "Stable"},
        stereo_metrics=lambda left, right: {"stereo_correlation": 1.0, "stereo_width_ratio": 0.0},
        technical_score=lambda flags: 100,
        tonal_balance_summary=lambda bands, perceived, features: {"profile": "Balanced"},
        trailing_silence_seconds=lambda samples, sample_rate: 0.0,
        windowed_rms_values=lambda samples, sample_rate: [-20.0, -19.0],
        analyze_thd_n=lambda samples, fs: {"thd": 0.0, "even_thd": 0.0, "odd_thd": 0.0, "thd_n": 0.0, "fundamental_hz": 440.0},
        detect_resonances=lambda samples, fs: [],
        detect_isp=lambda samples: (0.2, 0.2),
    )

    report = core_analyze_wav(b"fake", "mix.wav", mix_goal="premaster", context=context)

    assert report["metrics"]["technical_score"] == 100
    assert report["metrics"]["chords"]["estimated_key"] == "C Major"
    assert "LUFS fallback used in test." in report["analysis_diagnostics"]
    assert report["judgment"]["ok"] is True


def test_audio_scanner_uses_scan_context(tmp_path) -> None:
    audio_path = tmp_path / "mix.wav"
    audio_path.write_bytes(b"audio")

    context = ScanContext(
        discover_paths=lambda root, recursive=True: [audio_path],
        decode_audio_file=lambda path: {"wav_bytes": b"wav", "decoder": "wave", "source_format": "wav"},
        analyze_wav=lambda wav_bytes, filename, mix_goal="premaster": {
            "summary": "ok",
            "metrics": {"duration_seconds": 2.0, "filename": filename},
            "technical_metrics": {},
            "judgment": {},
            "flags": [],
            "action_plan": [],
            "closed_loop_action_plan": {},
            "ableton_repair_chains": {},
        },
        compare_metrics=lambda mix, reference: {},
        comparison_advice=lambda comparison: [],
        reference_coaching=lambda comparison, metrics, payload: {},
        report_summary=lambda metrics, flags, comparison=None: "summary",
        priority_actions=lambda metrics, flags, comparison=None: [],
        revision_lesson=lambda report: {},
        refresh_report_interpretation=lambda report: report,
        refresh_closed_loop_payloads=lambda report: report,
        kenn_handoff=lambda report: {"schema": "test"},
        mix_goal_info=lambda goal: {"key": goal},
    )

    result = scan_audio_files(tmp_path, recursive=True, mix_goal="premaster", reference_path=None, context=context)

    assert result["summary"]["found"] == 1
    assert result["items"][0]["kenn_handoff"]["schema"] == "test"


def test_review_workflow_context_applies_reference_and_version() -> None:
    report = {"metrics": {"technical_score": 80}, "flags": [], "summary": "before", "action_plan": []}
    context = ReviewWorkflowContext(
        analyze_wav=lambda *args, **kwargs: report,
        compare_metrics=lambda current, previous: {"rms_delta_db": 1.0},
        comparison_advice=lambda comparison: ["compare"],
        connect=lambda: None,
        find_similar_reviews=lambda fv, exclude_review_id=None: [],
        generate_mix_critique=lambda report: {"text": "critique"},
        generate_prose_summary=lambda report: {"mode": "deterministic", "available": False, "text": "summary"},
        init_reviews_table=lambda: None,
        latest_review_for_title=lambda title: {"id": "prev", "metrics": {"technical_score": 70}},
        max_upload_bytes=1_000_000,
        now=lambda: "now",
        priority_actions=lambda metrics, flags, comparison=None: [{"rank": 1}],
        reference_by_id=lambda reference_id: None,
        reference_envelope_for_genre=lambda genre_key: None,
        reference_coaching=lambda comparison, metrics, payload: {"headline": "reference"},
        refresh_closed_loop_payloads=lambda report: report.update({"closed_loop_action_plan": {}}),
        refresh_report_interpretation=lambda report: report.update({"judgment": {}}),
        report_root=Path("/tmp"),
        report_summary=lambda metrics, flags, comparison=None: "after",
        revision_agent_plan=lambda report: {"steps": []},
        revision_coaching=lambda report, previous: {"headline": "revision"},
        revision_impact_summary=lambda report, previous: {"verdict": "improved"},
        revision_lesson=lambda report: {"steps": []},
        upload_root=Path("/tmp"),
        validate_wav_upload=lambda *args, **kwargs: {"ok": True, "safe_name": "mix.wav"},
        version_advice=lambda comparison: ["version"],
    )

    updated = apply_version_and_reference_context(
        report,
        review_id="rev",
        review_title="Track",
        version_label="v2",
        reference_report={"metrics": {"technical_score": 90}},
        reference_safe_name="ref.wav",
        saved_reference=None,
        context=context,
    )

    assert updated["version_advice"] == ["version"]
    assert updated["comparison_advice"] == ["compare"]
    assert updated["mix_critique"]["text"] == "critique"


def test_direct_feature_and_interpretation_helpers() -> None:
    tonal = tonal_balance_summary(
        {"sub": 0.01, "bass": 0.02, "low_mids": 0.1, "mids": 0.5, "presence": 0.2, "sibilance": 0.1, "air": 0.07},
        {"presence": 0.2, "sibilance": 0.1, "air": 0.07},
        {"centroid_hz": 1200},
    )
    dynamics = dynamic_profile([0.0, 0.1, -0.1] * 1000, 44100, -1.0, -18.0, [-20.0, -18.0])
    flags = review_flags({"peak_dbfs": -0.2, "crest_factor_db": 5, "bands": {}, "perceptual_bands": {}, "true_peak_dbfs": -0.1})
    actions = priority_actions({"technical_score": 70}, flags)
    stereo = stereo_field_summary({"side_bands": {}, "correlation_bands": {}, "stereo_width_ratio": 0.2, "stereo_correlation": 0.9})

    assert tonal["profile"] in {"Balanced", "Bright", "Mid-focused", "Low-weighted"}
    assert dynamics["profile"] in {"Compressed", "Controlled", "Spiky", "Uneven"}
    assert actions
    assert stereo["image"] == "Stable"


def test_analyze_wav_does_not_force_samples_through_torch() -> None:
    """Regression test: analysis_core.analyze_wav must NOT wrap sample arrays in
    torch.Tensor before calling analyze_spectrum_and_correlation/calculate_lufs.

    On this project's numpy 2.x / torch 2.2 pin, tensor.numpy() raises, which
    silently pushed analyze_spectrum_and_correlation down a different,
    non-equivalent torch.stft code path — measured band correlation ~1.0 for
    near-decorrelated audio (should be ~0). Calling the feature function
    directly with plain arrays (what analyze_wav must pass) must stay on the
    numpy path and report near-zero correlation for two independent tones.
    """
    import math

    sample_rate = 44100
    n = sample_rate * 2
    left = [0.5 * math.sin(2 * math.pi * 440 * i / sample_rate) for i in range(n)]
    right = [0.5 * math.sin(2 * math.pi * 441 * i / sample_rate) for i in range(n)]

    _mid, _side, correlation_bands = analyze_spectrum_and_correlation(left, right, sample_rate)

    assert correlation_bands
    for band, value in correlation_bands.items():
        assert abs(value) < 0.5, (
            f"band {band!r} correlation {value} looks like the broken torch.stft "
            "path (near 1.0), not the correct near-zero numpy result"
        )
