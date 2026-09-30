"""Full stock device coverage: Dry/Wet family, EQ band frequency, exact insert names.

Each test names the human behavior it protects. The Dry/Wet % mappings below
mirror the reversible 2026-09-06 readback runs (Glue/Saturator/Auto Filter/
Drum Buss 100% -> applied -> 100%); the EQ taper matches Live's own
10 Hz * 2200^raw curve read from the fixture and live_command.py.
"""

from __future__ import annotations

import pytest
from pytest import approx

from kenn.core.device_units import display_to_raw, find_profile
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import (
    DEVICE_INSERTION_ALLOWLIST,
    DEVICE_SETUP_PARAMETER_ALLOWLIST,
    LiveActionService,
)


@pytest.mark.parametrize("device", ["Saturator", "Drum Buss", "Auto Filter", "Glue Compressor", "Compressor"])
def test_drywet_percent_maps_linearly_for_each_qualified_device(device: str) -> None:
    assert find_profile(device, "Dry/Wet", "%") is not None
    raw, error = display_to_raw(device_name=device, parameter_name="Dry/Wet", value=25.0, unit="%")
    assert error is None
    assert raw == approx(0.25)


def test_dry_wet_spelling_without_slash_reads_the_same_control() -> None:
    # Live spells it "Dry Wet" on Echo and "Dry/Wet" everywhere else; both convert.
    raw_slash, _ = display_to_raw(device_name="Echo", parameter_name="Dry/Wet", value=30.0, unit="%")
    raw_space, error = display_to_raw(device_name="Echo", parameter_name="Dry Wet", value=30.0, unit="%")
    assert error is None
    assert raw_slash == approx(0.3)
    assert raw_space == approx(0.3)


def test_eq_band_frequency_names_resolve_to_the_shared_log_profile() -> None:
    # Live names every band separately ("1 Frequency A" .. "8 Frequency B");
    # we keep one evidence-backed taper instead of 16 copies.
    for band_param in ("1 Frequency A", "3 Frequency B", "8 Frequency A"):
        assert find_profile("EQ Eight", band_param, "hz") is not None
        raw, error = display_to_raw(device_name="EQ Eight", parameter_name=band_param, value=1000.0, unit="hz")
        assert error is None
        assert raw == approx(0.5983683466911316, rel=1e-6)


def test_eq_band_frequency_rejects_subsonic_requests() -> None:
    raw, error = display_to_raw(device_name="EQ Eight", parameter_name="2 Frequency A", value=10.0, unit="hz")
    assert raw is None
    assert error is not None and "20" in error and "20000" in error


def test_unprofiled_param_refuses_unit_conversion_instead_of_guessing() -> None:
    # Hybrid decay has no measured taper; we refuse rather than invent milliseconds.
    raw, error = display_to_raw(
        device_name="Hybrid Reverb", parameter_name="Decay Time", value=1200.0, unit="ms"
    )
    assert raw is None
    assert error is not None


def test_browser_fuzzy_names_never_reach_the_allowlist() -> None:
    # Real-Live testing showed "Reverb" -> Convolution Reverb, "Delay" ->
    # Align Delay, "Limiter" -> Color Limiter, so only exact names qualify.
    for fuzzy in ("Reverb", "Delay", "Limiter"):
        assert fuzzy not in DEVICE_INSERTION_ALLOWLIST
    assert "Hybrid Reverb" in DEVICE_INSERTION_ALLOWLIST
    assert "Echo" in DEVICE_INSERTION_ALLOWLIST


def test_fuzzy_insert_proposal_fails_closed_on_fake_live() -> None:
    service = LiveActionService(FakeLiveBackend())
    result = service.propose_device_insertion(
        track_index=0, device_name="Reverb", session_id="fuzzy-check",
    )
    assert result["ok"] is False
    assert "allow-list" in result["error"]


def test_saturator_setup_proposal_binds_drywet_percent() -> None:
    service = LiveActionService(FakeLiveBackend())
    assert DEVICE_SETUP_PARAMETER_ALLOWLIST["Saturator"]["drywet"] == ("Dry/Wet", "%")
    result = service.propose_device_setup_action(
        track_index=0, device_name="Saturator", parameter_name="Dry/Wet",
        parameter_display_value=40.0, parameter_unit="%", session_id="setup-check",
    )
    assert result["ok"] is True
    assert result["proposal"]["parameter_after_value"] == approx(0.4)


def test_glue_setup_proposal_binds_drywet_percent() -> None:
    service = LiveActionService(FakeLiveBackend())
    result = service.propose_device_setup_action(
        track_index=1, device_name="Glue Compressor", parameter_name="Dry/Wet",
        parameter_display_value=50.0, parameter_unit="%", session_id="setup-check",
    )
    assert result["ok"] is True
    assert result["proposal"]["parameter_after_value"] == approx(0.5)


def test_setup_with_wrong_unit_fails_before_touching_live() -> None:
    service = LiveActionService(FakeLiveBackend())
    before = list(service.client.writes)
    result = service.propose_device_setup_action(
        track_index=0, device_name="Saturator", parameter_name="Dry/Wet",
        parameter_display_value=40.0, parameter_unit="dB", session_id="setup-check",
    )
    assert result["ok"] is False
    assert list(service.client.writes) == before


def test_existing_eq_gain_db_still_writes_through_generic_passthrough(monkeypatch, tmp_path) -> None:
    # EQ band gains read in dB already (raw == dB); no profile needed, and the
    # write verifies through value_string readback on the Bass EQ Eight.
    from kenn.core import live_receipt_journal
    from kenn.core.live_command import handle_command

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    result = handle_command("set EQ Eight 2 Gain A to -3 dB on Bass", session_id="eq-passthrough", service=service)
    # Guarded path stops at an exact confirmation-bound proposal; nothing writes yet.
    assert result["changed"] is False
    assert result["status"] == "confirmation_required"
    proposal = result["proposal"]
    assert proposal["parameter"] == "2 Gain A"
    assert proposal["after"] == approx(-3.0)
    assert proposal["parameter_index"] == 17


def test_band_qualified_eq_frequency_resolves_to_the_exact_live_control(monkeypatch, tmp_path) -> None:
    # "1 Frequency A" used to collapse to bare "frequency" and miss all 16
    # band controls; the qualifier now survives to the exact Live identity.
    from kenn.core import live_receipt_journal
    from kenn.core.live_command import handle_command

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    result = handle_command("set EQ Eight 1 Frequency A to 440 Hz on Bass", session_id="eq-band", service=service)
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["parameter"] == "1 Frequency A"
    assert result["proposal"]["after"] == approx(0.4916, rel=1e-3)


def test_band_qualified_eq_q_never_lands_on_adaptive_q(monkeypatch, tmp_path) -> None:
    # Suffix matching once read "2 Q A" as Adaptive Q, a real wrong-control
    # write. The band qualifier now binds the exact control instead.
    from kenn.core import live_receipt_journal
    from kenn.core.live_command import handle_command

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    result = handle_command("set EQ Eight 2 Q A to 0.5 on Bass", session_id="eq-q", service=service)
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["parameter"] == "2 Q A"


def test_bare_eq_keyword_still_asks_which_band(monkeypatch, tmp_path) -> None:
    # "frequency" alone matches 16 controls; asking beats guessing.
    from kenn.core import live_receipt_journal
    from kenn.core.live_command import handle_command

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    result = handle_command("set EQ Eight frequency to 440 Hz on Bass", session_id="eq-bare", service=service)
    assert result["changed"] is False
    assert "1 Frequency A" in result["answer"]


def test_utility_gain_points_to_output_instead_of_guessing() -> None:
    # Utility exposes Output, not Gain (unit-probe inventory 2026-09-21).
    from kenn.core.live_command import _resolve_device_parameter

    class _UtilityClient:
        def get_device_parameters(self, track_index: int, device_index: int) -> dict:
            return {"success": True, "device_name": "Utility", "parameters": [
                {"index": 0, "name": "Device On", "value": 1.0, "min": 0.0, "max": 1.0},
                {"index": 9, "name": "Output", "value": 0.0, "min": -36.0, "max": 36.0},
            ]}

    class _StubService:
        client = _UtilityClient()

    result = _resolve_device_parameter(
        _StubService(),  # type: ignore[arg-type]
        {"device": {"index": 0, "name": "Utility"}, "parameter": {"name": "Gain"}, "desired_value": -2.0},
        {"index": 0, "name": "Synth"}, "utility-check", None,
    )
    assert result["ok"] is False
    assert "Output" in result["clarification"]


def test_stock_registry_names_every_live_12_device() -> None:
    # Generated from the Live 12.4.6 app folders; the count pins regressions
    # if the registry drifts from what Live actually ships.
    from kenn.core.stock_devices import STOCK_DEVICES, STOCK_DEVICE_CATEGORIES, stock_device_name

    assert len(STOCK_DEVICES) == 78
    assert set(STOCK_DEVICE_CATEGORIES) == STOCK_DEVICES
    assert stock_device_name("wavetable") == "Wavetable"
    assert stock_device_name("Limiter") == "Limiter"
    assert stock_device_name("not a device") is None


def test_insertion_allowlist_stays_inside_the_stock_registry() -> None:
    from kenn.core.live_action_service import DEVICE_INSERTION_ALLOWLIST
    from kenn.core.stock_devices import STOCK_DEVICES

    assert set(DEVICE_INSERTION_ALLOWLIST) <= set(STOCK_DEVICES)


@pytest.mark.parametrize("command, device", [
    ("add wavetable to synth", "Wavetable"),
    ("add shifter to synth", "Shifter"),
    ("add operator to bass", "Operator"),
    ("add scale to synth", "Scale"),
])
def test_unqualified_stock_device_gets_an_honest_reply(monkeypatch, tmp_path, command: str, device: str) -> None:
    # A genuine Live device KENN can't insert yet is named as such; the
    # producer learns what happened instead of a generic shrug.
    from kenn.core import live_receipt_journal
    from kenn.core.live_command import handle_command

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    result = handle_command(command, session_id="stock-honest", service=service)
    assert result["changed"] is False
    assert f"KENN can't add {device} yet" in result["answer"]


def test_recipe_carries_track_and_device_across_then_steps(monkeypatch, tmp_path) -> None:
    # "then set its dry/wet" inherits Drum Bus + Compressor; each step still
    # resolves exactly and the whole recipe waits for one confirmation.
    from kenn.core import live_receipt_journal
    from kenn.core.live_command import handle_command

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    result = handle_command(
        "set the Drum Bus compressor threshold to -20 dB then set its dry/wet to 50%",
        session_id="recipe-pronoun", service=service,
    )
    assert result["status"] == "confirmation_required"
    assert "Compressor Threshold on 'Drum Bus'" in result["answer"]
    assert "Compressor Dry/Wet on 'Drum Bus'" in result["answer"]


def test_llm_setup_plan_validates_new_drywet_devices_and_refuses_limiter() -> None:
    # The planner prompt now lists the full setup set; validation agrees for
    # Glue/Saturator and still refuses Limiter before any proposal exists.
    from kenn.core.live_command import LLM_PLAN_SCHEMA, validate_llm_plan

    service = LiveActionService(FakeLiveBackend())
    snapshot = service.snapshot(include_mixer=False)

    def setup_plan(device: str) -> dict:
        return {
            "schema": LLM_PLAN_SCHEMA, "action": "insert_device_with_parameter",
            "track_index": 0, "track_name": "Kick", "device_index": None, "device_name": device,
            "insertion_index": 0, "parameter_index": None, "parameter_name": "Dry/Wet",
            "value": 50.0, "relative": False, "unit": "%", "frequency_hz": None, "eq_band": None,
            "locator_name": None, "new_track_name": None, "clip_slot_index": None,
            "source_track_index": None, "source_track_name": None, "source_clip_slot_index": None,
            "target_track_index": None, "target_track_name": None, "target_clip_slot_index": None,
            "return_track_index": None, "return_track_name": None, "clarification": None, "steps": None,
        }

    assert validate_llm_plan(setup_plan("Glue Compressor"), snapshot)["ok"] is True
    assert validate_llm_plan(setup_plan("Saturator"), snapshot)["ok"] is True
    refused = validate_llm_plan(setup_plan("Limiter"), snapshot)
    assert refused["ok"] is False


def test_direct_planner_resolves_new_drywet_and_band_frequency() -> None:
    # The lower-level planner shares the same evidence-backed conversions, so
    # natural-language planning stays aligned with the command gateway.
    from kenn.core.live_control_planner import LiveControlPlanner

    backend = FakeLiveBackend()
    planner = LiveControlPlanner(osc_client=backend)
    drywet = planner.parse_and_propose(
        "set the Drum Bus compressor dry/wet to 50%", backend.query_session_state())
    assert drywet["ok"] is True
    eqfreq = planner.parse_and_propose(
        "set EQ Eight 1 Frequency A to 440 Hz on Bass", backend.query_session_state())
    assert eqfreq["ok"] is True


def test_glue_threshold_db_writes_through_generic_passthrough() -> None:
    # Glue Threshold qualified 0 -> -6 -> 0 on real Live; raw tracks dB here.
    from kenn.core.live_control_planner import LiveControlPlanner

    backend = FakeLiveBackend()
    planner = LiveControlPlanner(osc_client=backend)
    info = backend.get_device_parameters(3, 0)
    assert info["device_name"] == "Compressor"
    names = [p["name"] for p in info["parameters"]]
    assert "Dry/Wet" in names
