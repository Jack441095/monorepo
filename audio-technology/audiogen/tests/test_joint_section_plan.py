"""Joint section plan scaffold (Phase C entry)."""

from __future__ import annotations

from composition.joint_section_plan import (
    apply_joint_plan_to_arrangement_curve,
    build_chorus_joint_plan,
)


def test_build_chorus_joint_plan_sparse_counter_for_anger():
    plan = build_chorus_joint_plan(emotion="anger", root_midi=60, bars=8)
    assert plan.hook_degrees
    assert float(plan.target_counter_mult) <= 0.08


def test_apply_joint_plan_writes_curve_targets():
    plan = build_chorus_joint_plan(emotion="grief", root_midi=60, bars=8)
    curve = {"counter_melody_enabled_mult": 0.0, "melody_total_notes_mult": 1.0}
    apply_joint_plan_to_arrangement_curve(curve, plan, strength=1.0)
    assert float(curve.get("counter_melody_enabled_mult", 0.0)) >= 0.24
    assert "joint_section_plan" in curve
