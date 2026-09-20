"""Stage 11.3 — mastering handoff payload.

Bundles what a mastering engineer (or an automated mastering stage) needs
to pick up a finished AutoMix render: the printed stem processing manifest
("stem prints" -- what each stem was actually rendered with, since AutoMix
sums to a stereo bus and does not retain separate stem WAVs after
rendering), the measured loudness/peak specs, the delivered file paths
(from ``mix_delivery.package_mixdown_delivery``'s status dict), and
grounded notes on what AutoMix decided and why.

Every field is pulled from data the render/delivery pipeline already
produced -- ``mix_renderer.mix_and_render_stems``'s ``render_result``,
``mix_delivery.package_mixdown_delivery``'s ``delivery_status``, and
``kenn_handoff.annotate_mix_plan_with_kenn``'s cited explanations (Stage
9). Nothing here is a new measurement or invented field; this module is a
bundler, not a second analysis pass.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np

from ..integration.kenn_handoff import annotate_mix_plan_with_kenn
from ..mixdown.mix_validator import verify_render_output
from .mastering_targets import get_mastering_target, target_as_dict


def _stem_prints(plan: Any) -> list[dict]:
    """The processing manifest AutoMix actually printed into the mix, per stem.

    This is not raw stem audio (the renderer sums to a stereo bus and does
    not persist post-processing per-stem WAVs -- the DAW export in
    ``integration/daw_integration.py`` is the pipeline's mechanism for
    getting an editable per-stem session back to an engineer). What *is*
    available and real here is exactly what was printed onto each stem
    before summing: gain, EQ, compression, gate, saturation, reverb/delay
    send, panning, width, and low-end mono behaviour -- i.e. a mastering
    engineer's "what did the mix engineer already do to this element"
    reference.
    """
    prints = []
    for stem in getattr(plan, "stems", []) or []:
        prints.append({
            "stem_name": getattr(stem, "stem_name", ""),
            "instrument": getattr(stem, "instrument", ""),
            "gain_db": getattr(stem, "gain_db", 0.0),
            "pan": getattr(stem, "pan", 0.0),
            "eq_bands": getattr(stem, "eq_bands", []),
            "compressor": getattr(stem, "compressor", None),
            "gate": getattr(stem, "gate", None),
            "reverb_send": getattr(stem, "reverb_send", 0.0),
            "reverb_type": getattr(stem, "reverb_type", ""),
            "delay_send": getattr(stem, "delay_send", 0.0),
            "stereo_width": getattr(stem, "stereo_width", 1.0),
            "mono_below_hz": getattr(stem, "mono_below_hz", 0.0),
            "saturation_drive_db": getattr(stem, "saturation_drive_db", 0.0),
        })
    return prints


def _loudness_specs(render_result: dict) -> dict:
    """Measured loudness/peak specs from the same gate that guards delivery.

    Reuses ``mix_validator.verify_render_output`` -- the exact function the
    delivery pipeline runs before a mixdown is allowed to ship (Stage 7.5)
    -- rather than re-measuring loudness/true-peak a second, potentially
    divergent way.
    """
    plan = render_result.get("mix_plan")
    left = render_result.get("left")
    right = render_result.get("right")
    wav_bytes = render_result.get("mixdown_wav_bytes")
    sample_rate = int(render_result.get("sample_rate", 44100))
    if left is None or right is None or wav_bytes is None:
        return {"ok": False, "reasons": ["render_result missing left/right/mixdown_wav_bytes"], "metrics": {}}

    bus = getattr(plan, "bus", None) if plan is not None else None
    ceiling_db = getattr(bus, "limiter_ceiling_db", -1.0) if bus is not None else -1.0
    target_lufs = getattr(plan, "target_lufs", None) if plan is not None else None

    validation = verify_render_output(
        np.asarray(left, dtype=np.float64),
        np.asarray(right, dtype=np.float64),
        sample_rate,
        wav_bytes,
        target_lufs=target_lufs,
        measured_lufs=render_result.get("measured_lufs"),
        ceiling_db=ceiling_db,
    )
    metrics = validation.get("metrics", {})
    return {
        "target_lufs": target_lufs,
        "measured_integrated_lufs": render_result.get("measured_lufs"),
        "true_peak_dbtp": metrics.get("true_peak_dbtp"),
        "sample_peak_dbfs": metrics.get("peak_dbfs"),
        "crest_factor_db": metrics.get("crest_factor_db"),
        "phase_correlation": metrics.get("phase_correlation"),
        "pre_release_validation_ok": validation.get("ok"),
        "pre_release_validation_reasons": validation.get("reasons", []),
        "sample_rate": sample_rate,
        "limiter_ceiling_db": ceiling_db,
    }


def build_mastering_handoff(
    render_result: dict,
    *,
    delivery_status: dict | None = None,
    target_context: str = "streaming",
    mastering_notes: str = "",
    project_id: str = "",
    session_id: str = "",
    allow_llm: bool = False,
    max_kenn_items: int = 6,
) -> dict:
    """Build a mastering-handoff bundle for a finished AutoMix render.

    Parameters
    ----------
    render_result : dict
        Output of ``mix_renderer.mix_and_render_stems`` (or
        ``mix_validator.validate_and_correct_mix``) -- must contain
        ``mix_plan``, ``left``, ``right``, ``sample_rate``,
        ``mixdown_wav_bytes``, ``measured_lufs``.
    delivery_status : dict, optional
        Output of ``mix_delivery.package_mixdown_delivery`` -- if given,
        its real file paths/version are folded into the bundle's
        ``delivered_files`` section instead of leaving it empty.
    target_context : str
        One of ``mastering_targets``' contexts (``streaming``, ``cd``,
        ``vinyl``, ``broadcast``) -- the delivery context the mastering
        engineer is being asked to master toward.
    """
    plan = render_result.get("mix_plan")
    if plan is None:
        raise ValueError("render_result has no 'mix_plan' -- cannot build a mastering handoff.")

    target = get_mastering_target(target_context)

    kenn_explanations = annotate_mix_plan_with_kenn(
        plan, max_items=max_kenn_items, session_id=session_id, allow_llm=allow_llm
    )

    delivered_files: dict[str, Any] = {}
    if delivery_status:
        delivered_files = {
            "version": delivery_status.get("version"),
            "wav_path": delivery_status.get("wav_path"),
            "zip_path": delivery_status.get("zip_path"),
            "report_path": delivery_status.get("report_path"),
            "decisions_json_path": delivery_status.get("decisions_json_path"),
            "additional_format_paths": delivery_status.get("additional_format_paths", {}),
        }

    return {
        "project_id": project_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "genre": getattr(plan, "genre", ""),
        "mix_goal": getattr(plan, "mix_goal", ""),
        "stem_prints": _stem_prints(plan),
        "loudness_specs": _loudness_specs(render_result),
        "mastering_target": target_as_dict(target),
        "delivered_files": delivered_files,
        "decisions_log": list(getattr(plan, "decisions_log", []) or []),
        "kenn_rationale": [
            {
                "parameter": item["parameter"],
                "stem_name": item.get("stem_name", ""),
                "value": item.get("value"),
                "answer": item.get("answer", ""),
                "sources": item.get("sources", []),
            }
            for item in kenn_explanations
        ],
        "mastering_notes": mastering_notes,
    }
