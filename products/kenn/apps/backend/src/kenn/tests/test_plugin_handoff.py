from __future__ import annotations

import time
import pytest

import kenn.plugin_handoff as plugin_handoff
from kenn.plugin_handoff import ingest_live_context, live_context_summary, pink_noise_reference_from_spectrum, review_from_handoff, validate_handoff


def _payload(**overrides):
    payload = {
        "schema": "kenn.plugin_handoff.v1",
        "audio_feature_schema": "audio_feature_frame.v1",
        "kind": "mix_review_snapshot",
        "assistant_mode": "suggest",
        "peak_dbfs": -4.0,
        "rms_dbfs": -16.0,
        "stereo_correlation": 0.7,
        "stereo_width": 0.2,
        "sample_rate": 48000.0,
        "analysed_samples": 48000,
        "audio_age_seconds": 0.0,
        "low_energy": 0.03,
        "mid_energy": 0.01,
        "high_energy": 0.002,
        "plugin_state": {"assistant_mode": "suggest", "analysis_enabled": True},
    }
    payload.update(overrides)
    return payload


def _window(**overrides):
    window = {"schema": "kenn.continuous_window.v1", "valid": True, "sequence": 10, "source_generation": 1,
              "start_sample": 43200, "end_sample": 48000, "duration_seconds": 0.1, "dropped_samples": 0, "invalid_samples": 0}
    window.update(overrides)
    return window


def test_feature_batch_keeps_64_insert_identities_and_returns_only_acknowledgements(monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    frames = [_payload(session_id=f"batch-{index}", conversation_id="shared-chat", host_track_name=f"Track {index}",
                       rms_dbfs=-10.0 - index, measurement_window=_window()) for index in range(64)]
    result = plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1", "frames": frames})
    assert result["ok"] and len(result["frames"]) == 64
    for index, acknowledgement in enumerate(result["frames"]):
        assert set(acknowledgement) == {"session_id", "ok", "freshness"}
        context = live_context_summary(acknowledgement["session_id"])
        assert context["host_track_name"] == f"Track {index}" and context["rms_dbfs"] == -10.0 - index


def test_batch_validation_time_cannot_retime_siblings_or_rejuvenate_audio(monkeypatch):
    # Serial validation used to shift sibling capture clocks enough to reject
    # a genuine paired interval; the shared receipt must include that elapsed age.
    clock = [1000.0]  # Synthetic epoch seconds, independent of wall-clock scheduling.
    validate = plugin_handoff.validate_handoff

    def delayed_validation(frame):
        clock[0] += 0.06  # 60 ms per check exceeds the paired capture-time tolerance.
        return validate(frame)

    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: clock[0])
    monkeypatch.setattr(plugin_handoff, "validate_handoff", delayed_validation)
    plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1",
        "frames": [_payload(session_id="first", measurement_window=_window()),
                   _payload(session_id="second", measurement_window=_window())]})
    first, second = (live_context_summary(key)["freshness"] for key in ("first", "second"))
    assert first["observed_at_epoch"] == second["observed_at_epoch"] == 1000.0
    assert first["age_seconds"] == second["age_seconds"] == round(clock[0] - 1000.0, 2)


@pytest.mark.parametrize("transport", ["batch", "frame", "both"])
def test_batch_export_clock_counts_transport_delay_for_current_and_paired_audio(monkeypatch, transport):
    # A stalled HTTP upload must not give already-exported windows another
    # second of currentness when the companion finally reads the request.
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: 1001.2)
    frame = _payload(session_id="delayed", measurement_window=_window(host_timeline={"schema": "kenn.host_timeline.v1",
        "valid": True, "transport_epoch": 1, "start_sample": 43200, "end_sample": 48000}), audio_age_seconds=0.1,
        fft_spectra={"schema": "kenn.fft_spectra.v1", "fast": None, "low": None})
    frame["paired_windows"] = [{key: frame[key] for key in ("measurement_window", "fft_spectra", "peak_dbfs", "rms_dbfs",
        "stereo_correlation", "stereo_width", "analysed_samples", "audio_age_seconds")}]
    if transport != "batch":
        frame["exported_at_epoch"] = 1000.0
    if transport == "frame":
        result = ingest_live_context(frame, session_id="delayed")
    else:
        result = plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1",
            "exported_at_epoch": 1000.0, "frames": [frame]})
    assert result["ok"]
    context = live_context_summary("delayed")
    assert context["freshness"]["received_at_epoch"] == 1001.2
    assert context["freshness"]["observed_at_epoch"] == pytest.approx(999.9)
    assert context["freshness"]["age_seconds"] == 1.3 and not context["freshness"]["current_for_diagnosis"]
    assert context["paired_windows"][0]["observed_at_epoch"] == pytest.approx(999.9)


@pytest.mark.parametrize("exported", [None, True, "1000", -1, float("nan"), float("inf"), 10 ** 1000, 1001.3])
def test_invalid_or_future_batch_export_clock_cannot_replace_audio(exported, monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: 1001.2)
    result = plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1",
        "exported_at_epoch": exported, "frames": [_payload(session_id="clock")]})
    assert not result["ok"] and plugin_handoff._live_contexts == {}


def test_small_future_export_clock_is_clamped_to_receipt_without_extending_lifetime(monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: 1001.2)
    result = plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1",
        "exported_at_epoch": 1001.22, "frames": [_payload(session_id="clock", audio_age_seconds=0.1)]})
    assert result["ok"]
    assert live_context_summary("clock")["freshness"]["observed_at_epoch"] == pytest.approx(1001.1)


@pytest.mark.parametrize("exported", [None, True, "1000", -1, float("nan"), float("inf"), 10 ** 1000, 1001.3])
def test_invalid_native_frame_export_clock_cannot_partially_replace_a_batch(exported, monkeypatch):
    # Ask and individual handoffs use the same export clock as the publisher;
    # preflight must catch a bad sibling before the first insert is cached.
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: 1001.2)
    result = plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1", "frames": [
        _payload(session_id="first"), _payload(session_id="invalid", exported_at_epoch=exported)]})
    assert not result["ok"] and plugin_handoff._live_contexts == {}


def test_frame_export_clock_cannot_make_an_older_batch_clock_younger(monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: 1001.2)
    result = plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1", "exported_at_epoch": 1000.0,
        "frames": [_payload(session_id="clock", exported_at_epoch=1001.2, audio_age_seconds=0.1)]})
    assert result["ok"]
    assert live_context_summary("clock")["freshness"]["observed_at_epoch"] == pytest.approx(999.9)


def test_wall_clock_step_during_review_refuses_snapshot_without_cache_mutation(monkeypatch):
    # A local clock step between validation passes must abstain rather than
    # throw or retain a packet that has become too far ahead of receipt.
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    clock = iter([1000.0, 1000.0, 999.0])  # Local epoch seconds during review, receipt and final validation.
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: next(clock))
    result = ingest_live_context(_payload(exported_at_epoch=1000.0), session_id="clock-step")
    assert not result["ok"] and plugin_handoff._live_contexts == {}


@pytest.mark.parametrize("change", ["schema", "empty", "not_list", "too_many", "duplicate", "missing_id", "blank_id", "long_id", "raw_audio", "control"])
def test_malformed_feature_batch_never_partially_replaces_an_insert(change, monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    batch = {"schema": "kenn.plugin_handoff_batch.v1", "frames": [_payload(session_id="first"), _payload(session_id="second")]}
    if change == "schema": batch["schema"] = "other"
    elif change == "empty": batch["frames"] = []
    elif change == "not_list": batch["frames"] = {}
    elif change == "too_many": batch["frames"] = [_payload(session_id=str(index)) for index in range(65)]
    elif change == "duplicate": batch["frames"][1]["session_id"] = " first "
    elif change == "missing_id": del batch["frames"][1]["session_id"]
    elif change == "blank_id": batch["frames"][1]["session_id"] = " "
    elif change == "long_id": batch["frames"][1]["session_id"] = "x" * 129
    elif change == "raw_audio": batch["frames"][1]["raw_audio"] = [0.0]
    else: batch["execute"] = "set_volume"
    assert not plugin_handoff.ingest_live_context_batch(batch)["ok"]
    assert plugin_handoff._live_contexts == {}


def test_one_stale_frame_does_not_refresh_itself_or_discard_a_current_sibling(monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    first = _payload(session_id="first", measurement_window=_window())
    ingest_live_context(_payload(session_id="first", analysed_samples=52800,
        measurement_window=_window(sequence=11, start_sample=48000, end_sample=52800)), session_id="first")
    observed = plugin_handoff._live_contexts["first"]["audio_observed_at"]
    result = plugin_handoff.ingest_live_context_batch({"schema": "kenn.plugin_handoff_batch.v1",
        "frames": [first, _payload(session_id="second", measurement_window=_window())]})
    assert not result["ok"] and not result["frames"][0]["ok"] and result["frames"][1]["ok"]
    assert plugin_handoff._live_contexts["first"]["audio_observed_at"] == observed
    assert live_context_summary("second")["freshness"]["current_for_diagnosis"]


@pytest.mark.parametrize("changes", [{"duration_seconds": 0.2}, {"start_sample": 47999}, {"sequence": True},
                                    {"source_generation": -1}, {"dropped_samples": 0.5}, {"valid": "yes"}, {"invalid_samples": float("nan")}])
def test_continuous_window_rejects_incoherent_or_unbounded_metadata(changes):
    assert not validate_handoff(_payload(measurement_window=_window(**changes)))["ok"]


def test_continuous_gaps_retire_advice_and_full_windows_recover(monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    current = _payload(measurement_window=_window(), peak_dbfs=-0.1)
    assert ingest_live_context(current, session_id="continuous")["live_context"]["freshness"]["current_for_diagnosis"]
    gap = ingest_live_context({**current, "measurement_window": _window(valid=False)}, session_id="continuous")
    assert gap["action_proposals"] == []
    assert not gap["live_context"]["freshness"]["current_for_diagnosis"]
    assert gap["live_context"]["live_window"]["sample_count"] == 0
    # A delayed HTTP copy of the retired frame cannot make it current again.
    assert not ingest_live_context(current, session_id="continuous")["ok"]
    restored = ingest_live_context({**current, "analysed_samples": 52800,
        "measurement_window": _window(sequence=11, start_sample=52800, end_sample=57600, dropped_samples=4800)}, session_id="continuous")
    assert restored["live_context"]["freshness"]["current_for_diagnosis"]
    assert restored["live_context"]["measurement_window"]["dropped_samples"] == 4800
    assert restored["live_context"]["live_window"]["sample_count"] == 1
    assert not ingest_live_context(current, session_id="continuous")["ok"]


def test_continuous_audio_age_includes_worker_backlog_and_expires_after_one_second(monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    assert not ingest_live_context(_payload(measurement_window=_window(), audio_age_seconds=1.01), session_id="continuous")["live_context"]["freshness"]["current_for_diagnosis"]
    ingest_live_context(_payload(measurement_window=_window(sequence=11, start_sample=48000, end_sample=52800), analysed_samples=52800), session_id="continuous")
    observed = plugin_handoff._live_contexts["continuous"]["audio_observed_at"]
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: observed + 1.01)
    context = live_context_summary("continuous")
    assert context["measurement_window"]["duration_seconds"] == 0.1
    assert not context["freshness"]["current_for_diagnosis"]
    assert context["freshness"]["max_current_age_seconds"] == 1.0


def test_expired_repeated_handoff_stays_unavailable_without_advice_or_exception(monkeypatch):
    monkeypatch.setattr(plugin_handoff, "_live_contexts", {})
    payload = _payload(peak_dbfs=-0.1)
    ingest_live_context(payload, session_id="expired")
    observed = plugin_handoff._live_contexts["expired"]["received_at"]
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: observed + 1801.0)  # Beyond the 30-minute retention limit.
    result = ingest_live_context(payload, session_id="expired")
    assert result["live_context"] is None and result["action_proposals"] == []


def _spectrum():
    return [
        {"center_hz": 315.0, "low_hz": 280.6, "high_hz": 353.6, "energy": 0.1},
        {"center_hz": 1000.0, "low_hz": 891.0, "high_hz": 1122.5, "energy": 0.01},
        {"center_hz": 2000.0, "low_hz": 1782.0, "high_hz": 2245.0, "energy": 0.0025},
    ]


def _evidence():
    return {
        "schema": "kenn.evidence.v1",
        "source": "plugin_bus_snapshot",
        "captured_at_age_seconds": 0.0,
        "observed_at_epoch": None,
        "facts": [{"name": "peak_dbfs", "value": -4.0, "unit": "dBFS", "source": "plugin_bus_snapshot", "confidence": "measured"}],
        "limitations": ["Bus snapshot only."],
    }


def test_handoff_accepts_realtime_band_metrics() -> None:
    checked = validate_handoff(_payload())
    assert checked["ok"] is True
    assert checked["metrics"]["low_energy"] == 0.03

    review = review_from_handoff(_payload())
    assert review["ok"] is True
    assert any(item["title"] == "Realtime tonal snapshot available" for item in review["observations"])


def test_handoff_rejects_raw_audio_and_nonfinite_metrics() -> None:
    assert validate_handoff(_payload(raw_audio=[0.0]))["ok"] is False
    assert validate_handoff(_payload(low_energy=float("nan")))["ok"] is False


def test_handoff_validates_optional_shared_evidence_packet() -> None:
    assert validate_handoff(_payload(evidence=_evidence()))["ok"] is True
    assert validate_handoff(_payload(evidence={**_evidence(), "source": "mix_review_upload"}))["ok"] is False
    bad = _evidence()
    bad["facts"] = [{**bad["facts"][0], "value": float("nan")}]
    assert validate_handoff(_payload(evidence=bad))["ok"] is False


def test_realtime_spectrum_is_validated_and_compared_to_pink_baseline() -> None:
    checked = validate_handoff(_payload(spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()))
    assert checked["ok"] is True
    reference = checked["pink_noise_reference"]
    assert reference["status"] == "complete"
    assert reference["anchor_frequency_hz"] == 1000.0
    largest = reference["largest_deviation"]
    assert largest["center_hz"] == 315.0
    assert largest["deviation_db"] > 0

    review = review_from_handoff(_payload(spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()))
    assert any(item["title"] == "Realtime spectral reference available" for item in review["observations"])
    assert "uncalibrated pink-noise-style shape reference" in review["limitations"]


def test_realtime_spectrum_rejects_bad_bounds_and_order() -> None:
    assert validate_handoff(_payload(spectrum_bands=[{"center_hz": 300.0, "low_hz": 320.0, "high_hz": 400.0, "energy": 0.1}]))["ok"] is False
    assert validate_handoff(_payload(spectrum_bands=[_spectrum()[1], _spectrum()[0]]))["ok"] is False
    assert validate_handoff(_payload(spectrum_bands=[{"center_hz": 300.0, "low_hz": 250.0, "high_hz": 350.0, "energy": 17.0}]))["ok"] is False


def test_pink_reference_abstains_when_anchor_is_silent() -> None:
    assert pink_noise_reference_from_spectrum([{"center_hz": 1000.0, "energy": 0.0}])["status"] == "abstained"


def test_live_context_keeps_bounded_window_and_freshness_receipt() -> None:
    session_id = "window-test"
    for frame_index, peak in enumerate((-5.0, -4.8, -5.1) * 5):
        result = ingest_live_context(
            _payload(session_id=session_id, analysed_samples=(frame_index + 1) * 48000, peak_dbfs=peak, spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()),
            session_id=session_id,
        )
    context = live_context_summary(session_id)
    assert context is not None
    assert context["live_window"]["sample_count"] == 12
    assert context["live_window"]["status"] == "stable"
    assert context["freshness"]["frame_count"] == 12
    assert context["freshness"]["ttl_seconds"] == 1800
    assert context["freshness"]["status"] == "current"
    assert context["freshness"]["current_for_diagnosis"] is True
    assert context["freshness"]["max_current_age_seconds"] == 15.0
    assert result["live_context"]["live_window"]["sample_count"] == 12


def test_repeated_stopped_audio_does_not_refresh_diagnosis_or_history(monkeypatch) -> None:
    # An 8-second publisher tick used to make the same stopped audio current forever.
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: 1000.0)
    ingest_live_context(_payload(host_track_name="Kick"), session_id="stopped")
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: 1016.0)
    repeated = ingest_live_context(_payload(host_track_name="Kick"), session_id="stopped")["live_context"]
    assert repeated["freshness"]["current_for_diagnosis"] is False
    assert repeated["live_window"]["sample_count"] == 1


def test_analysis_disabled_and_source_changes_cannot_inherit_current_history() -> None:
    ingest_live_context(_payload(host_track_name="Kick"), session_id="source-change")
    changed = ingest_live_context(_payload(host_track_name="Bass", analysed_samples=96000), session_id="source-change")["live_context"]
    assert changed["host_track_name"] == "Bass"
    assert changed["live_window"]["sample_count"] == 1
    disabled = ingest_live_context(_payload(host_track_name="Bass", analysed_samples=144000, plugin_state={"analysis_enabled": False}), session_id="source-change")["live_context"]
    assert disabled["freshness"]["current_for_diagnosis"] is False


def test_host_names_are_bounded_and_insert_metrics_do_not_become_master_loudness(monkeypatch) -> None:
    import kenn.audio_telemetry as telemetry

    deliveries = []
    monkeypatch.setattr(telemetry.get_telemetry_manager(), "ingest", deliveries.append)
    assert validate_handoff(_payload(host_track_name="K" * 129))["ok"] is False
    assert validate_handoff(_payload(host_track_name=1))["ok"] is False
    result = ingest_live_context(_payload(host_track_name="Kick"), session_id="no-invented-loudness")
    assert result["ok"] is True
    assert "integrated_lufs" not in result["live_context"]
    assert "true_peak_dbtp" not in result["live_context"]
    assert deliveries == []


def test_first_delivery_of_old_audio_and_rename_without_audio_stay_stale() -> None:
    old = ingest_live_context(_payload(audio_age_seconds=30.0), session_id="old-first")["live_context"]
    assert old["freshness"]["current_for_diagnosis"] is False
    ingest_live_context(_payload(host_track_name="Kick"), session_id="rename-stopped")
    renamed = ingest_live_context(_payload(host_track_name="Bass"), session_id="rename-stopped")["live_context"]
    assert renamed["freshness"]["current_for_diagnosis"] is False
    resumed = ingest_live_context(_payload(host_track_name="Bass", analysed_samples=96000), session_id="rename-stopped")["live_context"]
    assert resumed["freshness"]["current_for_diagnosis"] is True
    assert resumed["live_window"]["sample_count"] == 1


def test_live_context_marks_retained_but_old_context_stale_for_diagnosis(monkeypatch) -> None:
    session_id = "stale-diagnosis-test"
    ingest_live_context(_payload(session_id=session_id), session_id=session_id)
    received_at = plugin_handoff._live_contexts[session_id]["received_at"]
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: received_at + 15.01)

    context = live_context_summary(session_id)
    assert context is not None
    assert context["freshness"]["status"] == "stale_or_unknown"
    assert context["freshness"]["current_for_diagnosis"] is False
    assert context["freshness"]["age_seconds"] == 15.01
    assert context["freshness"]["ttl_seconds"] == 1800


def test_ingested_context_exposes_band_metrics_without_audio() -> None:
    result = ingest_live_context(_payload(session_id="handoff-test", spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()), session_id="handoff-test")
    assert result["ok"] is True
    context = result["live_context"]
    assert context["scope"] == "plugin_bus"
    assert context["low_energy"] == 0.03
    assert context["spectrum_bands"][1]["center_hz"] == 1000.0
    assert context["pink_noise_reference"]["status"] == "complete"
    assert context["evidence"]["schema"] == "kenn.evidence.v1"
    assert context["evidence"]["source"] == "plugin_bus_snapshot"
    assert any(fact["name"] == "peak_dbfs" for fact in context["evidence"]["facts"])
    assert "raw_audio" not in context
