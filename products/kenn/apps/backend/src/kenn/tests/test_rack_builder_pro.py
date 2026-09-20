"""Comprehensive validation suite for KENN Pro Audio Effect Rack Synthesizer."""

import pytest
from kenn.core.rack_builder import (
    RACK_TEMPLATES,
    get_rack_template,
    list_available_racks,
    synthesize_rack_proposal,
)


def test_all_12_pro_racks_comprehensive():
    racks = list_available_racks()
    assert len(racks) == 12

    for rack in racks:
        rid = rack["id"]
        tmpl = get_rack_template(rid)
        assert tmpl is not None
        assert tmpl["id"] == rid
        assert tmpl["category"] in {"bass", "drums", "vocals", "spatial", "color", "master", "synth", "utility"}
        assert len(tmpl["chains"]) >= 1
        assert len(tmpl["macros"]) == 8
        assert len(tmpl["variations"]) >= 2

        # Check macro bounds and target bindings
        for macro in tmpl["macros"]:
            assert 0 <= macro["index"] <= 7
            assert isinstance(macro["name"], str) and len(macro["name"]) > 0
            assert macro["min"] <= macro["max"]
            assert macro["min"] <= macro["default"] <= macro["max"]
            assert "target_device" in macro and len(macro["target_device"]) > 0
            assert "target_parameter" in macro and len(macro["target_parameter"]) > 0

        # Check variation integrity
        for var in tmpl["variations"]:
            assert "name" in var and len(var["name"]) > 0
            assert len(var["macro_values"]) == 8
            for val in var["macro_values"]:
                assert 0.0 <= val <= 1.0


def test_synthesize_pro_racks_proposals():
    target_racks = [
        "neuro_reese_saturator",
        "ott_drum_smasher",
        "midside_stereo_widener",
        "clean_808_saturator",
        "dynamic_vocal_air",
        "lofi_tape_warmer",
        "parallel_glue_punch",
        "acid_resonance_lead",
        "sub_bass_monomaker",
    ]

    for rid in target_racks:
        res = synthesize_rack_proposal(rid, track_index=1, track_name="Test Track", session_id="pro_test")
        assert res["ok"] is True
        p = res["proposal"]
        assert p["rack_id"] == rid
        assert p["track_index"] == 1
        assert p["track_name"] == "Test Track"
        assert p["requires_confirmation"] is True
        assert p["confirmation_token"].startswith("rack_")
        assert len(p["steps"]) == 10
        assert len(p["chains"]) >= 1
        assert len(p["variations"]) >= 2

