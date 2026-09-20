"""Unit tests for KENN Dynamic Audio Effect Rack Builder."""

import pytest
from kenn.core.rack_builder import (
    RACK_TEMPLATES,
    get_rack_template,
    list_available_racks,
    synthesize_rack_proposal,
)


def test_list_available_racks():
    racks = list_available_racks()
    assert len(racks) == 12
    ids = {r["id"] for r in racks}
    expected_ids = {
        "neuro_bass_rack",
        "nyc_drum_crush_rack",
        "vocal_presence_strip",
        "neuro_reese_saturator",
        "ott_drum_smasher",
        "midside_stereo_widener",
        "clean_808_saturator",
        "dynamic_vocal_air",
        "lofi_tape_warmer",
        "parallel_glue_punch",
        "acid_resonance_lead",
        "sub_bass_monomaker",
    }
    assert ids == expected_ids
    for r in racks:
        assert r["macro_count"] == 8
        assert r["chain_count"] >= 1
        assert r["variation_count"] >= 1


def test_get_rack_template():
    tmpl = get_rack_template("neuro_bass_rack")
    assert tmpl is not None
    assert tmpl["id"] == "neuro_bass_rack"
    assert len(tmpl["chains"]) == 3
    assert len(tmpl["macros"]) == 8
    assert tmpl["macros"][0]["name"] == "Sub/Mid Balance"


def test_synthesize_rack_proposal():
    res = synthesize_rack_proposal("nyc_drum_crush_rack", track_index=2, track_name="Drum Bus", session_id="test_sess")
    assert res["ok"] is True
    proposal = res["proposal"]
    assert proposal["track_index"] == 2
    assert proposal["track_name"] == "Drum Bus"
    assert proposal["requires_confirmation"] is True
    assert proposal["confirmation_token"].startswith("rack_")
    # Steps: 1 insert + 8 macros + 1 store variation = 10 steps
    assert proposal["step_count"] == 10
    assert len(proposal["steps"]) == 10
    assert proposal["steps"][0]["action"] == "insert_device"
    assert proposal["steps"][1]["action"] == "map_macro"
    assert proposal["steps"][-1]["action"] == "store_rack_variation"


def test_synthesize_invalid_rack():
    res = synthesize_rack_proposal("non_existent_rack", track_index=0)
    assert res["ok"] is False
    assert "Unknown rack template" in res["error"]

