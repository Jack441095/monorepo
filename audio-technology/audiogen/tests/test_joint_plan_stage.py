"""Phase C joint plan integration."""

from __future__ import annotations

from types import SimpleNamespace

from composition.joint_section_plan import (
    build_joint_plan_for_role,
    hook_blueprint_from_joint_plan,
)
from composition.section_planner.joint_plan_stage import integrate_joint_plan_at_harmony
from data.music_data import EMOTION_BY_NAME


class _Policy:
    form_mode = "default"

    def role_occurrence(self, _idx: int) -> int:
        return 1


class _Owner:
    arrangement_policy = _Policy()
    song_primary_emotion_name = "grief"


def test_chorus_joint_plan_yields_hook_blueprint():
    joint = build_joint_plan_for_role(
        emotion="grief",
        role="chorus",
        root_midi=60,
        bars=8,
    )
    assert joint is not None
    bp = hook_blueprint_from_joint_plan(joint)
    assert isinstance(bp, dict)
    assert len(bp.get("melody_steps_by_bar", [])) >= 1


def test_integrate_joint_plan_locks_harmony_when_enabled(monkeypatch):
    from audiogen_core.config import CONFIG

    monkeypatch.setattr(CONFIG.composition, "joint_generation_enabled", True)
    monkeypatch.setattr(CONFIG.composition, "joint_plan_lock_harmony", True)

    plan = SimpleNamespace(
        emotion=EMOTION_BY_NAME["grief"],
        root_note=60,
        bars=8,
        beats_per_bar=4.0,
        arrangement_curve={},
        joint_section_plan=None,
        joint_hook_blueprint=None,
    )
    curve, prog, meta = integrate_joint_plan_at_harmony(
        _Owner(),
        plan,
        {"melody_density_mult": 1.0},
        section_index=3,
        section_role="chorus",
        chord_progression=None,
    )
    assert bool(meta.get("enabled"))
    assert prog and len(prog) == 8
    assert isinstance(meta.get("hook_blueprint"), dict)
    assert "joint_section_plan" in curve


def test_verse_joint_plan_has_progression():
    joint = build_joint_plan_for_role(emotion="joy", role="verse", root_midi=60, bars=8)
    assert joint is not None
    assert len(joint.chord_symbols) == 8
    assert joint.target_counter_mult <= 0.12
