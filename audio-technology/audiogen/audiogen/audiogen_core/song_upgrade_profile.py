"""Offline / quality-first composition profiles for the song-upgrade roadmap."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_phase_a_profile(config: Any) -> None:
    """
    Phase A — align measurement and exploration for offline renders.

    - Audit-aligned whole-song rerank (same composite as batch note audit).
    - Joint section resampling (existing ``joint_generation_enabled`` path).
    - Stronger offline best-of-K / beam settings.
    """
    c = config.composition
    c.song_upgrade_phase_a_enabled = True
    c.audit_aligned_rerank_enabled = True
    c.audit_aligned_rerank_weight = float(max(0.35, min(0.75, float(getattr(c, "audit_aligned_rerank_weight", 0.55) or 0.55))))

    c.offline_quality_render_enabled = True
    c.whole_song_rerank_enabled = True
    c.joint_generation_enabled = True

    try:
        c.section_k_samples = int(max(int(getattr(c, "section_k_samples", 2) or 2), 3))
    except Exception:
        c.section_k_samples = 3
    try:
        c.section_pick_time_budget_s = float(max(float(getattr(c, "section_pick_time_budget_s", 0.75) or 0.75), 1.0))
    except Exception:
        c.section_pick_time_budget_s = 1.0

    try:
        scale = float(getattr(c, "offline_quality_k_scale", 1.6) or 1.6)
        c.offline_quality_k_scale = float(max(scale, 1.8))
    except Exception:
        c.offline_quality_k_scale = 1.8

    logger.info(
        "Applied song upgrade Phase A profile (audit_rerank=%s w=%.2f joint=%s section_k=%s)",
        bool(getattr(c, "audit_aligned_rerank_enabled", False)),
        float(getattr(c, "audit_aligned_rerank_weight", 0.0) or 0.0),
        bool(getattr(c, "joint_generation_enabled", False)),
        int(getattr(c, "section_k_samples", 0) or 0),
    )


def apply_phase_b_profile(
    config: Any,
    *,
    model_path: str = "artifacts/song_rerank/rerank_v1.json",
) -> None:
    """Phase B — learned reranker + candidate logging for retrain loops."""
    apply_phase_a_profile(config)
    c = config.composition
    c.song_upgrade_phase_b_enabled = True
    c.song_rerank_log_enabled = True
    if str(model_path or "").strip():
        c.song_rerank_model_path = str(model_path)
    logger.info(
        "Applied song upgrade Phase B profile (model_path=%s log=%s)",
        str(getattr(c, "song_rerank_model_path", "") or ""),
        bool(getattr(c, "song_rerank_log_enabled", False)),
    )


def apply_phase_c_profile(config: Any) -> None:
    """Phase C — shared joint section plan for harmony + melody lanes."""
    apply_phase_b_profile(config, model_path=str(getattr(config.composition, "song_rerank_model_path", "") or ""))
    c = config.composition
    c.song_upgrade_phase_c_enabled = True
    c.joint_generation_enabled = True
    c.joint_plan_lock_harmony = True
    c.joint_plan_markov_conditioning_enabled = True
    logger.info(
        "Applied song upgrade Phase C profile (joint_plan_lock_harmony=True markov_conditioning=True)"
    )


def apply_legacy_composition_profile(config: Any) -> None:
    """Pre song-upgrade baseline: no audit rerank, joint sampling, or learned rerank."""
    c = config.composition
    c.song_upgrade_phase_a_enabled = False
    c.song_upgrade_phase_b_enabled = False
    c.song_upgrade_phase_c_enabled = False
    c.audit_aligned_rerank_enabled = False
    c.whole_song_rerank_enabled = False
    c.offline_quality_render_enabled = False
    c.joint_generation_enabled = False
    c.joint_plan_lock_harmony = False
    c.joint_plan_markov_conditioning_enabled = False
    c.song_rerank_log_enabled = False
    c.song_rerank_model_path = ""
    try:
        c.section_k_samples = 2
    except Exception:
        pass
    logger.info("Applied legacy composition profile (song-upgrade disabled)")


def apply_default_song_upgrade_profile(config: Any) -> None:
    """Default runtime profile for full-song / audit pipelines (Phase C)."""
    apply_phase_c_profile(config)
