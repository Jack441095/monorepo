"""Current-insert advice must stay attributed, reversible, and approval gated."""

from __future__ import annotations

from copy import deepcopy
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

import pytest

import kenn.plugin_handoff as handoff
import kenn.core.live_analysis_binding as bindings
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_analysis_host import AbletonAnalysisHost
from kenn.core.live_track_analysis import answer_track_analysis, wants_track_analysis
from kenn.tests.test_plugin_handoff import _payload, _window


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(handoff, "_live_contexts", {})
    monkeypatch.setattr(bindings, "_bindings", {})
    fake = FakeLiveBackend()
    fake._session["tracks"] = [
        {"index": 0, "name": "Kick", "volume": 0.85, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
        {"index": 1, "name": "Bass", "volume": 0.75, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
    ]
    return fake


def _ask(live, question="Analyse the kick and tell me what to change", **metrics):
    handoff.ingest_live_context(_payload(host_track_name="Kick", peak_dbfs=-0.5, **metrics), session_id="insert")
    return answer_track_analysis(question, session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))


@pytest.mark.parametrize("question", ["Analyse the kick", "bind this insert to track 1"])
def test_published_owner_must_match_before_using_audio_or_preparing_a_card(live, question):
    # A browser once ignored the native conversation, making an insert ID alone
    # sufficient to use another owner's measurements and create a fader card.
    result = _ask(live, question, conversation_id="another-chat")
    assert result["status"] == "clarification_required" and "another conversation" in result["answer"]
    assert "analysis" not in result and result["proposal"] is None
    assert live.writes == [] and bindings._bindings == {}


@pytest.mark.parametrize("question", ["Analyse the kick", "Analyze track 1", "What should I change on this channel?"])
def test_requests_bind_only_the_unique_measured_track(live, question):
    result = _ask(live, question)
    assert result["analysis"]["target"]["track_index"] == 0
    assert result["analysis"]["session"]["source"] == "fresh_live_snapshot"
    assert result["analysis"]["measured"]["sample_headroom_db"] == 0.5
    assert result["requires_confirmation"] is True
    assert result["proposal"]["action"] == "set_volume"
    assert result["proposal"]["after_db"] == pytest.approx(-2.5, abs=0.02)
    assert live.writes == []


@pytest.mark.parametrize("name", ["Bass", "Drums", "Lead Vocal", "Synth", "Drum Bus"])
def test_measurements_and_fader_policy_are_not_specific_to_kick(live, name):
    live._session["tracks"][0]["name"] = name
    live._session["tracks"][1]["name"] = "Other part"
    handoff.ingest_live_context(_payload(host_track_name=name, peak_dbfs=-0.5), session_id="insert")
    result = answer_track_analysis(f"Analyse {name}", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    # Role labels locate the insert but never become an automatic EQ recipe.
    assert result["analysis"]["target"]["name"] == name
    assert result["proposal"]["action"] == "set_volume"


def test_unmeasured_track_and_duplicate_names_require_context(live):
    other = _ask(live, "Analyse the bass")
    assert other["status"] == "clarification_required"
    assert other["analysis"]["measured"] == {}
    assert other["proposal"] is None
    live._session["tracks"][1]["name"] = "Kick"
    duplicate = _ask(live, "Analyse the kick")
    assert "Which track number" in duplicate["answer"]
    numbered = _ask(live, "Analyse track 1")
    assert numbered["proposal"] is None  # A number cannot prove which duplicated host name supplies audio.
    assert live.writes == []


@pytest.mark.parametrize("question", ["Analyse track 1 and channel 2", "Is the bass masking the kick?"])
def test_multi_track_requests_ask_for_one_source_without_attributing_its_audio(live, question):
    # The first named/numbered track must not silently stand in for a comparison.
    result = _ask(live, question)
    assert result["status"] == "clarification_required"
    assert result["analysis"]["measured"] == {}
    assert result["proposal"] is None
    assert live.writes == []


def test_headroom_audition_near_the_reserve_uses_only_a_small_reduction(live):
    handoff.ingest_live_context(_payload(host_track_name="Kick", peak_dbfs=-2.9), session_id="insert")
    result = answer_track_analysis("Analyse kick", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert result["proposal"]["after_db"] == pytest.approx(-0.1, abs=0.02)
    assert live.writes == []


def test_missing_stale_disabled_and_silent_input_abstain(live, monkeypatch):
    missing = answer_track_analysis("Analyse the kick", session_id="chat", host=AbletonAnalysisHost(live))
    assert missing["confidence"] == "unknown"
    disabled = _ask(live, plugin_state={"analysis_enabled": False})
    assert disabled["analysis"]["measured"] == {}
    _ask(live)
    received_at = handoff._live_contexts["insert"]["received_at"]
    monkeypatch.setattr(handoff.time, "time", lambda: received_at + 16.0)
    stale = answer_track_analysis("Analyse the kick", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert stale["proposal"] is None
    silent = _ask(live, rms_dbfs=-100.0, analysed_samples=96000)
    assert silent["confidence"] == "unknown"
    assert silent["analysis"]["recommendations"] == []


@pytest.mark.parametrize("question", ["Is sidechain compression working on this track?", "Is the kick masking anything on this track?"])
def test_sidechain_and_masking_never_invent_routing_or_offer_automatic_changes(live, question):
    result = _ask(live, question, crest_db=2.0, low_energy=1.0)
    assert result["confidence"] == "unknown"
    assert result["proposal"] is None
    assert "cannot determine" in result["answer"]
    assert "routing" not in result["analysis"]["session"]
    assert "integrated_lufs" not in result["analysis"]["measured"]
    assert "true_peak_dbtp" not in result["analysis"]["measured"]


def test_full_scale_and_negative_correlation_offer_evidence_based_manual_checks(live):
    result = _ask(live, clipped_samples=12, stereo_correlation=-0.8)
    manual = [r for r in result["analysis"]["recommendations"] if r["application"] == "manual"]
    assert {r["issue"] for r in manual} == {"near_full_scale_input", "negative_correlation"}
    assert all(r["evidence"] and r["expected_effect"] and r["trade_off"] for r in manual)
    assert "cannot repair" in result["answer"]
    assert live.writes == []


def test_ask_mode_and_read_only_backend_fall_back_to_manual_fader(live):
    result = _ask(live, assistant_mode="ask", plugin_state={"assistant_mode": "ask", "analysis_enabled": True})
    assert result["proposal"] is None
    live.read_only = True
    result = _ask(live)
    assert result["proposal"] is None
    assert result["analysis"]["recommendations"][0]["application"] == "manual"
    assert "manually" in result["answer"]
    assert live.writes == []


def test_offline_and_master_insert_analysis_has_no_live_control(live):
    live._session["status"] = "offline"
    result = _ask(live, "Analyse this channel")
    assert result["analysis"]["target"]["association"] == "insert_only"
    assert result["proposal"] is None
    live._session["status"] = "connected"
    handoff.ingest_live_context(_payload(host_track_name="Master"), session_id="master")
    result = answer_track_analysis("Analyse the master", session_id="master", host=AbletonAnalysisHost(live))
    assert result["analysis"]["target"]["association"] == "insert_only"
    assert result["proposal"] is None


def test_sparse_meter_history_is_not_reported_as_compression_or_dynamic_range(live):
    for count, rms in enumerate((-24.0, -12.0, -18.0), start=1):
        handoff.ingest_live_context(_payload(host_track_name="Kick", rms_dbfs=rms, crest_db=2.0, analysed_samples=count * 48000), session_id="insert")
    result = answer_track_analysis("Analyse kick", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert "-24.0 to -12.0" in result["answer"]
    assert "cannot prove compression" in result["answer"]
    assert result["analysis"]["measured"]["live_window"]["status"] == "changing"
    assert result["proposal"] is None


def test_confirmation_apply_readback_and_undo_leave_other_tracks_untouched(live):
    result = _ask(live)
    service = LiveActionService(live)
    proposal = result["proposal"]
    before = live.query_session_state()
    assert service.execute(proposal, confirm_token="", session_id="chat")["ok"] is False
    assert service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="another-chat")["ok"] is False
    assert live.writes == []
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="chat")
    assert applied["ok"] and applied["receipt"]["verified"]
    assert live.query_session_state()["tracks"][1] == before["tracks"][1]
    undo = service.propose_undo(applied["receipt"], session_id="chat")["proposal"]
    assert service.execute(undo, confirm_token="", session_id="chat")["ok"] is False
    restored = service.execute(undo, confirm_token=undo["confirmation_token"], session_id="chat")
    assert restored["ok"] and restored["receipt"]["verified"]
    assert live.query_session_state()["tracks"] == before["tracks"]


@pytest.mark.parametrize("change", ["fader", "name", "tampered_card"])
def test_changed_state_and_tampered_analysis_cards_cannot_write(live, change):
    proposal = _ask(live)["proposal"]
    if change == "fader":
        live._session["tracks"][0]["volume"] = 0.7
    elif change == "name":
        live._session["tracks"][0]["name"] = "Snare"
    else:
        proposal = {**deepcopy(proposal), "after": 1.0}
    refused = LiveActionService(live).execute(proposal, confirm_token=proposal["confirmation_token"], session_id="chat")
    assert refused["ok"] is False
    assert live.writes == []


def test_generic_engineering_questions_keep_the_existing_knowledge_route():
    assert not wants_track_analysis("How do I analyse a kick?")
    assert not wants_track_analysis("What is sidechain compression?")
    assert not wants_track_analysis("Lower track 1 by 2 dB")


def _bind(live, question="bind this insert to track 1", **metrics):
    handoff.ingest_live_context(_payload(host_track_name="Kick", measurement_window=_window(), **metrics), session_id="insert")
    return answer_track_analysis(question, session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))


def test_explicit_binding_is_owner_scoped_metadata_and_never_changes_live(live):
    bound = _bind(live)
    assert bound["binding"]["track_index"] == 0
    assert bound["proposal"] is None
    answer = answer_track_analysis("Analyse this insert", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert answer["analysis"]["target"]["association"] == "explicit_revision_checked"
    assert "100 ms" in answer["analysis"]["measurement_scope"]
    assert "stereo-power" in answer["answer"]
    other = answer_track_analysis("Analyse this insert", session_id="other", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert other["analysis"]["target"]["association"] == "unique_host_name"
    unbound = answer_track_analysis("unbind this insert", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert "Cleared" in unbound["answer"]
    assert not bindings._bindings and live.writes == []


@pytest.mark.parametrize("change", ["rename", "reorder", "generation", "reset", "expiry"])
def test_explicit_association_rejects_stale_revision_instead_of_falling_back(live, monkeypatch, change):
    _bind(live)
    if change == "rename":
        live._session["tracks"][1]["name"] = "Other bass"
    elif change == "reorder":
        live._session["tracks"].reverse()
    elif change == "generation":
        handoff.ingest_live_context(_payload(host_track_name="Kick", analysed_samples=52800,
            measurement_window=_window(source_generation=2, sequence=11, start_sample=48000, end_sample=52800)), session_id="insert")
    elif change == "reset":
        handoff.ingest_live_context(_payload(host_track_name="Kick", analysed_samples=4800,
            measurement_window=_window(source_generation=2, sequence=1, start_sample=0, end_sample=4800)), session_id="insert")
    else:
        created = bindings._bindings[("chat", "insert")]["created_at"]
        monkeypatch.setattr(bindings.time, "monotonic", lambda: created + 301.0)
    answer = answer_track_analysis("Analyse this insert", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert answer["status"] == "clarification_required"
    assert answer["analysis"]["measured"] == {} and answer["proposal"] is None
    assert live.writes == []


def test_binding_cannot_override_conflicting_host_or_upgrade_control_authority(live):
    assert "Place it" in _bind(live, "bind this insert to Bass")["answer"]
    live._session["tracks"][1]["name"] = "Kick"
    assert "binding" in _bind(live)
    answer = answer_track_analysis("Analyse track 1", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert answer["analysis"]["measured"] and answer["proposal"] is None
    assert live.writes == []


def test_missing_host_binding_allows_observations_without_fader_authority(live):
    handoff.ingest_live_context(_payload(measurement_window=_window()), session_id="insert")
    bound = answer_track_analysis("bind this insert to track 1", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert "binding" in bound
    answer = answer_track_analysis("Analyse this insert", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert answer["analysis"]["target"]["track_index"] == 0 and answer["proposal"] is None
    assert live.writes == []


def test_binding_requires_continuous_fresh_audio_but_unbinding_does_not(live):
    _ask(live)  # Legacy handoffs have no coherent source generation.
    result = answer_track_analysis("bind this insert to track 1", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert "binding" not in result
    handoff._live_contexts.clear()
    cleared = answer_track_analysis("unbind this insert", session_id="chat", plugin_session_id="insert", host=AbletonAnalysisHost(live))
    assert "Cleared" in cleared["answer"] and live.writes == []


def test_http_native_features_to_chat_card_to_confirmed_fake_write(live, monkeypatch):
    import kenn.ableton_osc_bridge as bridge
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit
    import kenn.core.live_action_service as actions

    monkeypatch.setattr(bridge, "live_client", live)
    monkeypatch.setattr(actions, "live_client", live)
    rate_limit.RATE_BUCKETS.clear()
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()

    def post(path, payload):
        request = urllib.request.Request(f"http://127.0.0.1:{httpd.server_port}{path}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            # Refused confirmations are expected HTTP responses, not transport failures.
            response = error
        with response:
            return json.loads(response.read())

    try:
        native_binary = os.environ.get("KENN_NATIVE_COMMAND_TEST_BINARY")
        if native_binary:
            # Opt in after compiling JUCE; ordinary backend runs need no native toolchain.
            native = subprocess.run([native_binary], env={**os.environ,
                "KENN_TEST_ENDPOINT": f"http://127.0.0.1:{httpd.server_port}",
                "KENN_TEST_ANALYSIS_TRACK": "Kick", "KENN_TEST_OFFLINE_ONLY": "0"},
                capture_output=True, text=True, timeout=30)
            assert native.returncode == 0, native.stdout + native.stderr
            assert "SUCCESS: native insert analysis" in native.stdout
            assert "SUCCESS: two native inserts" in native.stdout
            assert live.writes == []
        response = post("/api/ask", {"question": "Analyse the kick", "session_id": "http-analysis", "plugin_handoff": _payload(host_track_name="Kick", peak_dbfs=-0.5)})
        assert response["route"] == "live_track_analysis"
        assert response["requires_confirmation"] is True
        assert live.writes == []
        # Abstentions once used a confidence value outside the HTTP envelope's
        # enum, causing connection resets even though direct calls succeeded.
        for question, owner, extra in (
            ("unbind this insert", "http-empty", {}),
            ("Analyse this insert", "http-empty", {}),
            ("Is sidechain compression working on the kick?", "http-sidechain",
             {"plugin_handoff": _payload(host_track_name="Kick")}),
            ("Analyse the kick", "http-silence",
             {"plugin_handoff": _payload(host_track_name="Kick", rms_dbfs=-90.0)}),
            ("Analyse the kick", "http-delayed",
             {"plugin_handoff": _payload(host_track_name="Kick", measurement_window=_window(), exported_at_epoch=time.time() - 1.2)}),
        ):
            abstention = post("/api/ask", {"question": question, "session_id": owner, **extra})
            assert abstention["confidence"] == "unknown", abstention
            assert abstention["proposal"] is None and not abstention["requires_confirmation"]
        assert live.writes == []
        proposal = response["proposal"]
        blocked = post("/api/ableton/command", {"proposal": proposal, "session_id": "http-analysis"})
        assert blocked["status"] in {"requires_confirmation", "failed"}
        assert live.writes == []
        applied = post("/api/ableton/command", {"proposal": proposal, "confirm_token": proposal["confirmation_token"], "session_id": "http-analysis"})
        assert applied["status"] == "applied", applied
        assert applied["receipt"]["verified"] is True
        assert len(live.writes) == 1
        raw_audio = post("/api/ask", {"question": "Analyse the kick", "session_id": "http-analysis", "plugin_handoff": _payload(raw_audio=[0.0])})
        assert "Raw audio" in raw_audio["error"]
        # Cached DSP batches must survive an exhausted control bucket without
        # lifting the existing endpoint permissions or allowing a Live write.
        from kenn.core.endpoint_policy import endpoint_policy
        assert endpoint_policy("kenn", "POST", "/api/plugin-handoff-batch").permissions == endpoint_policy("kenn", "POST", "/api/plugin-handoff").permissions
        rate_limit.RATE_BUCKETS.clear()
        for _ in range(60):
            assert rate_limit.rate_allowed("127.0.0.1", "mutation")[0]
        batch = post("/api/plugin-handoff-batch", {"schema": "kenn.plugin_handoff_batch.v1",
            "frames": [_payload(session_id="batch-http-kick"), _payload(session_id="batch-http-bass")]})
        assert batch["ok"] and len(batch["frames"]) == 2
        still_blocked = post("/api/ableton/command", {"proposal": proposal, "confirm_token": proposal["confirmation_token"], "session_id": "http-analysis"})
        assert "Too many requests" in still_blocked["error"] and len(live.writes) == 1
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize("profile", ["short", "delayed", "memory", "sustained"])
def test_native_feature_publishers_remain_fresh_with_64_inserts(live, monkeypatch, profile):
    """Profile real native HTTP delivery without contacting or writing a producer session."""
    binary = os.environ.get("KENN_NATIVE_PUBLISH_TEST_BINARY")
    if not binary:
        # Ordinary backend verification does not require a native toolchain.
        pytest.skip("Compile TestRealtimePerformance and opt in to the 12-second HTTP profile.")
    if profile == "sustained" and os.environ.get("KENN_NATIVE_PUBLISH_SUSTAINED") != "1":
        # The 65-second run crosses the 60-second rate bucket only when explicitly requested.
        pytest.skip("Set KENN_NATIVE_PUBLISH_SUSTAINED=1 for sustained 64-insert transport profiling.")
    import re
    import resource
    import sys
    from collections import defaultdict, deque
    import kenn.ableton_osc_bridge as bridge
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    monkeypatch.setattr(bridge, "live_client", live)
    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    records = []
    record_lock = threading.Lock()

    class ProfileHandler(server.Handler):
        def do_POST(self):
            self.profile_started = time.perf_counter()
            if profile == "delayed" and not records:
                # Hold already-exported audio for 1.05 s, below the native 1.2 s
                # HTTP timeout but beyond the one-second diagnosis lifetime.
                time.sleep(1.05)
            super().do_POST()

        def send_json(self, status, payload):
            super().send_json(status, payload)
            with record_lock:
                records.append({"status": status, "frames": payload.get("frames") or [],
                                "bytes": int(self.headers.get("Content-Length", "0")),
                                "completed_at": time.perf_counter(),
                                "handler_ms": (time.perf_counter() - self.profile_started) * 1000})

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), ProfileHandler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    companion_started = time.process_time()
    try:
        profile_env = {**os.environ, "KENN_TEST_PUBLISH_ENDPOINT": f"http://127.0.0.1:{httpd.server_port}"}
        if profile != "short":
            profile_env["KENN_TEST_PUBLISH_SECONDS"] = {"delayed": "5", "memory": "15", "sustained": "65"}[profile]
        else:
            profile_env.pop("KENN_TEST_PUBLISH_SECONDS", None)  # An inherited duration must not change the four-cell short profile.
        native = subprocess.run([binary], env=profile_env, capture_output=True, text=True, timeout=90)
        assert native.returncode == 0, "\n".join(line for line in native.stdout.splitlines()
            if not line.startswith("publisher ")) + native.stderr
        inserts = re.findall(r"publisher instances=\d+ insert=(\S+)", native.stdout)
        assert len(inserts) == len(set(inserts)) == (105 if profile == "short" else 64)
        frames = [frame for row in records for frame in row["frames"]]
        counts = {insert: sum(frame["session_id"] == insert for frame in frames) for insert in inserts}
        assert min(counts.values()) >= 2, {
            "underdelivered_inserts": sum(count < 2 for count in counts.values()),
            "request_bytes_max": max((row["bytes"] for row in records), default=0),
            "batch_frames_max": max((len(row["frames"]) for row in records), default=0),
        }
        assert all(row["status"] == 200 for row in records), records
        assert max(row["bytes"] for row in records) <= 1024 * 1024  # The normal 1 MiB HTTP cap remains in force at 64 inserts.
        assert all(frame["ok"] for frame in frames), frames
        if profile == "delayed":
            assert all(not frame["freshness"]["current_for_diagnosis"] for frame in records[0]["frames"]), "Delayed audio was made fresh at HTTP receipt."
            assert all(frame["freshness"]["current_for_diagnosis"] for row in records[1:] for frame in row["frames"])
        else:
            assert all(frame["freshness"]["current_for_diagnosis"] for frame in frames), frames
        delivery_gaps = [current["completed_at"] - previous["completed_at"] for previous, current in zip(records, records[1:])]
        if profile == "sustained":
            # Cover the entire 60-second bucket and reject a plateau long enough
            # to expire a continuous source; request/serialization time reduces
            # the cadence below the publisher's upper limit of two batches/s.
            assert records[-1]["completed_at"] - records[0]["completed_at"] >= 60
            assert max(delivery_gaps) < 1.0
        assert live.writes == []
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        handler = sorted(row["handler_ms"] for row in records)
        # ru_maxrss is bytes on macOS and KiB on Linux. This opt-in profile is
        # run in its own pytest process so earlier child peaks cannot mask RSS.
        rss_bytes = after.ru_maxrss if sys.platform == "darwin" else after.ru_maxrss * 1024
        print(native.stdout)
        print(json.dumps({"native_publisher_profile": {
            "profile": profile,
            "requests": len(records), "frames": len(frames), "deliveries_per_insert_min": min(counts.values()),
            "request_bytes_min": min(row["bytes"] for row in records), "request_bytes_max": max(row["bytes"] for row in records),
            "handler_p99_ms": handler[int(0.99 * (len(handler) - 1))], "handler_max_ms": max(handler),
            "delivery_gap_max_seconds": max(delivery_gaps),
            "capture_age_max_seconds": max(frame["freshness"]["age_seconds"] for frame in frames),
            "native_cpu_seconds": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
            "native_max_rss_bytes": rss_bytes, "companion_cpu_seconds": time.process_time() - companion_started,
        }}, sort_keys=True))
    finally:
        # Stop the isolated fixture even when delivery fails; it owns no Live state.
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)
