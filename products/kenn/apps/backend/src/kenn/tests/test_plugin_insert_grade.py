"""Selected insert grades must come from their own qualified, current stereo window."""

from copy import deepcopy

import pytest

import kenn.plugin_handoff as handoff
from kenn.core.mix_doctor import score_stereo_correlation
from kenn.tests.test_plugin_handoff import _payload, _window


@pytest.fixture(autouse=True)
def isolated_insert_clock(monkeypatch):
    clock = [1000.0]  # Synthetic epoch seconds keep receipt and expiry checks deterministic.
    monkeypatch.setattr(handoff, "_live_contexts", {})
    monkeypatch.setattr(handoff, "_pending_parameter_updates", {})
    monkeypatch.setattr(handoff.time, "time", lambda: clock[0])
    return clock


def _stereo_payload(*, input_channels=2, correlation_valid=True, legacy=False, **changes):
    metadata = {} if legacy else {"input_channels": input_channels, "correlation_valid": correlation_valid}
    payload = _payload(
        conversation_id="song", host_track_name="Kick", measurement_window=_window(**metadata),
        plugin_state={"assistant_mode": "suggest", "analysis_enabled": True, "live_context_enabled": True},
        **metadata,
    )
    payload.update(changes)
    return payload


def _publish(payload=None, *, insert="kick"):
    result = handoff.ingest_live_context(_stereo_payload() if payload is None else payload, session_id=insert)
    assert result["ok"], result
    return result


def _selected_grade(*, owner="song", insert="kick"):
    sources = handoff.plugin_insert_sources(owner, insert)
    assert sources["ok"], sources
    source, = (source for source in sources["sources"] if source["insert_id"] == insert)
    return source["grading"]


def _assert_ungraded(grading):
    assert grading["status"] == "ungraded"
    assert grading["reason"]
    assert grading["stereo"] is None
    assert grading["grade"]["points"] == 0.0
    assert grading["grade"]["points_available"] == 0.0
    assert grading["grade"]["parts"] == []
    assert {part["part"] for part in grading["grade"]["ungraded"]} == {
        "technical_health", "declared_target", "reference_match",
    }
    assert {part["dimension"] for part in grading["unscored_dimensions"]} == {
        "dynamic_health", "low_end_control", "spectral_balance", "stem_separation", "stereo_imaging",
    }


@pytest.mark.parametrize("correlation,points", [(-0.35, 1.5), (0.0, 3.6), (0.25, 5.1), (0.5, 6.0)])
def test_selected_stereo_window_reuses_existing_rule_with_only_six_points_available(correlation, points):
    payload = _stereo_payload(stereo_correlation=correlation, target_lufs=-14.0)
    receipt = _publish(payload)
    grading = _selected_grade()

    assert "grade" not in receipt["live_context"]  # A global session report must not acquire this insert's points.
    assert grading["schema"] == "kenn.plugin_insert_grade.v1"
    assert grading["scope"] == "selected_insert_window"
    assert grading["conversation_id"] == "song" and grading["insert_id"] == "kick"
    assert grading["host_track_name"] == "Kick" and grading["sample_rate"] == 48000.0
    assert grading["measurement_window"] == payload["measurement_window"]
    assert grading["freshness"] == {"age_seconds": 0.0, "max_age_seconds": 1.0, "current_for_diagnosis": True}
    assert grading["status"] == "graded" and grading["reason"] == ""
    assert grading["stereo"] == {**score_stereo_correlation(correlation), "correlation": correlation}
    combined = grading["grade"]
    assert combined["points"] == points and combined["points_available"] == 6.0
    assert combined["full_marks"] == 100.0
    technical, = combined["parts"]
    assert technical["part"] == "technical_health" and technical["full_marks"] == 30.0
    assert technical["points"] == points and technical["points_available"] == 6.0
    assert "not a whole-mix or release-readiness grade" in technical["note"]
    assert len(technical["left_out"]) == 4
    assert {part["part"] for part in combined["ungraded"]} == {"declared_target", "reference_match"}
    assert "candidate remains disabled" in combined["ungraded"][0]["reason"]
    assert "letter" not in combined and "grade" not in combined
    assert _selected_grade() == grading  # Re-reading unchanged input does not consult another session or rerun DSP.

    grading["measurement_window"]["sequence"] = 999
    assert _selected_grade()["measurement_window"]["sequence"] == 10


def test_grades_never_select_or_combine_a_sibling_or_another_conversations_insert():
    _publish(_stereo_payload(stereo_correlation=-0.4))
    _publish(_stereo_payload(host_track_name="Bass", stereo_correlation=0.9), insert="bass")
    _publish(_stereo_payload(conversation_id="other", host_track_name="Foreign"), insert="foreign")

    sources = handoff.plugin_insert_sources("song", "kick")["sources"]
    assert [source["insert_id"] for source in sources] == ["kick", "bass"]
    assert sources[0]["grading"]["grade"]["points"] == 1.5
    assert "grading" not in sources[1]
    assert _selected_grade(insert="bass")["grade"]["points"] == 6.0
    assert _selected_grade()["grade"]["points"] == 1.5
    assert not handoff.plugin_insert_sources("song", "foreign")["ok"]
    assert not handoff.plugin_insert_sources("other", "kick")["ok"]

    waiting = handoff.plugin_insert_sources("song", "unpublished")
    assert waiting["selected_status"] == "waiting_for_publication"
    assert all("grading" not in source for source in waiting["sources"])
    assert all("grading" not in source for source in handoff.plugin_insert_sources("song")["sources"])


@pytest.mark.parametrize(
    "changes,reason",
    [
        pytest.param({"input_channels": 1, "correlation_valid": False}, "mono", id="mono"),
        pytest.param({"correlation_valid": False}, "undefined", id="undefined"),
        pytest.param({"legacy": True}, "layout is missing", id="legacy"),
        pytest.param({"rms_dbfs": -80.0}, "activity floor", id="quiet-boundary"),
        pytest.param({"rms_dbfs": -100.0}, "activity floor", id="quiet"),
        pytest.param({"measurement_window": None}, "100 ms", id="no-contiguous-window"),
        pytest.param({"audio_age_seconds": 1.01}, "stale", id="stale-on-arrival"),
        pytest.param({"plugin_state": {"assistant_mode": "suggest", "analysis_enabled": False}}, "paused", id="disabled"),
    ],
)
def test_unqualified_window_metadata_or_audio_abstains_from_grade(changes, reason):
    _publish(_stereo_payload(**changes))
    grading = _selected_grade()

    _assert_ungraded(grading)
    assert reason in grading["reason"]


def test_subsecond_age_is_not_rounded_into_an_extra_grade_lifetime(isolated_insert_clock):
    _publish()
    isolated_insert_clock[0] += 0.9999  # Seconds since capture, just inside the one-second lifetime.
    assert _selected_grade()["status"] == "graded"
    isolated_insert_clock[0] += 0.0002  # A further 0.2 ms must expire even though the source list rounds to 1.00 s.
    source, = handoff.plugin_insert_sources("song", "kick")["sources"]

    assert source["audio_age_seconds"] == 1.0
    assert source["grading"]["freshness"]["age_seconds"] == pytest.approx(1.0001)
    _assert_ungraded(source["grading"])


def test_queued_pause_retires_grade_before_host_acknowledgement_and_late_publication():
    _publish()
    assert _selected_grade()["status"] == "graded"
    assert handoff.queue_owned_plugin_parameters("kick", "song", {"live_context_enabled": False})["ok"]
    _assert_ungraded(_selected_grade())
    _publish(_stereo_payload(analysed_samples=52800,
        measurement_window=_window(sequence=11, start_sample=48000, end_sample=52800,
                                   input_channels=2, correlation_valid=True)))
    source, = handoff.plugin_insert_sources("song", "kick")["sources"]

    assert source["reported_parameters"]["live_context_enabled"] is True
    assert source["requested_parameters"]["live_context_enabled"] is False
    _assert_ungraded(source["grading"])


def test_new_source_generation_cannot_inherit_grade_until_audio_advances():
    _publish()
    _publish(_stereo_payload(measurement_window=_window(source_generation=2, sequence=1,
        start_sample=0, end_sample=4800, input_channels=2, correlation_valid=True)))
    _assert_ungraded(_selected_grade())
    _publish(_stereo_payload(analysed_samples=9600, stereo_correlation=0.25,
        measurement_window=_window(source_generation=2, sequence=2, start_sample=4800, end_sample=9600,
                                   input_channels=2, correlation_valid=True)))

    grading = _selected_grade()
    assert grading["measurement_window"]["source_generation"] == 2
    assert grading["grade"]["points"] == 5.1


def test_invalid_window_retires_grade_and_old_http_copy_cannot_resurrect_it():
    valid = _stereo_payload()
    _publish(valid)
    invalid = deepcopy(valid)
    invalid["measurement_window"]["valid"] = False
    _publish(invalid)
    _assert_ungraded(_selected_grade())

    assert not handoff.ingest_live_context(valid, session_id="kick")["ok"]
    _assert_ungraded(_selected_grade())


@pytest.mark.parametrize("location", ["frame", "window"])
@pytest.mark.parametrize(
    "metadata",
    [
        {"input_channels": 2}, {"correlation_valid": True},
        {"input_channels": True, "correlation_valid": False},
        {"input_channels": 2.0, "correlation_valid": True},
        {"input_channels": "2", "correlation_valid": True},
        {"input_channels": 3, "correlation_valid": True},
        {"input_channels": 2, "correlation_valid": 1},
        {"input_channels": 2, "correlation_valid": "true"},
        {"input_channels": 1, "correlation_valid": True},
    ],
)
def test_malformed_eligibility_is_rejected_before_replacing_qualified_grade(location, metadata):
    _publish()
    before = deepcopy(handoff._live_contexts["kick"])
    grading = _selected_grade()
    malformed = _stereo_payload()
    target = malformed if location == "frame" else malformed["measurement_window"]
    target.pop("input_channels")
    target.pop("correlation_valid")
    target.update(metadata)

    assert not handoff.ingest_live_context(malformed, session_id="kick")["ok"]
    assert handoff._live_contexts["kick"] == before
    assert _selected_grade() == grading


@pytest.mark.parametrize("metadata", [{}, {"input_channels": 1, "correlation_valid": False},
                                      {"input_channels": 2, "correlation_valid": False}])
def test_frame_and_window_eligibility_must_agree_before_any_grade_is_cached(metadata):
    payload = _stereo_payload()
    payload["measurement_window"].pop("input_channels")
    payload["measurement_window"].pop("correlation_valid")
    payload["measurement_window"].update(metadata)

    assert not handoff.ingest_live_context(payload, session_id="kick")["ok"]
    assert handoff._live_contexts == {}


@pytest.mark.parametrize("original", [{"legacy": True}, {"input_channels": 1, "correlation_valid": False},
                                      {"correlation_valid": False}])
def test_same_sequence_cannot_upgrade_old_correlation_eligibility(original):
    _publish(_stereo_payload(**original))
    initial = _selected_grade()
    _assert_ungraded(initial)
    result = handoff.ingest_live_context(_stereo_payload(), session_id="kick")

    assert not result["ok"] and "without a new audio window" in result["error"]
    assert _selected_grade() == initial
    _publish(_stereo_payload(analysed_samples=52800,
        measurement_window=_window(sequence=11, start_sample=48000, end_sample=52800,
                                   input_channels=2, correlation_valid=True)))
    assert _selected_grade()["status"] == "graded"
