"""Paired advice needs actual matching clocks, owner declarations and bounded spectra."""

from copy import deepcopy

import pytest

import kenn.plugin_handoff as handoff
from kenn.core.live_analysis_host import AbletonAnalysisHost
from kenn.core.live_track_analysis import answer_track_analysis
from kenn.tests.test_live_track_analysis import live
from kenn.tests.test_plugin_handoff import _payload, _window


def _frame(name="Kick", *, end=48000, local_offset=0, epoch=2, band=5, size=8192, age=0.0):
    local_end = end - local_offset
    power = [0.0] * 32
    power[band] = 0.125
    fft = {"size_samples": size, "start_sample": local_end-size, "end_sample": local_end,
           "bin_hz": 48000/size, "mean_square": 0.125, "peak_hz": 10*48000/size, "band_power": power}
    window = _window(sequence=end//4800, start_sample=local_end-4800, end_sample=local_end,
                     host_timeline={"schema": "kenn.host_timeline.v1", "valid": True, "transport_epoch": epoch,
                                    "start_sample": end-4800, "end_sample": end})
    return _payload(host_track_name=name, measurement_window=window, analysed_samples=local_end, audio_age_seconds=age,
                    fft_spectra={"schema": "kenn.fft_spectra.v1", "low": fft, "fast": None})


def _bind(live, payload, index, *, owner="chat", insert=None):
    insert = insert or payload["host_track_name"]
    assert handoff.ingest_live_context(payload, session_id=insert)["ok"]
    result = answer_track_analysis(f"bind this insert to track {index+1}", session_id=owner, plugin_session_id=insert, host=AbletonAnalysisHost(live))
    assert "binding" in result


def _pair(live, question="Is the bass masking the kick?", owner="chat"):
    return answer_track_analysis(question, session_id=owner, host=AbletonAnalysisHost(live))


def test_matching_host_samples_allow_different_insert_counters_and_local_epochs(live):
    _bind(live, _frame(), 0)
    _bind(live, _frame("Bass", local_offset=97, epoch=17), 1)
    result = _pair(live)
    assert result["status"] == "analysed" and result["confidence"] == "medium"
    assert result["analysis"]["measured"]["spectral_shape_similarity"] == pytest.approx(1.0)
    assert result["analysis"]["measured"]["fft_host_start_sample"] == 48000-8192
    assert result["analysis"]["measured"]["metric_host_start_sample"] == 43200
    assert "does not prove audible masking" in result["answer"]
    assert "routing" not in result["analysis"]["session"]
    assert result["proposal"] is None and live.writes == []


def test_reassigning_a_published_conversation_retires_its_previous_paired_binding(live):
    kick, bass = _frame(), _frame("Bass")
    kick["conversation_id"] = bass["conversation_id"] = "chat"
    _bind(live, kick, 0)
    _bind(live, bass, 1)
    bass["conversation_id"] = "other-chat"
    assert handoff.ingest_live_context(bass, session_id="Bass")["ok"]
    result = _pair(live)
    assert result["status"] == "clarification_required"
    assert result["analysis"]["measured"] == {} and result["proposal"] is None
    assert live.writes == []


@pytest.mark.parametrize("change", ["other_owner", "no_clock", "different_interval", "old_loop_pass", "stale", "warmup", "disabled", "different_rate", "rename", "duplicate_insert"])
def test_missing_or_misaligned_pair_abstains_without_writes(live, change):
    _bind(live, _frame(), 0)
    bass = _frame("Bass")
    if change == "no_clock":
        bass["measurement_window"].pop("host_timeline")
    elif change == "different_interval":
        bass = _frame("Bass", end=52800)
    elif change == "old_loop_pass":
        bass["audio_age_seconds"] = 0.2  # Same sample indexes on an earlier loop are not aligned current audio.
    elif change == "warmup":
        bass["fft_spectra"]["low"] = None
    elif change == "different_rate":
        bass["sample_rate"] = 96000
        bass["measurement_window"].update(start_sample=38400, duration_seconds=0.1)
        bass["measurement_window"]["host_timeline"]["start_sample"] = 38400
        bass["fft_spectra"]["low"]["bin_hz"] = 96000/8192
    _bind(live, bass, 1, owner="other" if change == "other_owner" else "chat")
    if change in {"stale", "disabled"}:
        bass["analysed_samples"] += 4800
        bass["measurement_window"] = {**bass["measurement_window"], "sequence": 11, "valid": False}
        bass["measurement_window"]["host_timeline"]["valid"] = False
        bass["fft_spectra"]["low"] = None
        if change == "disabled":
            bass["plugin_state"]["analysis_enabled"] = False
        assert handoff.ingest_live_context(bass, session_id="Bass")["ok"]
    elif change == "rename":
        live._session["tracks"][1]["name"] = "Other bass"
    elif change == "duplicate_insert":
        _bind(live, _frame("Bass"), 1, insert="another-bass")
    result = _pair(live)
    assert result["status"] == "clarification_required" and result["confidence"] == "unknown"
    assert result["analysis"]["measured"] == {} and result["proposal"] is None
    assert live.writes == []


def test_disjoint_group_power_is_measured_without_calling_it_a_masking_diagnosis(live):
    _bind(live, _frame(band=3), 0)
    _bind(live, _frame("Bass", band=9), 1)
    result = _pair(live)
    assert result["analysis"]["measured"]["spectral_shape_similarity"] == 0
    assert all(item["application"] == "manual" for item in result["analysis"]["recommendations"])
    sidechain = _pair(live, "Is kick and bass sidechain compression working?")
    assert sidechain["confidence"] == "unknown" and sidechain["analysis"]["sidechain_status"] == "unknown"


def test_bound_silent_low_end_has_no_shape_similarity(live):
    _bind(live, _frame(), 0)
    quiet = _frame("Bass")
    quiet["fft_spectra"]["low"]["band_power"] = [0.0] * 32
    quiet["fft_spectra"]["low"]["mean_square"] = 0.0
    _bind(live, quiet, 1)
    result = _pair(live)
    assert result["confidence"] == "unknown" and "spectral_shape_similarity" not in result["analysis"]["measured"]


@pytest.mark.parametrize("field,value", [("size_samples", True), ("size_samples", 8192.0), ("size_samples", 2048), ("end_sample", 48001),
                                        ("start_sample", -1), ("bin_hz", 10), ("mean_square", 10**400), ("mean_square", float("inf")),
                                        ("peak_hz", 25000), ("band_power", [0]*33), ("band_power", [float("nan")]*32),
                                        ("band_power", [1]*32)])
def test_fft_contract_rejects_false_precision_and_unbounded_data(field, value):
    payload = _frame()
    payload["fft_spectra"]["low"][field] = value
    assert not handoff.validate_handoff(payload)["ok"]


@pytest.mark.parametrize("changes", [{"start_sample": 43201}, {"end_sample": 48001}, {"transport_epoch": True},
                                    {"start_sample": float("nan")}, {"valid": "true"}])
def test_host_clock_contract_rejects_incoherent_sample_grid(changes):
    payload = _frame()
    payload["measurement_window"]["host_timeline"].update(changes)
    assert not handoff.validate_handoff(payload)["ok"]


def _history_entry(payload):
    fields = ("measurement_window", "fft_spectra", "peak_dbfs", "rms_dbfs", "stereo_correlation", "stereo_width", "analysed_samples", "audio_age_seconds")
    return {key: deepcopy(payload[key]) for key in fields}


def test_six_window_history_bridges_publisher_phase_offset(live):
    kick = _frame(end=52800)
    old_kick = _frame(end=48000, age=0.1)
    kick["paired_windows"] = [_history_entry(old_kick), _history_entry(kick)]
    _bind(live, kick, 0)
    _bind(live, _frame("Bass", age=0.1), 1)
    result = _pair(live)
    assert result["status"] == "analysed"
    assert result["analysis"]["measured"]["metric_host_end_sample"] == 48000


def test_transport_epoch_change_clears_trends_without_expiring_track_binding(live):
    _bind(live, _frame(), 0)
    after_loop = _frame(end=52800, epoch=3)
    result = handoff.ingest_live_context(after_loop, session_id="Kick")
    assert result["live_context"]["live_window"]["sample_count"] == 1
    answer = answer_track_analysis("Analyse this insert", session_id="chat", plugin_session_id="Kick", host=AbletonAnalysisHost(live))
    assert answer["analysis"]["target"]["association"] == "explicit_revision_checked"


def test_signed_host_preroll_is_valid_without_inventing_a_local_counter_reset():
    payload = _frame()
    payload["measurement_window"]["host_timeline"].update(start_sample=-4800, end_sample=0)
    assert handoff.validate_handoff(payload)["ok"]


def test_resending_cached_history_cannot_refresh_its_capture_time(live, monkeypatch):
    payload = _frame()
    payload["paired_windows"] = [_history_entry(payload)]
    monkeypatch.setattr(handoff.time, "time", lambda: 1000.0)
    assert handoff.ingest_live_context(payload, session_id="Kick")["ok"]
    monkeypatch.setattr(handoff.time, "time", lambda: 1000.75)
    context = handoff.ingest_live_context(payload, session_id="Kick")["live_context"]
    assert context["paired_windows"][0]["observed_at_epoch"] == 1000.0
    assert context["paired_windows"][0]["age_seconds"] == 0.75


def test_parameter_queues_resolve_a_single_insert_and_refuse_ambiguous_conversations(live, monkeypatch):
    monkeypatch.setattr(handoff, "_pending_parameter_updates", {})
    kick = _frame(); kick["conversation_id"] = "chat"
    assert handoff.ingest_live_context(kick, session_id="Kick")["ok"]
    assert handoff.set_plugin_parameter("chat", "target_lufs", -12.0)["session_id"] == "Kick"
    assert handoff.pop_pending_parameter_updates("Kick")["pending_updates"] == {"target_lufs": -12.0}
    bass = _frame("Bass"); bass["conversation_id"] = "chat"
    assert handoff.ingest_live_context(bass, session_id="Bass")["ok"]
    assert not handoff.set_plugin_parameter("chat", "target_lufs", -10.0)["ok"]
    assert not handoff.get_plugin_parameters("chat")["ok"]
    assert handoff.set_plugin_parameter("Kick", "target_lufs", -11.0)["ok"]
    assert handoff.pop_pending_parameter_updates("Bass")["pending_updates"] == {}
    assert handoff.pop_pending_parameter_updates("Kick")["pending_updates"] == {"target_lufs": -11.0}


@pytest.mark.parametrize("change", ["too_many", "cross_epoch", "cross_source", "misordered", "raw_audio", "future", "too_old"])
def test_paired_history_cannot_smuggle_audio_or_bridge_discontinuities(change):
    payload = _frame(end=52800)
    entry = _history_entry(_frame(end=48000, age=0.1))
    payload["paired_windows"] = [entry]
    if change == "too_many":
        payload["paired_windows"] *= 7
    elif change == "cross_epoch":
        entry["measurement_window"]["host_timeline"]["transport_epoch"] += 1
    elif change == "cross_source":
        entry["measurement_window"]["source_generation"] += 1
    elif change == "misordered":
        payload["paired_windows"] *= 2
    elif change == "raw_audio":
        entry["raw_audio"] = [0.0]
    elif change == "future":
        payload["paired_windows"] = [_history_entry(_frame(end=57600))]
    elif change == "too_old":
        payload["paired_windows"] = [_history_entry(_frame(end=19200, age=0.7))]
    assert not handoff.validate_handoff(payload)["ok"]
