from __future__ import annotations

import hashlib
from pathlib import Path
import sys

try:
    import numpy as np  # noqa: F401 — NUMPY_AVAILABLE used outside

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from db import connect, now
from stem_uploads import parse_multipart_form
from song_projects import get_project as get_song_project
from song_projects import set_reference_track as set_project_reference_track
from audio_analysis.mix_review.mix_review_config import (
    ABLETON_ROOT,
    AGENTS_ROOT,
    ANALYSIS_FEEDBACK_PATH,
    AUDIOGEN_ROOT,
    BUSINESS_ROOT,
    BANDS,
    CREATE_REFERENCES_SQL,
    CREATE_REVIEWS_SQL,
    DECODABLE_SUFFIXES,
    DEFAULT_MIX_GOAL,
    MAX_UPLOAD_BYTES,
    PORTFOLIO_ROOT,
    REFERENCE_ROOT,
    REPORT_ROOT,
    TARGET_CONFIG_PATH,
    UPLOAD_ROOT,
)

if str(BUSINESS_ROOT) not in sys.path:
    sys.path.insert(0, str(BUSINESS_ROOT))
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))

from agents.MixReview.revision_agent import (  # noqa: E402
    revision_agent_plan,
    revision_impact_summary,
)
from audio_analysis.integration.ableton_repairs import ableton_repair_templates
from audio_analysis.mix_review.revision_plan import next_revision_plan
from audio_analysis.integration.handoff import kenn_handoff
from audio_analysis.integration.session_report import build_session_report
from audio_analysis.analysis_core.analysis_interpretation import (  # noqa: E402
    advice_from_metrics as interpretation_advice_from_metrics,
    annotate_flags as interpretation_annotate_flags,
    band_reading as interpretation_band_reading,
    confidence_for_flag as interpretation_confidence_for_flag,
    critique_prompt_payload as interpretation_critique_prompt_payload,
    deterministic_mix_critique as interpretation_deterministic_mix_critique,
    frequency_repair_map as interpretation_frequency_repair_map,
    generate_mix_critique as interpretation_generate_mix_critique,
    generate_prose_summary as interpretation_generate_prose_summary,
    judgment_payload as interpretation_judgment_payload,
    lesson_cards as interpretation_lesson_cards,
    priority_actions as interpretation_priority_actions,
    rating_from_score as interpretation_rating_from_score,
    refresh_report_interpretation as interpretation_refresh_report_interpretation,
    report_summary as interpretation_report_summary,
    review_flags as interpretation_review_flags,
    revision_lesson as interpretation_revision_lesson,
    set_mix_critique_provider as interpretation_set_mix_critique_provider,
    source_hypotheses as interpretation_source_hypotheses,
    technical_metrics_payload as interpretation_technical_metrics_payload,
    technical_score as interpretation_technical_score,
    valid_mix_critique as interpretation_valid_mix_critique,
)
from audio_analysis.analysis_core.analysis_features import (  # noqa: E402
    analyze_spectrum_and_correlation as features_analyze_spectrum_and_correlation,
    analyze_spectrum_and_correlation_fallback as features_analyze_spectrum_and_correlation_fallback,
    analyze_spectrum_and_correlation_numpy as features_analyze_spectrum_and_correlation_numpy,
    ms_band_ratio as features_ms_band_ratio,
    stereo_correlation_timeline as features_stereo_correlation_timeline,
)
from audio_analysis.utils.audio_io_api import (  # noqa: E402, F401 — re-exported as public API
    read_wav_mono,
    _write_wav_from_float_array,
    _decode_with_soundfile_bytes,
    _decode_with_soundfile_path,
    ffmpeg_path,
    _decode_with_ffmpeg_path,
    _decode_with_ffmpeg_bytes,
    decode_audio_bytes,
    decode_audio_file,
)
from audio_analysis.analysis_core.analysis_features_api import (  # noqa: E402, F401 — re-exported as public API
    _fft,
    a_weighting_gain,
    detect_chords_and_key,
    spectrum_magnitudes,
    band_ratios,
    spectral_bands,
    perceptual_bands,
    perceptual_summary,
    percentile,
    spectral_features,
    tonal_balance_summary,
    dynamic_profile,
    section_analysis,
    stereo_field_summary,
    rms_db,
    windowed_rms_values,
    stereo_metrics,
    leading_silence_seconds,
    trailing_silence_seconds,
    metric_float,
)
from audio_analysis.analysis_core.analysis_core import AnalysisContext, analyze_wav as core_analyze_wav  # noqa: E402
from audio_analysis.analysis_core.feature_cache import get_or_analyze as cached_analyze_wav  # noqa: E402
from audio_analysis.analysis_core.audio_scanner import (  # noqa: E402
    ScanContext,
    discover_audio_paths as scanner_discover_audio_paths,
    scan_audio_benchmark as scanner_scan_audio_benchmark,
    scan_audio_files as scanner_scan_audio_files,
    validate_audio_upload as scanner_validate_audio_upload,
)
from audio_analysis.integration.ableton_exports import generate_correction_rack as ableton_generate_correction_rack  # noqa: E402
from audio_analysis.mixdown.stem_analysis import (  # noqa: E402
    analyze_stems_masking as stem_analyze_stems_masking,
    handle_stems_upload as stem_handle_stems_upload,
)
from audio_analysis.analysis_core.distortion_resonance import analyze_thd_n, detect_resonances, detect_isp
from audio_analysis.analysis_core.target_config import (  # noqa: E402
    get_mix_review_targets as target_get_mix_review_targets,
    load_goal_targets as target_load_goal_targets,
    mix_goal_info as target_mix_goal_info,
    normalize_mix_goal as target_normalize_mix_goal,
    normalize_target_check as target_normalize_target_check,
    save_mix_review_targets as target_save_mix_review_targets,
    validated_goal_targets as target_validated_goal_targets,
)
from audio_analysis.analysis_core.loudness_api import (  # noqa: E402, F401 — re-exported as public API
    get_k_filter_coefficients,
    apply_biquad,
    calculate_lufs_fallback,
    calculate_lufs_torch,
    calculate_lufs_numpy,
    calculate_lufs,
    calculate_loudness_profile,
    oversample_fft_torch,
    calculate_true_peak_torch,
    calculate_true_peak_fallback,
    calculate_true_peak_numpy,
    calculate_true_peak_numpy_efficient,
    calculate_true_peak_fallback_efficient,
    calculate_true_peak,
)
from audio_analysis.analysis_core.music_analysis import (  # noqa: E402
    batch_music_analysis as music_analysis_batch_music_analysis,
    batch_music_analysis_csv as music_analysis_batch_music_analysis_csv,
    music_analysis_from_report,
)
from audio_analysis.integration.closed_loop import (  # noqa: E402
    ableton_repair_chain_export,
    batch_qa_summary as closed_loop_batch_qa_summary,
    closed_loop_action_plan,
)
from audio_analysis.integration.comparison import (  # noqa: E402
    compare_metrics as comparison_compare_metrics,
    comparison_advice as comparison_comparison_advice,
    reference_coaching as comparison_reference_coaching,
    revision_coaching as comparison_revision_coaching,
    track_timeline as comparison_track_timeline,
    version_advice as comparison_version_advice,
)
from audio_analysis.integration.report_rendering import report_html as render_report_html  # noqa: E402
from audio_analysis.mix_review.review_store import (  # noqa: E402
    _cache_report_summary as store_cache_report_summary,
    init_reviews_table as store_init_reviews_table,
    latest_review_for_title as store_latest_review_for_title,
    list_reviews as store_list_reviews,
    normalize_title as store_normalize_title,
    numeric_delta as store_numeric_delta,
    read_report as store_read_report,
    record_review_feedback as store_record_review_feedback,
    repair_chains_json_bytes as store_repair_chains_json_bytes,
    report_json_bytes as store_report_json_bytes,
    review_audio_path as store_review_audio_path,
    review_by_id as store_review_by_id,
    review_history as store_review_history,
    update_revision_agent_step as store_update_revision_agent_step,
    find_similar_reviews as store_find_similar_reviews,
)
from audio_analysis.integration.reference_store import (  # noqa: E402
    ReferenceStoreContext,
    handle_multipart_reference as reference_handle_multipart_reference,
    list_references as reference_list_references,
    reference_by_id as reference_reference_by_id,
    reference_envelope_for_genre as reference_reference_envelope_for_genre,
    save_reference as reference_save_reference,
)
from audio_analysis.mix_review.review_workflow import (  # noqa: E402
    ReviewArtifactRegistry,
    ReviewWorkflowContext,
    background_analyze as workflow_background_analyze,
    handle_multipart_music_analysis as workflow_handle_multipart_music_analysis,
    handle_multipart_review as workflow_handle_multipart_review,
    mix_review_status as workflow_mix_review_status,
    save_review as workflow_save_review,
)
from audio_analysis.mix_review.mix_review_critique import (  # noqa: E402
    generate_critique as stage10_generate_critique,
)
from audio_analysis.mix_review.mix_style_classifier import (  # noqa: E402
    classify_mix_style as stage10_classify_mix_style,
)

_DEFAULT_CONNECT = connect


def _review_artifact_registry() -> ReviewArtifactRegistry | None:
    """Wire platform artifacts at the application seam, not inside DSP modules."""
    if connect is not _DEFAULT_CONNECT:
        return None
    try:
        import artifact_store
        import event_store
    except ImportError:
        return None
    return ReviewArtifactRegistry(
        prepare=artifact_store.prepare_blob,
        register=artifact_store.register_prepared,
        discard=artifact_store.discard_unreferenced_blob,
        public=artifact_store.public_record,
        by_external_key=artifact_store.get_by_external_key,
        emit=event_store.append_in_transaction,
    )

if str(BUSINESS_ROOT) not in sys.path:
    sys.path.insert(0, str(BUSINESS_ROOT))
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))


if str(ABLETON_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ABLETON_ROOT.parent))


def init_reviews_table() -> None:
    registry = _review_artifact_registry()
    if registry is not None:
        import artifact_store

        artifact_store.ensure_schema()
    store_init_reviews_table(
        upload_root=UPLOAD_ROOT,
        report_root=REPORT_ROOT,
        reference_root=REFERENCE_ROOT,
        create_sql=CREATE_REVIEWS_SQL,
        create_references_sql=CREATE_REFERENCES_SQL,
        connect_func=connect,
    )


def normalize_title(value: str) -> str:
    return store_normalize_title(value)


def normalize_mix_goal(value: str) -> str:
    return target_normalize_mix_goal(value)


def mix_goal_info(value: str) -> dict:
    return target_mix_goal_info(value)


def normalize_target_check(spec: dict) -> dict | None:
    return target_normalize_target_check(spec)


def validated_goal_targets(raw: dict) -> dict:
    return target_validated_goal_targets(raw)


def load_goal_targets(path: Path | None = None) -> dict:
    return target_load_goal_targets(path or TARGET_CONFIG_PATH)


def get_mix_review_targets() -> dict:
    return target_get_mix_review_targets(TARGET_CONFIG_PATH)


def save_mix_review_targets(targets: dict) -> dict:
    return target_save_mix_review_targets(targets, path=TARGET_CONFIG_PATH)


def read_report(report_name: str) -> dict:
    return store_read_report(REPORT_ROOT, report_name)


def review_by_id(review_id: str) -> dict | None:
    return store_review_by_id(
        review_id, report_root=REPORT_ROOT, init_func=init_reviews_table, connect_func=connect
    )


def update_revision_agent_step(review_id: str, step_id: str, status: str) -> dict:
    """Persist a revision agent checklist step status in the saved report."""
    return store_update_revision_agent_step(
        review_id,
        step_id,
        status,
        report_root=REPORT_ROOT,
        init_func=init_reviews_table,
        connect_func=connect,
    )


def version_diff(review_id_a: str, review_id_b: str | None = None) -> dict:
    """Return a clean diff between two review versions.

    If ``review_id_b`` is None, compares ``review_id_a`` against its
    previous version (auto-discovered by matching title).

    Returns a dict with 'ok', 'narrative', 'deltas', 'cleared', 'new_flags',
    and a single-line 'narrative_line' for LLM context handoff.
    """
    from audio_analysis.mix_review.revision_narrative import version_diff as _run_version_diff

    report_a = review_by_id(review_id_a)
    if not report_a:
        return {"ok": False, "error": f"Review not found: {review_id_a}"}

    report_b: dict | None = None
    if review_id_b:
        report_b = review_by_id(review_id_b)
        if not report_b:
            return {"ok": False, "error": f"Review not found: {review_id_b}"}
    else:
        # Auto-discover previous version by matching title
        title = str(report_a.get("title", "")).strip()
        if not title:
            return {"ok": False, "error": "Review has no title — cannot find previous version."}
        previous = latest_review_for_title(title)
        if previous and str(previous.get("id", "")) != review_id_a:
            report_b = previous

    return _run_version_diff(report_a, report_b)


def record_review_feedback(
    review_id: str, decision: str, note: str = "", *, path: Path | None = None
) -> dict:
    return store_record_review_feedback(
        review_id,
        decision,
        note,
        path=path or ANALYSIS_FEEDBACK_PATH,
        review_lookup=review_by_id,
        report_reader=read_report,
    )


def latest_review_for_title(title: str) -> dict | None:
    return store_latest_review_for_title(
        title, report_root=REPORT_ROOT, init_func=init_reviews_table, connect_func=connect
    )


def _reference_store_context() -> ReferenceStoreContext:
    return ReferenceStoreContext(
        analyze_wav=analyze_wav,
        connect=connect,
        init_reviews_table=init_reviews_table,
        now=now,
        reference_root=REFERENCE_ROOT,
        validate_wav_upload=validate_wav_upload,
    )


def save_reference(
    *,
    file_bytes: bytes,
    filename: str,
    name: str = "",
    style: str = "",
) -> dict:
    return reference_save_reference(
        file_bytes=file_bytes,
        filename=filename,
        name=name,
        style=style,
        context=_reference_store_context(),
    )


def list_references(limit: int = 100) -> list[dict]:
    return reference_list_references(limit, init_reviews_table=init_reviews_table, connect=connect)


def reference_by_id(reference_id: str) -> dict | None:
    return reference_reference_by_id(
        reference_id, init_reviews_table=init_reviews_table, connect=connect
    )


def reference_envelope_for_genre(genre_key: str) -> dict | None:
    return reference_reference_envelope_for_genre(
        genre_key, init_reviews_table=init_reviews_table, connect=connect
    )


def handle_multipart_reference(content_type: str, body: bytes) -> dict:
    return reference_handle_multipart_reference(
        content_type,
        body,
        parse_multipart_form=parse_multipart_form,
        save_reference=save_reference,
    )


def analyze_spectrum_and_correlation_fallback(
    left: list[float], right: list[float], sample_rate: int
) -> tuple[dict, dict, dict]:
    return features_analyze_spectrum_and_correlation_fallback(left, right, sample_rate)


def analyze_spectrum_and_correlation_numpy(L: list[float], R: list[float], sample_rate: int) -> tuple[dict, dict, dict]:
    return features_analyze_spectrum_and_correlation_numpy(L, R, sample_rate)


def analyze_spectrum_and_correlation(
    left_samples: list[float], right_samples: list[float], sample_rate: int
) -> tuple[dict, dict, dict]:
    return features_analyze_spectrum_and_correlation(left_samples, right_samples, sample_rate)


def ms_band_ratio(mid_bands: dict, side_bands: dict) -> dict:
    return features_ms_band_ratio(mid_bands, side_bands)


def stereo_correlation_timeline(left: list[float], right: list[float], sample_rate: float) -> dict:
    return features_stereo_correlation_timeline(left, right, sample_rate)


def nested_metric(metrics: dict, spec: dict) -> float:
    if "path" in spec:
        value = metrics
        for key in spec["path"]:
            if not isinstance(value, dict):
                return 0.0
            value = value.get(key)
        return metric_float(value)
    return metric_float(metrics.get(str(spec.get("metric", ""))))


def target_status(value: float, spec: dict) -> str:
    minimum = spec.get("min")
    maximum = spec.get("max")
    if minimum is not None and value < float(minimum):
        return "warn"
    if maximum is not None and value > float(maximum):
        return "warn"
    return "pass"


def goal_target_checks(metrics: dict, phon_level: float = 60.0) -> dict:
    goal = (
        metrics.get("mix_goal")
        if isinstance(metrics.get("mix_goal"), dict)
        else mix_goal_info(DEFAULT_MIX_GOAL)
    )
    key = str(goal.get("key") or DEFAULT_MIX_GOAL)
    targets = load_goal_targets()
    target = targets.get(key, targets[DEFAULT_MIX_GOAL])
    checks = []
    warning_count = 0
    for spec in target.get("checks", []):
        spec_copy = dict(spec)
        label = spec_copy.get("label", "").lower()
        path = spec_copy.get("path", [])
        
        # Apply Fletcher-Munson adjustments to limits
        is_low_end = "low end" in label or "bass" in label or "sub" in label or any(b in path for b in ["low_end_share", "sub", "bass"])
        is_high_end = "clarity" in label or "harshness" in label or "presence" in label or "air" in label or any(b in path for b in ["clarity_share", "perceived_clarity_share", "presence", "air"])
        
        if is_low_end:
            if phon_level < 50.0:
                # Quiet: loosen limits (allow more low end to compensate for low ear sensitivity)
                if "max" in spec_copy and spec_copy["max"] is not None:
                    spec_copy["max"] = round(float(spec_copy["max"]) * 1.08, 3)
                if "min" in spec_copy and spec_copy["min"] is not None:
                    spec_copy["min"] = round(float(spec_copy["min"]) * 0.90, 3)
            elif phon_level >= 75.0:
                # Loud: tighten limits (stricter low end since ear sensitivity is high)
                if "max" in spec_copy and spec_copy["max"] is not None:
                    spec_copy["max"] = round(float(spec_copy["max"]) * 0.95, 3)
                if "min" in spec_copy and spec_copy["min"] is not None:
                    spec_copy["min"] = round(float(spec_copy["min"]) * 1.05, 3)
        elif is_high_end:
            if phon_level < 50.0:
                # Quiet: loosen limits slightly
                if "max" in spec_copy and spec_copy["max"] is not None:
                    spec_copy["max"] = round(float(spec_copy["max"]) * 1.05, 3)
            elif phon_level >= 75.0:
                # Loud: tighten harshness/clarity limits
                if "max" in spec_copy and spec_copy["max"] is not None:
                    spec_copy["max"] = round(float(spec_copy["max"]) * 0.92, 3)

        value = nested_metric(metrics, spec_copy)
        status = target_status(value, spec_copy)
        
        min_val = spec_copy.get("min")
        max_val = spec_copy.get("max")
        if min_val is not None and max_val is not None:
            target_desc = f"{min_val} to {max_val}"
        elif min_val is not None:
            target_desc = f"above {min_val}"
        elif max_val is not None:
            target_desc = f"below {max_val}"
        else:
            target_desc = spec_copy.get("target", "")

        if status == "warn":
            warning_count += 1
            if min_val is not None and value < float(min_val):
                message = f"{spec_copy['label']} is below the {goal.get('label', 'selected')} target ({target_desc}) at {int(phon_level)} phon."
            else:
                message = f"{spec_copy['label']} is above the {goal.get('label', 'selected')} target ({target_desc}) at {int(phon_level)} phon."
        else:
            message = f"{spec_copy['label']} is on target ({target_desc}) at {int(phon_level)} phon."
            
        checks.append(
            {
                "label": spec_copy.get("label", "Target check"),
                "value": round(value, 3),
                "status": status,
                "target": target_desc,
                "message": message,
                "education": spec_copy.get("education", ""),
            }
        )
    return {
        "goal": goal,
        "summary": target.get("summary", ""),
        "passed": len(checks) - warning_count,
        "warnings": warning_count,
        "checks": checks,
        "config_path": str(TARGET_CONFIG_PATH),
    }


def review_flags(metrics: dict) -> list[dict]:
    return interpretation_review_flags(metrics)


def confidence_for_flag(flag: dict) -> str:
    return interpretation_confidence_for_flag(flag)


def annotate_flags(flags: list[dict]) -> list[dict]:
    return interpretation_annotate_flags(flags)


def technical_score(flags: list[dict]) -> int:
    return interpretation_technical_score(flags)


def rating_from_score(score: int) -> str:
    return interpretation_rating_from_score(score)


def technical_metrics_payload(metrics: dict) -> dict:
    """Objective measurements without advice, scoring, or repair judgment."""
    return interpretation_technical_metrics_payload(metrics)


def judgment_payload(
    metrics: dict, flags: list[dict], actions: list[dict], advice: list[str], summary: str
) -> dict:
    """Goal-aware interpretation built from the objective measurements."""
    return interpretation_judgment_payload(metrics, flags, actions, advice, summary)


def refresh_report_interpretation(report: dict) -> dict:
    return interpretation_refresh_report_interpretation(report)


def priority_actions(
    metrics: dict, flags: list[dict], comparison: dict | None = None
) -> list[dict]:
    return interpretation_priority_actions(metrics, flags, comparison)


def report_summary(metrics: dict, flags: list[dict], comparison: dict | None = None) -> str:
    return interpretation_report_summary(metrics, flags, comparison)


def compare_metrics(mix_metrics: dict, reference_metrics: dict) -> dict:
    return comparison_compare_metrics(mix_metrics, reference_metrics, BANDS)


def comparison_advice(comparison: dict) -> list[str]:
    return comparison_comparison_advice(comparison)


def reference_coaching(comparison: dict, mix_metrics: dict, reference_payload: dict) -> dict:
    return comparison_reference_coaching(
        comparison,
        mix_metrics,
        reference_payload,
        metric_float=metric_float,
        mix_goal_info=mix_goal_info,
    )


def version_advice(comparison: dict) -> list[str]:
    return comparison_version_advice(comparison)


def deterministic_mix_critique(report: dict) -> str:
    return interpretation_deterministic_mix_critique(report)


def valid_mix_critique(text: str) -> bool:
    return interpretation_valid_mix_critique(text)


def critique_prompt_payload(report: dict) -> dict:
    return interpretation_critique_prompt_payload(report)


def generate_mix_critique(report: dict) -> dict:
    return interpretation_generate_mix_critique(report)


def generate_prose_summary(report: dict) -> dict:
    return interpretation_generate_prose_summary(report)


def find_similar_reviews(feature_vector: dict, *, exclude_review_id: str | None = None) -> list[dict]:
    return store_find_similar_reviews(
        feature_vector, connect_func=connect, exclude_review_id=exclude_review_id
    )


def set_mix_critique_provider(provider) -> None:
    interpretation_set_mix_critique_provider(provider)


def generate_mix_review_critique(report: dict, *, allow_llm: bool = True) -> dict:
    """Stage 10 AI-augmented critique (distinct from the legacy ``mix_critique``
    field above): covers the Stage 10 metrics specifically (section-LRA
    spread, stereo asymmetry, transient preservation, stem masking).
    Env-gated by ``MIX_REVIEW_CRITIQUE_ENABLED``; always returns usable text
    via its deterministic fallback when the LLM path is off/unavailable."""
    return stage10_generate_critique(report, allow_llm=allow_llm)


def classify_mix_style(report: dict) -> dict:
    """Stage 10 deterministic era / loudness-war / vintage-modern / genre
    classification, purely from measured metrics (no LLM)."""
    return stage10_classify_mix_style(report)


def advice_from_metrics(
    metrics: dict, flags: list[dict] | None = None, phon_level: float = 60.0
) -> list[str]:
    return interpretation_advice_from_metrics(metrics, flags, phon_level=phon_level)


def source_hypotheses(metrics: dict, flags: list[dict]) -> list[dict]:
    return interpretation_source_hypotheses(metrics, flags)


def band_reading(value: float, band_info: dict) -> str:
    return interpretation_band_reading(value, band_info)


def frequency_repair_map(
    metrics: dict, flags: list[dict], phon_level: float = 60.0
) -> list[dict]:
    return interpretation_frequency_repair_map(metrics, flags, phon_level=phon_level)


def lesson_cards(flags: list[dict], mix_goal: dict, *, limit: int = 4) -> list[dict]:
    return interpretation_lesson_cards(flags, mix_goal, limit=limit)


def revision_lesson(report: dict) -> dict:
    return interpretation_revision_lesson(report, mix_goal_info=mix_goal_info)


def revision_coaching(current_report: dict, previous_report: dict | None) -> dict | None:
    return comparison_revision_coaching(
        current_report,
        previous_report,
        metric_float=metric_float,
        mix_goal_info=mix_goal_info,
    )


def _analysis_core_context() -> AnalysisContext:
    return AnalysisContext(
        ableton_repair_chain_export=ableton_repair_chain_export,
        ableton_repair_templates=ableton_repair_templates,
        advice_from_metrics=advice_from_metrics,
        analyze_spectrum_and_correlation=analyze_spectrum_and_correlation,
        annotate_flags=annotate_flags,
        band_ratios=band_ratios,
        calculate_lufs=calculate_lufs,
        calculate_true_peak=calculate_true_peak,
        loudness_profile=calculate_loudness_profile,
        closed_loop_action_plan=closed_loop_action_plan,
        decode_audio_bytes=decode_audio_bytes,
        detect_chords_and_key=detect_chords_and_key,
        dynamic_profile=dynamic_profile,
        frequency_repair_map=frequency_repair_map,
        goal_target_checks=goal_target_checks,
        leading_silence_seconds=leading_silence_seconds,
        lesson_cards=lesson_cards,
        mix_goal_info=mix_goal_info,
        perceptual_summary=perceptual_summary,
        priority_actions=priority_actions,
        rating_from_score=rating_from_score,
        read_wav_mono=read_wav_mono,
        refresh_report_interpretation=refresh_report_interpretation,
        report_summary=report_summary,
        review_flags=review_flags,
        revision_lesson=revision_lesson,
        section_analysis=section_analysis,
        source_hypotheses=source_hypotheses,
        spectral_features=spectral_features,
        spectrum_magnitudes=spectrum_magnitudes,
        ms_band_ratio=ms_band_ratio,
        stereo_correlation_timeline=stereo_correlation_timeline,
        stereo_field_summary=stereo_field_summary,
        stereo_metrics=stereo_metrics,
        technical_score=technical_score,
        tonal_balance_summary=tonal_balance_summary,
        trailing_silence_seconds=trailing_silence_seconds,
        windowed_rms_values=windowed_rms_values,
        analyze_thd_n=analyze_thd_n,
        detect_resonances=detect_resonances,
        detect_isp=detect_isp,
    )


def _target_config_fingerprint() -> str:
    """Hash the active goal-targets config so cache keys change when it's edited."""
    try:
        data = TARGET_CONFIG_PATH.read_bytes()
    except OSError:
        return "default"
    return hashlib.sha256(data).hexdigest()[:16]


def analyze_wav(
    file_bytes: bytes, filename: str = "mix.wav", *, mix_goal: str = DEFAULT_MIX_GOAL, phon_level: float = 60.0,
    light: bool = False, include_bands: bool = True,
) -> dict:
    return cached_analyze_wav(
        file_bytes,
        filename=filename,
        mix_goal=mix_goal,
        phon_level=phon_level,
        light=light,
        include_bands=include_bands,
        target_config_fingerprint=_target_config_fingerprint(),
        analyze=lambda: core_analyze_wav(
            file_bytes, filename, mix_goal=mix_goal, context=_analysis_core_context(), phon_level=phon_level,
            light=light, include_bands=include_bands,
        ),
    )


def refresh_closed_loop_payloads(report: dict) -> dict:
    report["ableton_repair_chains"] = ableton_repair_chain_export(report)
    report["closed_loop_action_plan"] = closed_loop_action_plan(report)
    report["next_revision_plan"] = next_revision_plan(report)
    report["session_report"] = build_session_report(report)
    report["kenn_handoff"] = kenn_handoff(report)

    # Stage D — proactively explain the highest-severity Mix Review flags
    # using KENN's grounded answer pipeline, same best-effort treatment as
    # AutoMix parameters/dynamic EQ cuts in mix_delivery.py's
    # package_mixdown_delivery: never let a KENN/index problem block report
    # delivery, and keep allow_llm=False so this stays fast and deterministic.
    if "kenn_explanations" not in report:
        flags = report.get("flags")
        if isinstance(flags, list) and flags:
            try:
                from audio_analysis.integration.kenn_handoff import annotate_flags_with_kenn

                kenn_explanations = annotate_flags_with_kenn(flags)
            except Exception:
                kenn_explanations = []
                import logging

                logging.getLogger(__name__).warning(
                    "KENN flag explanation annotation failed; delivering report without it",
                    exc_info=True,
                )
            if kenn_explanations:
                report["kenn_explanations"] = kenn_explanations

    return report


def validate_wav_upload(file_bytes: bytes, filename: str, *, label: str = "File") -> dict:
    return scanner_validate_audio_upload(
        file_bytes,
        filename,
        label=label,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        audio_suffixes=DECODABLE_SUFFIXES,
    )


def discover_audio_paths(root: Path, *, recursive: bool = True) -> list[Path]:
    """Return known audio-like files below a file or directory path."""
    return scanner_discover_audio_paths(
        root, recursive=recursive, audio_suffixes=DECODABLE_SUFFIXES
    )


def scan_audio_files(
    root: Path,
    *,
    recursive: bool = True,
    mix_goal: str = DEFAULT_MIX_GOAL,
    reference_path: Path | None = None,
) -> dict:
    """Analyze every supported WAV file and report unsupported audio files explicitly."""
    return scanner_scan_audio_files(
        root,
        recursive=recursive,
        mix_goal=mix_goal,
        reference_path=reference_path,
        context=ScanContext(
            discover_paths=discover_audio_paths,
            decode_audio_file=decode_audio_file,
            analyze_wav=analyze_wav,
            compare_metrics=compare_metrics,
            comparison_advice=comparison_advice,
            reference_coaching=reference_coaching,
            report_summary=report_summary,
            priority_actions=priority_actions,
            revision_lesson=revision_lesson,
            refresh_report_interpretation=refresh_report_interpretation,
            refresh_closed_loop_payloads=refresh_closed_loop_payloads,
            kenn_handoff=kenn_handoff,
            mix_goal_info=mix_goal_info,
        ),
    )


def scan_audio_benchmark(payload: dict) -> dict:
    """Summarize scan throughput from a scan_audio_files payload."""
    return scanner_scan_audio_benchmark(payload, metric_float=metric_float, percentile=percentile)


def batch_qa_summary(scan_payload: dict) -> dict:
    """Rank scanned audio items by risk to identify catalogue-quality problems."""
    return closed_loop_batch_qa_summary(scan_payload)


def batch_music_analysis(scan_payload: dict) -> dict:
    """Run music-theory analysis (key, chord progression) over a scan result."""
    return music_analysis_batch_music_analysis(scan_payload)


def batch_music_analysis_csv(batch_payload: dict) -> str:
    """Export batch music analysis as CSV text."""
    return music_analysis_batch_music_analysis_csv(batch_payload)


def _review_workflow_context() -> ReviewWorkflowContext:
    return ReviewWorkflowContext(
        analyze_wav=analyze_wav,
        compare_metrics=compare_metrics,
        comparison_advice=comparison_advice,
        connect=connect,
        find_similar_reviews=find_similar_reviews,
        generate_mix_critique=generate_mix_critique,
        generate_mix_review_critique=generate_mix_review_critique,
        classify_mix_style=classify_mix_style,
        get_song_project=get_song_project,
        set_project_reference_track=set_project_reference_track,
        generate_prose_summary=generate_prose_summary,
        init_reviews_table=init_reviews_table,
        latest_review_for_title=latest_review_for_title,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        now=now,
        priority_actions=priority_actions,
        reference_by_id=reference_by_id,
        reference_envelope_for_genre=reference_envelope_for_genre,
        reference_coaching=reference_coaching,
        refresh_closed_loop_payloads=refresh_closed_loop_payloads,
        refresh_report_interpretation=refresh_report_interpretation,
        report_root=REPORT_ROOT,
        report_summary=report_summary,
        revision_agent_plan=revision_agent_plan,
        revision_coaching=revision_coaching,
        revision_impact_summary=revision_impact_summary,
        revision_lesson=revision_lesson,
        upload_root=UPLOAD_ROOT,
        validate_wav_upload=validate_wav_upload,
        version_advice=version_advice,
        artifact_registry=_review_artifact_registry(),
    )


def mix_review_status(review_id: str) -> dict:
    result = workflow_mix_review_status(
        review_id,
        init_reviews_table=init_reviews_table,
        connect=connect,
        read_report=read_report,
    )
    if result.get("ok"):
        report = result.get("review") or result.get("report") or {}
        if report:
            cache_report_summary(report)
        registry = _review_artifact_registry()
        if registry is not None:
            artifacts = {
                key: registry.public(item)
                for key, item in (
                    ("source", registry.by_external_key(f"mix-review-source:{review_id}")),
                    ("report", registry.by_external_key(f"mix-review-report:{review_id}")),
                )
                if item is not None
            }
            if artifacts:
                result["artifacts"] = artifacts
                if isinstance(result.get("review"), dict):
                    result["review"]["artifacts"] = artifacts
    return result


def _background_analyze(
    review_id: str,
    file_bytes: bytes,
    safe_name: str,
    mix_goal: str,
    reference_bytes: bytes | None,
    reference_safe_name: str,
    saved_reference: dict | None,
    review_title: str,
    version_label: str,
    stored_name: str,
    report_name: str,
    file_size: int,
    project_id: str = "",
    source_artifact_id: str = "",
    phon_level: float = 60.0,
) -> None:
    return workflow_background_analyze(
        review_id,
        file_bytes,
        safe_name,
        mix_goal,
        reference_bytes,
        reference_safe_name,
        saved_reference,
        review_title,
        version_label,
        stored_name,
        report_name,
        file_size,
        project_id,
        source_artifact_id,
        context=_review_workflow_context(),
        phon_level=phon_level,
    )


def save_review(
    *,
    file_bytes: bytes,
    filename: str,
    title: str = "",
    version_label: str = "",
    mix_goal: str = DEFAULT_MIX_GOAL,
    reference_bytes: bytes | None = None,
    reference_filename: str = "",
    reference_id: str = "",
    project_id: str = "",
    background: bool = False,
    phon_level: float = 60.0,
    stems: list[dict] | None = None,
    pre_master_bytes: bytes | None = None,
    correlation_id: str = "",
) -> dict:
    """Analyze and persist a mix review.

    ``stems`` (Stage 10, optional) — when at least two stems are supplied as
    ``{"name": str, "file_bytes": bytes}`` dicts, the report gains
    ``stem_masking`` (frequency-masking detection between stems) and
    ``stem_solo`` (per-stem spectral dominance/low-end comparison). Omitted
    entirely (no behavior change) when not supplied.

    ``pre_master_bytes`` (Stage 10, optional) — a pre-limiter/pre-master
    render of the *same* material as ``file_bytes``. When supplied, the
    report gains ``transient_preservation`` comparing attack sharpness
    before vs. after mastering. Meaningless (and not attempted) without a
    genuine "before" render of the same audio, so it's opt-in.
    """
    return workflow_save_review(
        file_bytes=file_bytes,
        filename=filename,
        title=title,
        version_label=version_label,
        mix_goal=mix_goal,
        reference_bytes=reference_bytes,
        reference_filename=reference_filename,
        reference_id=reference_id,
        project_id=project_id,
        background=background,
        context=_review_workflow_context(),
        phon_level=phon_level,
        stems=stems,
        pre_master_bytes=pre_master_bytes,
        correlation_id=correlation_id,
    )


def handle_multipart_review(
    content_type: str, body: bytes, *, correlation_id: str = "", project_id_override: str = ""
) -> dict:
    return workflow_handle_multipart_review(
        content_type,
        body,
        parse_multipart_form=parse_multipart_form,
        save_review=save_review,
        correlation_id=correlation_id,
        project_id_override=project_id_override,
    )


def handle_multipart_music_analysis(content_type: str, body: bytes) -> dict:
    return workflow_handle_multipart_music_analysis(
        content_type,
        body,
        parse_multipart_form=parse_multipart_form,
        default_mix_goal=DEFAULT_MIX_GOAL,
        validate_wav_upload=validate_wav_upload,
        analyze_wav=analyze_wav,
        music_analysis_from_report=music_analysis_from_report,
    )


def handle_multipart_waveform(content_type: str, body: bytes) -> dict:
    """Downsampled waveform peaks for an uploaded audio file -- the
    lightweight shape a frontend waveform view needs (a few hundred to a
    few thousand (min, max) points), not full-resolution decoded samples.
    See analysis_core/waveform.py for why raw samples are never returned."""
    from audio_analysis.analysis_core.waveform import DEFAULT_POINTS, compute_waveform_peaks

    fields = parse_multipart_form(content_type, body)
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return {"ok": False, "error": "Missing file field."}
    filename = str(fields.get("file__filename", "audio.wav"))
    validation = validate_wav_upload(bytes(file_bytes), filename, label="Audio file")
    if not validation.get("ok"):
        return validation
    try:
        target_points = int(fields.get("points", DEFAULT_POINTS) or DEFAULT_POINTS)
    except (TypeError, ValueError):
        target_points = DEFAULT_POINTS
    try:
        # as_arrays=True: compute_waveform_peaks immediately np.asarray()s
        # the returned samples anyway -- skip the redundant list<->array
        # round trip (measured ~4x faster on a real 205s track).
        decoded = read_wav_mono(bytes(file_bytes), max_samples=0, as_arrays=True)
    except Exception as exc:
        return {"ok": False, "error": f"Could not decode audio: {exc}"}
    peaks = compute_waveform_peaks(decoded["samples"], decoded["sample_rate"], target_points=target_points)
    return {"ok": True, **peaks}


def handle_multipart_podcast_check(content_type: str, body: bytes) -> dict:
    """Podcast/spoken-word readiness check for an uploaded episode file.

    Advice-only (no DSP): runs the same measurement pass as Mix Review, then
    scores it against podcast delivery norms (Apple/Spotify/mono/YouTube) via
    audio_analysis.podcast. Mirrors the CLI path in scripts/podcast_check.py
    so a browser upload gets the same report a person running the script
    would.
    """
    from audio_analysis.podcast import analyze_podcast, render_podcast_report_html

    fields = parse_multipart_form(content_type, body)
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return {"ok": False, "error": "Missing file field."}
    filename = str(fields.get("file__filename", "episode.wav"))
    validation = validate_wav_upload(bytes(file_bytes), filename, label="Audio file")
    if not validation.get("ok"):
        return validation
    target = str(fields.get("target", "apple") or "apple")
    try:
        # light=True skips chord/key, transient/groove, section analysis,
        # THD/resonance/ISP, and the whole report-interpretation tail --
        # none of which analyze_podcast reads. include_bands=True since it
        # does read metrics["bands"]. Measured ~19-23% wall-time reduction
        # on real tracks; verified output-identical on every field this
        # caller uses in tests/audio_analysis/test_analyze_wav_light_mode.py.
        result = analyze_wav(bytes(file_bytes), str(validation["safe_name"]), light=True, include_bands=True)
    except Exception as exc:
        return {"ok": False, "error": f"Could not analyze audio: {exc}"}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else result
    report = analyze_podcast(metrics, target=target, explain=True)
    title = Path(filename).stem
    html_report = render_podcast_report_html(report, title=title)
    return {"ok": True, "report": report, "html_report": html_report, "title": title}


def handle_multipart_delivery_conform(content_type: str, body: bytes) -> dict:
    """Delivery-spec conformance check for an uploaded master.

    Advice-only (no DSP): runs the same measurement pass as Mix Review, then
    checks it against a named delivery platform's published loudness/true-
    peak spec via audio_analysis.mixdown.delivery_conform. Same shape as
    handle_multipart_podcast_check, for a finished master rather than a
    spoken-word episode.
    """
    from audio_analysis.mixdown.delivery_conform import check_delivery_conformance
    from audio_analysis.mixdown.delivery_report import render_delivery_report_html

    fields = parse_multipart_form(content_type, body)
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return {"ok": False, "error": "Missing file field."}
    filename = str(fields.get("file__filename", "master.wav"))
    validation = validate_wav_upload(bytes(file_bytes), filename, label="Audio file")
    if not validation.get("ok"):
        return validation
    target = str(fields.get("target", "spotify") or "spotify")
    try:
        # light=True, include_bands=False: check_delivery_conformance never
        # reads metrics["bands"] at all (see module docstring), so this also
        # skips the high-fidelity spectral re-read podcast-check still needs.
        # Same output-preservation guarantee/tests as podcast-check's call.
        result = analyze_wav(bytes(file_bytes), str(validation["safe_name"]), light=True, include_bands=False)
    except Exception as exc:
        return {"ok": False, "error": f"Could not analyze audio: {exc}"}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else result
    report = check_delivery_conformance(metrics, target=target)
    html_report = render_delivery_report_html(report, title=Path(filename).stem)
    return {"ok": True, "report": report, "html_report": html_report}


def list_reviews(limit: int = 50, *, use_cache: bool = True) -> list[dict]:
    return store_list_reviews(
        limit,
        report_root=REPORT_ROOT,
        init_func=init_reviews_table,
        connect_func=connect,
        use_cache=use_cache,
    )


def _numeric_delta(new_value: object, old_value: object) -> float | None:
    return store_numeric_delta(new_value, old_value)


def review_history(limit: int = 20, *, title: str = "") -> list[dict]:
    """Return compact review history for product UIs and chat context."""
    return store_review_history(list_reviews, limit, title=title)


def track_timeline(title: str, *, limit: int = 80) -> dict:
    return comparison_track_timeline(
        title,
        limit=limit,
        normalize_title=normalize_title,
        list_reviews=list_reviews,
        numeric_delta=_numeric_delta,
    )


# ---------------------------------------------------------------------------
# ML modules — anomaly detection + quality prediction
# (delegated to ml_api.py)
# ---------------------------------------------------------------------------

from audio_analysis.ml_api import (  # noqa: E402, F401 — re-exported as public API
    detect_anomalies,
    anomaly_report_for_report,
    predict_quality,
    quality_predictor_status,
    scoring_feature_importance,
)


def revision_narrative_for_report(review_id: str) -> dict:
    """Build a revision narrative for the given review.

    Compares the review against its previous version (same title, earlier date)
    and returns a compact, agent-friendly diff.

    Returns:
        Dict with ok, verdict, narrative (str), deltas, cleared, new_flags,
        action_summary, narrative_line.
    """
    from audio_analysis.mix_review.revision_narrative import build_revision_narrative

    report = review_by_id(review_id)
    if not report:
        return {"ok": False, "error": f"Review not found: {review_id}"}

    # Find previous version of the same track
    title = str(report.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "Review has no title — cannot compare."}
    previous = latest_review_for_title(title)
    previous_report = None
    if previous and str(previous.get("id", "")) != review_id:
        previous_report = previous

    narrative = build_revision_narrative(
        report,
        previous_report,
        version_comparison=report.get("version_comparison"),
        revision_impact=report.get("revision_impact"),
    )
    return {"ok": True, **narrative}


def report_html(review_id: str) -> str | None:
    report = review_by_id(review_id)
    if not report:
        return None
    return render_report_html(report)


def report_json_bytes(review_id: str) -> bytes | None:
    return store_report_json_bytes(review_by_id, review_id)


def repair_chains_json_bytes(review_id: str) -> bytes | None:
    return store_repair_chains_json_bytes(review_by_id, review_id)


def review_audio_path(review_id: str, type: str = "mix") -> Path | None:
    return store_review_audio_path(review_by_id, review_id, type, upload_root=UPLOAD_ROOT)


def reference_audio_path(reference_id: str) -> Path | None:
    ref = reference_by_id(reference_id)
    if not ref:
        return None
    stored_name = ref.get("stored_name")
    if stored_name:
        return REFERENCE_ROOT / stored_name
    return None


def generate_correction_rack(review_id: str) -> bytes | None:
    return ableton_generate_correction_rack(
        review_id, review_lookup=review_by_id, report_reader=read_report
    )


def analyze_stems_masking(stems: list[dict]) -> dict:
    return stem_analyze_stems_masking(
        stems, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands
    )


def handle_stems_upload(content_type: str, body: bytes) -> dict:
    return stem_handle_stems_upload(content_type, body, analyze_stems_masking=analyze_stems_masking)


def cache_report_summary(report: dict) -> None:
    """Populate the SQLite summary cache for a single report dict.

    Call this after saving or modifying a report so the dashboard
    list can return cached summaries instead of re-reading the JSON file.
    """
    store_cache_report_summary(report, connect)


# --- File cleanup API (exposed for agents) ---

from audio_analysis.utils.file_cleanup_api import (  # noqa: E402, F401 — re-exported
    set_auto_delete_uploads as file_cleanup_set_auto_delete_uploads,
    cleanup_audiogen_exports as file_cleanup_audiogen_exports,
    cleanup_all_uploads as file_cleanup_all_uploads,
    cleanup_orphaned_uploads as file_cleanup_orphaned_uploads,
    cleanup_old_uploads as file_cleanup_old_uploads,
    cleanup_single_review,
    get_storage_stats as file_get_storage_stats,
    CLEANUP_POLICY_AFTER_ANALYSIS,
    CLEANUP_POLICY_AGE_BASED,
)


def set_auto_delete_uploads(enabled: bool) -> None:
    """Toggle automatic deletion of uploaded audio after analysis.

    When enabled (default True), the original upload is deleted as soon as
    analysis completes and the report JSON is saved. The report retains all
    extracted metrics; the audio is not needed again.

    Agents can use this if they need to temporarily keep uploads, for
    example during batch ingestion where re-analysis may be beneficial.
    """
    file_cleanup_set_auto_delete_uploads(enabled)


def cleanup_audiogen_exports(dry_run: bool = True) -> dict:
    """Delete AudioGen export files (WAVs + JSON reports) from `exports/web/`.

    AudioGen writes render outputs to `LLM_AudioGen/exports/web/` during
    full-song rendering. These files are copied to Portfolio/audio after
    generation, so the exports become stale duplicates. This function
    cleans them up.

    Args:
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, deleted (count), total_bytes_freed, note.
    """
    return file_cleanup_audiogen_exports(
        audiogen_root=AUDIOGEN_ROOT,
        dry_run=dry_run,
    )


def cleanup_all_audio_exports(dry_run: bool = True) -> dict:
    """Clean up ALL temporary audio files — both mix review uploads and AudioGen exports.

    This is the one-stop shop for agents to reclaim disk space:
    - Deletes uploaded mix audio (the report JSONs are kept)
    - Deletes AudioGen export files (the Portfolio copies are kept)
    - Does NOT touch Portfolio/audio curated files
    - Does NOT touch report JSONs in reports/

    Args:
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, mix_uploads, audiogen_exports, total_bytes_freed.
    """
    mix_result = file_cleanup_all_uploads(
        upload_root=UPLOAD_ROOT,
        connect_func=connect,
        dry_run=dry_run,
    )
    audiogen_result = file_cleanup_audiogen_exports(
        audiogen_root=AUDIOGEN_ROOT,
        dry_run=dry_run,
    )
    mix_deleted = mix_result.get("deleted_mix", 0) + mix_result.get("deleted_reference", 0)
    return {
        "ok": mix_result.get("ok") and audiogen_result.get("ok"),
        "dry_run": dry_run,
        "mix_uploads": {"deleted": mix_deleted, **mix_result},
        "audiogen_exports": audiogen_result,
        "total_deleted": mix_deleted + audiogen_result.get("deleted", 0),
        "note": "Mix review reports and Portfolio audio were preserved.",
    }


def cleanup_orphaned_uploads(dry_run: bool = True) -> dict:
    """Remove uploaded files that have no matching database record.

    This gets rid of the accumulated 9-byte corrupt files from failed
    uploads. In dry-run mode (default), it reports what would be deleted
    without actually removing anything.

    Args:
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, dry_run, deleted (count), errors.
    """
    return file_cleanup_orphaned_uploads(
        upload_root=UPLOAD_ROOT,
        connect_func=connect,
        dry_run=dry_run,
    )


def cleanup_old_uploads(days: int = 30, dry_run: bool = True) -> dict:
    """Delete uploaded audio files older than the specified number of days.

    This is useful for a one-time manual sweep or scheduled maintenance.
    The report JSONs are NOT deleted — only the original audio uploads.

    Args:
        days: Delete uploads older than this many days.
        dry_run: If True, only report what would be deleted.

    Returns:
        Summary dict with counts of deleted files.
    """
    return file_cleanup_old_uploads(
        upload_root=UPLOAD_ROOT,
        connect_func=connect,
        days=days,
        dry_run=dry_run,
    )


def cleanup_all_uploads(dry_run: bool = True) -> dict:
    """Delete ALL uploaded audio files across every review.

    WARNING: This removes the original audio for all reviews. The report
    JSONs (metrics, flags, analysis) are preserved. Use this when you
    want to reclaim disk space after confirming all analyses are complete.

    Args:
        dry_run: If True, only report what would be deleted.

    Returns:
        Summary dict with counts of deleted files.
    """
    return file_cleanup_all_uploads(
        upload_root=UPLOAD_ROOT,
        connect_func=connect,
        dry_run=dry_run,
    )


def get_storage_stats() -> dict:
    """Get storage usage statistics for all audio-related directories.

    Useful for agents to monitor disk usage and decide when cleanup is needed.

    Returns:
        Dict with per-directory file counts and sizes.
    """
    base = file_get_storage_stats(
        upload_root=UPLOAD_ROOT,
        report_root=REPORT_ROOT,
        reference_root=REFERENCE_ROOT,
    )
    # Add AudioGen exports

    export_dir = AUDIOGEN_ROOT / "exports" / "web"
    base["audiogen_exports"] = {"path": str(export_dir), "files": 0, "size_bytes": 0}
    if export_dir.exists():
        for f in export_dir.iterdir():
            if f.is_file():
                base["audiogen_exports"]["files"] += 1
                base["audiogen_exports"]["size_bytes"] += f.stat().st_size
    portfolio = PORTFOLIO_ROOT / "audio"
    base["portfolio_audio"] = {"path": str(portfolio), "files": 0, "size_bytes": 0}
    if portfolio.exists():
        for f in portfolio.iterdir():
            if f.is_file():
                base["portfolio_audio"]["files"] += 1
                base["portfolio_audio"]["size_bytes"] += f.stat().st_size
    return base


def delete_review(review_id: str, dry_run: bool = True) -> dict:
    """Delete all files associated with a single review.

    Removes uploaded audio, reference files, and optionally the report JSON.
    Use this from the agent when a review needs to be fully purged.

    Args:
        review_id: The review to delete
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with ok, deleted_upload, deleted_report, errors.
    """
    return cleanup_single_review(
        review_id,
        upload_root=UPLOAD_ROOT,
        report_root=REPORT_ROOT,
        connect_func=connect,
        dry_run=dry_run,
    )
