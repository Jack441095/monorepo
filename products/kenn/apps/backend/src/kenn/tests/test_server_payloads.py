"""Uploaded chat history keeps explicit intent when signal evidence is unqualified."""

from copy import deepcopy

import pytest

from kenn import server_payloads
from kenn.core.evidence import TRANSIENT_SIGNAL_LIMITATION, UPLOADED_SIGNAL_LIMITATION


def _handoff():
    return {
        "schema": "kenn_mix_review_handoff.v1",
        "title": "Producer's mix",
        "mix_goal_label": "Warm club mix",
        "session_goal": "Keep the vocal forward",
        "context": "Cached signal summary",
        "context_lines": ["Cached signal context", "Cached signal advice"],
        "metrics": {"rms_dbfs": -18.0, "peak_dbfs": -1.0},
        "flags": [{"severity": "warn", "label": "Peak", "detail": "Cached peak warning"}],
        "priority_actions": [{"rank": 1, "action": "Cached gain reduction"}],
        "judgment": {"technical_rating": "Excellent"},
        "technical_metrics": {"integrated_lufs": -12.0},
        "section_highlights": {"chorus": "Cached section imbalance"},
        "ableton_repair_templates": [{"device_chain": "EQ Eight", "move": "Cached EQ repair"}],
        "revision_steps": [{"action": "Cached revision move"}],
        "reference": {"title": "Cached reference analysis"},
        "reference_comparison": {"dynamics": {"mix": {"rms_dbfs": -18.0}, "reference": {"rms_dbfs": -20.0}},"eq_bands": [{"freq": 100.0, "gain": -2.0}]},
        "mix_style": {"genre": {"genre_name": "House", "confidence": 0.9}},
        "leave_alone": ["Cached stereo judgment"],
        "previous_version": {"title": "Cached previous analysis"},
        "version_comparison": {"summary": "Cached improvement"},
        "version_advice": {"summary": "Cached revision advice"},
        "revision_impact": {"summary": "Cached impact"},
        "next_revision_plan": {"focus": "Cached plan", "steps": [{"action": "Cached step"}]},
    }


def _transient_summary():
    return {
        "score": 0.0,
        "matched_event_count": 1,
        "profile": "uncompressed",
        "activity": {
            "schema": "kenn.transient_preservation.activity.v1",
            "pre_rms_dbfs": -18.0,
            "post_rms_dbfs": -18.5,
        },
    }


@pytest.mark.parametrize("metrics", [
    None, {}, [], {"rms_dbfs": None}, {"rms_dbfs": "-18"},
    {"rms_dbfs": True}, {"rms_dbfs": False}, {"rms_dbfs": float("nan")},
    {"rms_dbfs": float("inf")}, {"rms_dbfs": float("-inf")},
    {"rms_dbfs": 10**400}, {"rms_dbfs": -100.0}, {"rms_dbfs": -60.0},
])
def test_quiet_uploaded_handoff_rebuilds_history_without_cached_signal_claims(metrics, monkeypatch):
    # Cached prose and nested repairs used to bypass the typed measurement gate.
    context = _handoff()
    context["metrics"] = metrics
    before = deepcopy(context)
    monkeypatch.setattr(server_payloads, "_retrieve_approved_genre_evidence", lambda: pytest.fail("Quiet genre was evaluated"))

    turn = server_payloads.mix_review_context_turn(context)

    assert turn == {"role": "user", "content": "\n".join([
        "Mix Review Lab context for Producer's mix.",
        UPLOADED_SIGNAL_LIMITATION,
        "Selected mix target: Warm club mix",
        "Session goal: Keep the vocal forward",
    ])}
    assert context == before


def test_quiet_uploaded_handoff_bounds_identity_and_preserves_nested_explicit_goals():
    context = {
        "schema": "kenn_mix_review_handoff.v1",
        "title": "T" * 200,
        "session_context": {"mix_goal_label": "M" * 200, "session_goal": "G" * 400},
        "context": "Cached summary must not appear",
    }
    turn = server_payloads.mix_review_context_turn(context)
    assert turn["content"].splitlines() == [
        f"Mix Review Lab context for {'T' * 120}.",
        UPLOADED_SIGNAL_LIMITATION,
        f"Selected mix target: {'M' * 160}",
        f"Session goal: {'G' * 300}",
    ]


@pytest.mark.parametrize("rms_dbfs", [-59.9, -18.0])
def test_active_uploaded_handoff_retains_structured_narrative_and_reference_moves(rms_dbfs, monkeypatch):
    context = _handoff()
    context["metrics"]["rms_dbfs"] = rms_dbfs
    before = deepcopy(context)
    monkeypatch.setattr(server_payloads, "_retrieve_approved_genre_evidence", lambda: "genre-source@index:fixture")

    content = server_payloads.mix_review_context_turn(context)["content"]

    for marker in (
        "Cached signal context", "Cached signal advice", "Selected mix target: Warm club mix",
        "Session goal: Keep the vocal forward", f"rms dbfs={rms_dbfs}", "Cached peak warning",
        "Cached gain reduction", "Excellent", "integrated_lufs", "Cached section imbalance",
        "Cached EQ repair", "Cached revision move", "Cached reference analysis",
        "Reduce 2.0 dB around 100 Hz", "House-leaning", "Cached stereo judgment",
        "Cached previous analysis", "Cached improvement", "Cached revision advice",
        "Cached impact", "Cached plan", "Cached step",
    ):
        assert marker in content
    assert UPLOADED_SIGNAL_LIMITATION not in content
    assert context == before


def test_active_uploaded_handoff_keeps_freeform_summary_when_context_lines_are_absent():
    context = _handoff()
    del context["context_lines"]
    assert "Cached signal summary" in server_payloads.mix_review_context_turn(context)["content"]


@pytest.mark.parametrize("side", ["mix", "reference"])
@pytest.mark.parametrize("rms", [None, True, float("nan"), -60.0, -80.0])
def test_active_mix_with_unqualified_comparison_keeps_only_measured_own_history(side, rms):
    # Cached whole-review prose may include reference advice even when the own-source metrics qualify.
    context = _handoff()
    context["reference_comparison"]["dynamics"][side]["rms_dbfs"] = rms
    before = deepcopy(context)
    content = server_payloads.mix_review_context_turn(context)["content"]
    assert "Mix and reference RMS" in content
    assert '"rms_dbfs": -18.0' in content
    assert "Warm club mix" in content and "Keep the vocal forward" in content
    assert "Cached" not in content
    assert "Excellent" not in content
    assert context == before


@pytest.mark.parametrize("mutate", [
    lambda value: value.update(activity={"schema": "wrong", "pre_rms_dbfs": -18.0, "post_rms_dbfs": -18.0}),
    lambda value: value["activity"].update(pre_rms_dbfs=-60.0),
    lambda value: value["activity"].update(post_rms_dbfs=float("nan")),
    lambda value: value.update(matched_event_count=0),
    lambda value: value.update(score=1.1),
    lambda value: value.update(profile="x" * 161),
])
def test_unqualified_transient_summary_rebuilds_cached_handoff_but_keeps_qualified_reference(mutate):
    context = _handoff()
    summary = _transient_summary()
    mutate(summary)
    summary["cached_claim"] = "must never be serialized"
    context["analysis_evidence"] = {"transient_preservation": summary}
    context["metrics"]["transient_preservation_score"] = 0.0
    before = deepcopy(context)

    content = server_payloads.mix_review_context_turn(context)["content"]

    assert TRANSIENT_SIGNAL_LIMITATION in content
    assert "Structured metrics:" in content and '"rms_dbfs": -18.0' in content
    assert "Qualified reference comparison:" in content and '"reference": {"rms_dbfs": -20.0}' in content
    assert "transient_preservation_score" not in content
    assert "must never be serialized" not in content
    assert "Cached" not in content and "Excellent" not in content
    assert "Warm club mix" in content and "Keep the vocal forward" in content
    assert context == before


def test_qualified_zero_transient_score_and_exact_provenance_survive_history():
    context = _handoff()
    summary = _transient_summary()
    summary["cached_claim"] = "must be stripped"
    context["analysis_evidence"] = {"transient_preservation": summary}
    context["metrics"]["transient_preservation_score"] = 0.91
    context["metrics"]["matched_event_count"] = 99

    content = server_payloads.mix_review_context_turn(context)["content"]

    assert "Cached signal context" in content
    assert TRANSIENT_SIGNAL_LIMITATION not in content
    assert '"score": 0.0' in content
    assert '"pre_rms_dbfs": -18.0' in content and '"post_rms_dbfs": -18.5' in content
    assert "must be stripped" not in content
    assert "transient preservation score" not in content
    assert "matched event count=99" not in content


def test_legacy_transient_prose_without_activity_proof_is_rebuilt():
    context = _handoff()
    context["context_lines"] = ["Transient preservation score: 0.91; punch retained."]

    content = server_payloads.mix_review_context_turn(context)["content"]

    assert TRANSIENT_SIGNAL_LIMITATION in content
    assert "Transient preservation score" not in content
    assert "Cached peak warning" not in content
    assert '"rms_dbfs": -18.0' in content


def test_invalid_transient_section_type_is_rebuilt_without_cached_claims():
    context = _handoff()
    context["analysis_evidence"] = {"transient_preservation": "score 0.91, preserved"}

    content = server_payloads.mix_review_context_turn(context)["content"]

    assert TRANSIENT_SIGNAL_LIMITATION in content
    assert "score 0.91" not in content
    assert "Cached peak warning" not in content
    assert '"rms_dbfs": -18.0' in content


def _erb_summary():
    return {
        "stem_count": 2, "lowest_visibility": 0.0, "lowest_visibility_stem": "Bass",
        "activity": {
            "schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": -60.0,
            "frame_size_samples": 4096,
            "sources": [{"name": name, "sample_rate": 44100, "frame_count": 1,
                         "active_frame_count": 1} for name in ("Bass", "Kick")],
            "pairs": [{"stems": ["Bass", "Kick"], "simultaneously_active_frame_count": 1}],
        },
    }


@pytest.mark.parametrize("mutate", [
    lambda summary: summary.pop("activity"),
    lambda summary: summary["activity"].update(schema="legacy"),
    lambda summary: summary["activity"]["pairs"][0].update(simultaneously_active_frame_count=0),
    lambda summary: summary["activity"]["sources"][0].update(sample_rate=48000),
    lambda summary: summary.update(lowest_visibility_stem="Invented"),
    lambda summary: summary.update(lowest_visibility=float("nan")),
])
def test_unqualified_erb_rebuilds_cached_prose_and_preserves_other_measurements(mutate):
    # A real upload and valid transient/reference evidence cannot qualify synthetic stem profiles.
    context = _handoff()
    summary = _erb_summary()
    mutate(summary)
    context["analysis_evidence"] = {"stem_masking": summary, "transient_preservation": _transient_summary()}
    context["metrics"]["stem_masking_lowest_visibility"] = 0.99
    before = deepcopy(context)
    content = server_payloads.mix_review_context_turn(context)["content"]
    assert "jointly active real preview frames" in content
    assert "Cached" not in content
    assert '"rms_dbfs": -18.0' in content
    assert "Qualified reference comparison" in content
    assert "Qualified transient-preservation summary" in content
    assert "Qualified ERB" not in content
    assert "0.99" not in content
    assert context == before


@pytest.mark.parametrize("other_invalid", ["reference", "transient"])
def test_valid_zero_erb_survives_an_unqualified_optional_comparison(other_invalid):
    context = _handoff()
    summary = _erb_summary()
    summary["unexpected"] = "unvalidated prose"
    context["analysis_evidence"] = {"stem_masking": summary}
    if other_invalid == "reference":
        context["reference_comparison"] = {}
    else:
        context["analysis_evidence"]["transient_preservation"] = {}
    content = server_payloads.mix_review_context_turn(context)["content"]
    assert "Qualified ERB stem-masking summary" in content
    assert '"lowest_visibility": 0.0' in content
    assert "unvalidated prose" not in content
    assert "Cached" not in content


@pytest.mark.parametrize("legacy_location", ["context_lines", "metrics", "top_level"])
def test_legacy_erb_claims_cannot_bypass_missing_activity(legacy_location):
    context = _handoff()
    if legacy_location == "context_lines":
        context["context_lines"] = ["Stem masking says carve the bass"]
    elif legacy_location == "metrics":
        context["metrics"]["stem_masking_lowest_visibility"] = 0.97
    else:
        context["stem_masking_lowest_visibility"] = 0.97
    content = server_payloads.mix_review_context_turn(context)["content"]
    assert "jointly active real preview frames" in content
    assert "carve the bass" not in content
    assert "0.97" not in content


def test_actual_legacy_masking_critique_is_withheld_without_activity():
    # Historical critique prose carried neither a stem_masking key nor structured provenance.
    context = _handoff()
    context["context_lines"] = [
        "Among the supplied stems, 'Bass' has the lowest simultaneous-masking "
        "visibility (0.2) — it's the stem most likely getting buried by the others; "
        "consider carving space for it."
    ]
    content = server_payloads.mix_review_context_turn(context)["content"]
    assert "jointly active real preview frames" in content
    assert "getting buried" not in content
    assert "carving space" not in content
