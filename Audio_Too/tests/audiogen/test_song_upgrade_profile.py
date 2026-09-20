"""Song upgrade Phase A profile toggles."""

from __future__ import annotations

from audiogen_core.config import CONFIG
from audiogen_core.config import ConfigurationManager
from audiogen_core.song_upgrade_profile import (
    apply_legacy_composition_profile,
    apply_phase_a_profile,
    apply_phase_b_profile,
    apply_phase_c_profile,
)


def test_configuration_manager_defaults_to_phase_c():
    cm = ConfigurationManager()
    c = cm.composition
    assert bool(getattr(c, "song_upgrade_phase_c_enabled", False))
    assert bool(getattr(c, "joint_generation_enabled", False))
    assert bool(getattr(c, "joint_plan_lock_harmony", False))
    assert bool(getattr(c, "audit_aligned_rerank_enabled", False))


def test_apply_legacy_composition_profile_disables_upgrade():
    apply_legacy_composition_profile(CONFIG)
    c = CONFIG.composition
    assert not bool(getattr(c, "joint_generation_enabled", True))
    assert not bool(getattr(c, "audit_aligned_rerank_enabled", True))
    apply_phase_c_profile(CONFIG)


def test_apply_phase_a_profile_enables_audit_rerank_and_joint():
    apply_phase_a_profile(CONFIG)
    c = CONFIG.composition
    assert bool(getattr(c, "song_upgrade_phase_a_enabled", False))
    assert bool(getattr(c, "audit_aligned_rerank_enabled", False))
    assert bool(getattr(c, "joint_generation_enabled", False))
    assert bool(getattr(c, "offline_quality_render_enabled", False))
    assert int(getattr(c, "section_k_samples", 0) or 0) >= 3


def test_apply_phase_b_profile_sets_model_and_logging():
    apply_phase_b_profile(CONFIG, model_path="artifacts/song_rerank/rerank_v1.json")
    c = CONFIG.composition
    assert bool(getattr(c, "song_upgrade_phase_b_enabled", False))
    assert bool(getattr(c, "song_rerank_log_enabled", False))
    assert "rerank" in str(getattr(c, "song_rerank_model_path", ""))


def test_apply_phase_c_profile_enables_joint_lock():
    apply_phase_c_profile(CONFIG)
    c = CONFIG.composition
    assert bool(getattr(c, "joint_generation_enabled", False))
    assert bool(getattr(c, "joint_plan_lock_harmony", False))
    assert bool(getattr(c, "joint_plan_markov_conditioning_enabled", False))
    assert bool(getattr(c, "song_upgrade_phase_b_enabled", False))
