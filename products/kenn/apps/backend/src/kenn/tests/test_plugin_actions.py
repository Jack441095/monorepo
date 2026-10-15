from __future__ import annotations

import math

import pytest

from kenn.plugin_actions import proposals_from_live_context


# A peak near full scale used to produce advice even when its RMS came from silence.
def _context(*, rms: object = -79.9, peak: object = -0.1) -> dict[str, object]:
    return {"rms_dbfs": rms, "peak_dbfs": peak}


@pytest.mark.parametrize("rms", [-100.0, -80.0])
def test_quiet_live_context_cannot_propose_from_peak(rms: float) -> None:
    assert proposals_from_live_context(_context(rms=rms)) == []


def test_active_finite_context_keeps_existing_peak_proposal() -> None:
    proposals = proposals_from_live_context(_context())

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["schema"] == "kenn.action_proposal.v1"
    assert proposal["target"] == "kenn_mix_assistant"
    assert proposal["parameter"] == "target_lufs"
    assert proposal["before"] == -14.0
    assert proposal["after"] == -15.0
    assert proposal["requires_confirmation"] is True
    assert proposal["undo"]["value"] == -14.0


@pytest.mark.parametrize("rms", [None, True, False, math.nan, math.inf, -math.inf, 10**400])
def test_missing_or_invalid_rms_cannot_authorize_proposal(rms: object) -> None:
    context = _context(rms=rms)
    if rms is None:
        context.pop("rms_dbfs")

    assert proposals_from_live_context(context) == []


@pytest.mark.parametrize("peak", [None, True, math.nan, math.inf, -math.inf, 10**400])
def test_missing_or_invalid_peak_cannot_authorize_proposal(peak: object) -> None:
    context = _context(peak=peak)
    if peak is None:
        context.pop("peak_dbfs")

    assert proposals_from_live_context(context) == []


@pytest.mark.parametrize(("rms", "expected"), [(-80.0, False), (-79.9, True)])
def test_ingested_snapshot_proposes_only_above_live_activity_floor(rms: float, expected: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    from kenn import plugin_handoff

    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    payload = {
        "schema": "kenn.plugin_handoff.v1",
        "audio_feature_schema": "audio_feature_frame.v1",
        "kind": "mix_review_snapshot",
        "assistant_mode": "suggest",
        "peak_dbfs": -0.1,
        "rms_dbfs": rms,
        "stereo_correlation": 0.7,
        "stereo_width": 0.2,
        "sample_rate": 48000.0,
        "analysed_samples": 48000,
        "audio_age_seconds": 0.0,
        "plugin_state": {"assistant_mode": "suggest", "analysis_enabled": True},
    }
    result = plugin_handoff.ingest_live_context(payload, session_id="proposal-gate-test")

    assert result["ok"] is True
    assert bool(result["action_proposals"]) is expected
