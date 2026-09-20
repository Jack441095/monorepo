from kenn.plugin_actions import proposals_from_live_context, validate_apply_request


def test_peak_headroom_proposal_is_reversible_and_confirmed():
    proposal = proposals_from_live_context({"peak_dbfs": -0.1}, target_lufs=-14.0)[0]
    assert proposal["requires_confirmation"] is True
    assert proposal["undo"]["value"] == -14.0
    assert proposal["evidence"] == ["Latest plug-in bus peak: -0.1 dBFS.", "This is a bus snapshot and does not identify the source of the peak."]
    assert "does not change audio" in proposal["expected_result"]
    assert "Undo restores" in proposal["verification"]
    assert validate_apply_request(proposal)["ok"] is True


def test_rejects_unconfirmed_or_unsafe_plugin_actions():
    assert validate_apply_request({})["ok"] is False
    assert validate_apply_request({"schema": "kenn.action_proposal.v1", "requires_confirmation": True, "target": "kenn_mix_assistant", "parameter": "target_lufs", "before": -14, "after": 10})["ok"] is False
