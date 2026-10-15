"""Ask must use the selected insert's current partial grade without preparing writes."""

from collections import defaultdict, deque
import json
import threading
import urllib.request

import pytest

import kenn.core.live_analysis_binding as bindings
import kenn.plugin_handoff as handoff
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_analysis_host import AbletonAnalysisHost
from kenn.core.live_track_analysis import answer_track_analysis, wants_track_analysis
from kenn.tests.test_plugin_handoff import _window
from kenn.tests.test_plugin_insert_grade import _publish, _stereo_payload


@pytest.fixture
def insert_session(monkeypatch):
    clock = [1000.0]  # Synthetic epoch seconds make endpoint and Ask payloads directly comparable.
    monkeypatch.setattr(handoff, "_live_contexts", {})
    monkeypatch.setattr(handoff, "_pending_parameter_updates", {})
    monkeypatch.setattr(bindings, "_bindings", {})
    monkeypatch.setattr(handoff.time, "time", lambda: clock[0])
    live = FakeLiveBackend()
    live._session["tracks"] = [
        {"index": 0, "name": "Kick", "volume": 0.85, "pan": 0.0, "muted": False,
         "soloed": False, "armed": False, "devices": []},
        {"index": 1, "name": "Bass", "volume": 0.75, "pan": 0.0, "muted": False,
         "soloed": False, "armed": False, "devices": []},
    ]
    return live, clock


def _ask(live, question="Grade this insert", *, owner="song", insert="kick"):
    return answer_track_analysis(question, session_id=owner, plugin_session_id=insert,
                                 host=AbletonAnalysisHost(live))


def _source_grade(insert="kick"):
    sources = handoff.plugin_insert_sources("song", insert)
    return next(source["grading"] for source in sources["sources"] if source["insert_id"] == insert)


def _assert_read_only(result, live):
    assert result is not None
    assert result["route"] == "live_track_analysis"
    assert result["proposal"] is None
    assert result["requires_confirmation"] is False
    assert result["confirmation_token"] == ""
    assert live.writes == []


def _assert_ungraded(result, live):
    _assert_read_only(result, live)
    grading = result["grading"]
    assert grading == _source_grade()
    assert grading["status"] == "ungraded"
    assert grading["grade"]["points_available"] == 0.0
    assert grading["stereo"] is None
    assert grading["reason"] in result["answer"]


@pytest.mark.parametrize("question", ["Grade this insert", "Grade Kick", "Grade track 1",
                                      "Please can you grade this insert", "Would you rate selected insert please"])
def test_grade_ask_returns_the_exact_selected_window_payload_without_a_fader_card(insert_session, question):
    live, _ = insert_session
    # A near-full-scale peak must not turn a read-only grade into the analysis route's fader proposal.
    _publish(_stereo_payload(stereo_correlation=0.3, peak_dbfs=-0.5))
    expected = _source_grade()
    result = _ask(live, question)

    _assert_read_only(result, live)
    assert result["grading"] == expected
    assert expected["grade"]["points"] == 5.1
    assert expected["grade"]["points_available"] == 6.0
    assert expected["grade"]["full_marks"] == 100.0
    answer = result["answer"]
    assert "Kick" in answer and "100 ms" in answer
    assert "5.1" in answer and "6" in answer and "100" in answer
    for field in ("source", "tier", "threshold_band"):
        assert expected["stereo"][field] in answer
    readable = answer.casefold().replace("_", " ").replace("-", " ")
    for omitted in ("dynamic health", "low end control", "spectral balance", "stem separation",
                    "declared target", "reference"):
        assert omitted in readable
    assert "not a whole" in answer
    assert "letter" not in expected["grade"]


@pytest.mark.parametrize("question", ["Grade Bass", "Grade track 2", "Grade Kick and Bass"])
def test_an_explicit_other_or_multiple_target_cannot_receive_selected_kick_points(insert_session, question):
    live, _ = insert_session
    _publish()
    _publish(_stereo_payload(host_track_name="Bass", stereo_correlation=-0.4), insert="bass")
    result = _ask(live, question)

    _assert_read_only(result, live)
    assert result["status"] == "clarification_required"
    assert "grading" not in result
    assert "6.0" not in result["answer"]


@pytest.mark.parametrize("question", ["Grade this insert and Piano", "Grade this insert, Kick and Piano"])
def test_an_explicit_binding_cannot_discard_a_named_other_target_in_a_grade_request(insert_session, question):
    live, _ = insert_session
    live._session["tracks"][1]["name"] = "Piano"
    _publish()
    bound = _ask(live, "bind this insert to track 1")
    assert bound["binding"]["track_index"] == 0
    result = _ask(live, question)

    _assert_read_only(result, live)
    assert result["status"] == "clarification_required"
    assert "grading" not in result


def test_grade_this_insert_keeps_a_revision_checked_binding_when_host_names_are_duplicated(insert_session):
    live, _ = insert_session
    live._session["tracks"][1]["name"] = "Kick"
    _publish()
    bound = _ask(live, "bind this insert to track 1")
    assert bound["binding"]["track_index"] == 0
    result = _ask(live)

    _assert_read_only(result, live)
    assert result["grading"] == _source_grade()
    assert result["analysis"]["target"]["association"] == "explicit_revision_checked"
    assert result["analysis"]["target"]["track_index"] == 0


@pytest.mark.parametrize("owner,insert", [("other", "kick"), ("", "kick"), ("song", "unknown")])
def test_missing_or_wrong_ownership_never_borrows_an_available_sibling(insert_session, owner, insert):
    live, _ = insert_session
    _publish()
    _publish(_stereo_payload(host_track_name="Bass"), insert="bass")
    result = _ask(live, owner=owner, insert=insert)

    _assert_read_only(result, live)
    assert result["status"] == "clarification_required"
    assert "grading" not in result


def test_legacy_ownerless_frame_cannot_gain_grade_points_from_a_conversation_id(insert_session):
    live, _ = insert_session
    _publish(_stereo_payload(conversation_id=""))
    result = _ask(live)

    _assert_read_only(result, live)
    assert "grading" not in result or result["grading"]["grade"]["points_available"] == 0.0
    assert result["status"] == "clarification_required"


@pytest.mark.parametrize("changes", [
    pytest.param({"rms_dbfs": -80.0}, id="quiet-boundary"),
    pytest.param({"input_channels": 1, "correlation_valid": False}, id="mono"),
    pytest.param({"legacy": True}, id="legacy-metadata"),
    pytest.param({"correlation_valid": False}, id="undefined-correlation"),
    pytest.param({"audio_age_seconds": 1.01}, id="stale-on-arrival"),
    pytest.param({"measurement_window": _window(valid=False, input_channels=2,
                                               correlation_valid=True)}, id="invalid-window"),
])
def test_unqualified_audio_has_the_same_explicit_abstention_in_ask_and_source_list(insert_session, changes):
    live, _ = insert_session
    _publish(_stereo_payload(**changes))

    _assert_ungraded(_ask(live), live)


def test_ask_expires_unrounded_audio_age_instead_of_reusing_a_previous_answer(insert_session):
    live, clock = insert_session
    _publish()
    assert _ask(live)["grading"]["status"] == "graded"
    clock[0] += 0.9999  # Seconds since capture, still within the existing one-second evidence lifetime.
    assert _ask(live)["grading"]["status"] == "graded"
    clock[0] += 0.0002  # A further 0.2 ms crosses expiry despite rounded source-list age of 1.00 s.

    _assert_ungraded(_ask(live), live)


@pytest.mark.parametrize("event", ["expiry", "pause", "reset", "owner-reassignment"])
def test_a_slow_host_read_cannot_publish_a_grade_retired_while_waiting(insert_session, monkeypatch, event):
    live, clock = insert_session
    _publish()
    host = AbletonAnalysisHost(live)
    observe = host.observe
    events = {
        "expiry": lambda: clock.__setitem__(0, clock[0] + 1.01),  # Seconds beyond the one-second evidence lifetime.
        "pause": lambda: handoff.queue_owned_plugin_parameters("kick", "song", {"live_context_enabled": False}),
        "reset": lambda: _publish(_stereo_payload(measurement_window=_window(source_generation=2, sequence=1,
            start_sample=0, end_sample=4800, input_channels=2, correlation_valid=True))),
        "owner-reassignment": lambda: _publish(_stereo_payload(conversation_id="other", analysed_samples=52800,
            measurement_window=_window(sequence=11, start_sample=48000, end_sample=52800,
                                       input_channels=2, correlation_valid=True))),
    }

    def retiring_observation():
        state = observe()
        # Model an event arriving while a fresh topology request is in flight, without scheduling sleeps.
        events[event]()
        return state

    monkeypatch.setattr(host, "observe", retiring_observation)
    result = answer_track_analysis("Grade this insert", session_id="song", plugin_session_id="kick", host=host)

    _assert_read_only(result, live)
    if event == "owner-reassignment":
        # The new owner has evidence, but the original conversation has lost permission to see it.
        assert result["status"] == "clarification_required"
        assert "grading" not in result
    else:
        _assert_ungraded(result, live)


def test_an_explicit_unmatched_number_cannot_fall_back_to_this_insert_while_live_is_offline(insert_session):
    live, _ = insert_session
    _publish()
    live._session["status"] = "offline"
    result = _ask(live, "Grade this insert and track 99")

    _assert_read_only(result, live)
    assert result["status"] == "clarification_required"
    assert "grading" not in result


def test_queued_pause_and_a_late_host_frame_cannot_restore_grade_in_ask(insert_session):
    live, _ = insert_session
    _publish()
    assert _ask(live)["grading"]["status"] == "graded"
    assert handoff.queue_owned_plugin_parameters("kick", "song", {"live_context_enabled": False})["ok"]
    _assert_ungraded(_ask(live), live)
    _publish(_stereo_payload(analysed_samples=52800,
        measurement_window=_window(sequence=11, start_sample=48000, end_sample=52800,
                                   input_channels=2, correlation_valid=True)))

    _assert_ungraded(_ask(live), live)


def test_source_generation_reset_withholds_grade_until_a_new_complete_window(insert_session):
    live, _ = insert_session
    _publish()
    assert _ask(live)["grading"]["status"] == "graded"
    _publish(_stereo_payload(measurement_window=_window(source_generation=2, sequence=1,
        start_sample=0, end_sample=4800, input_channels=2, correlation_valid=True)))
    _assert_ungraded(_ask(live), live)
    _publish(_stereo_payload(analysed_samples=9600, stereo_correlation=0.25,
        measurement_window=_window(source_generation=2, sequence=2, start_sample=4800, end_sample=9600,
                                   input_channels=2, correlation_valid=True)))
    result = _ask(live)

    assert result["grading"] == _source_grade()
    assert result["grading"]["grade"]["points"] == 5.1
    assert result["grading"]["measurement_window"]["source_generation"] == 2
    _assert_read_only(result, live)


def test_switching_selected_source_a_b_a_never_returns_latest_siblings_points(insert_session):
    live, _ = insert_session
    _publish(_stereo_payload(stereo_correlation=-0.4))
    _publish(_stereo_payload(host_track_name="Bass", stereo_correlation=0.9), insert="bass")

    for insert, name, points in (("kick", "Kick", 1.5), ("bass", "Bass", 6.0), ("kick", "Kick", 1.5)):
        result = _ask(live, insert=insert)
        _assert_read_only(result, live)
        assert result["grading"] == _source_grade(insert)
        assert result["grading"]["host_track_name"] == name
        assert result["grading"]["grade"]["points"] == points


@pytest.mark.parametrize("question", [
    "How do I grade this insert?", "What is a good grade for this track?",
    "Explain how to grade a kick", "Grade my uploaded mix", "Grade the uploaded master",
])
def test_generic_grading_and_uploaded_mix_questions_keep_their_existing_route(insert_session, question):
    live, _ = insert_session
    _publish()

    assert not wants_track_analysis(question)
    assert _ask(live, question) is None
    assert live.writes == []


def test_http_ask_preserves_selected_grade_and_pause_abstention_without_live_writes(insert_session, monkeypatch):
    import kenn.ableton_osc_bridge as bridge
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    live, _ = insert_session
    monkeypatch.setattr(bridge, "live_client", live)
    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    _publish(_stereo_payload(stereo_correlation=0.3))
    _publish(_stereo_payload(host_track_name="Bass", stereo_correlation=0.9), insert="bass")
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()

    def ask():
        request = urllib.request.Request(f"http://127.0.0.1:{httpd.server_port}/api/ask",
            data=json.dumps({"question": "Grade this insert", "session_id": "song",
                             "plugin_session_id": "kick"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    try:
        result = ask()
        _assert_read_only(result, live)
        assert result["grading"] == _source_grade()
        assert result["grading"]["grade"]["points"] == 5.1
        assert handoff.queue_owned_plugin_parameters("kick", "song", {"live_context_enabled": False})["ok"]
        _assert_ungraded(ask(), live)
    finally:
        # This fixture owns only its ephemeral FakeLive server; leave all producer processes untouched.
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)
