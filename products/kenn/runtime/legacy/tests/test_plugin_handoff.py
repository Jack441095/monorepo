import io
import json

from kenn import server
from kenn.plugin_handoff import ingest_live_context, live_context_summary, review_from_handoff, validate_handoff


def _payload(**overrides):
    result = {
        "schema": "kenn.plugin_handoff.v1", "kind": "mix_review_snapshot",
        "peak_dbfs": -0.1, "rms_dbfs": -12.0, "stereo_correlation": -0.2,
        "stereo_width": 0.8, "sample_rate": 48000, "analysed_samples": 96000,
    }
    result.update(overrides)
    return result


def test_validates_a_native_plugin_snapshot():
    checked = validate_handoff(_payload())
    assert checked["ok"] is True
    assert checked["metrics"]["peak_dbfs"] == -0.1


def test_rejects_an_unknown_schema_and_empty_snapshot():
    assert validate_handoff(_payload(schema="other"))["ok"] is False
    assert validate_handoff(_payload(audio_feature_schema="audio_feature_frame.v0"))["ok"] is False
    assert validate_handoff(_payload(analysed_samples=0))["ok"] is False
    assert validate_handoff(_payload(assistant_mode="unsafe"))["ok"] is False


def test_review_flags_risk_without_starting_automix():
    result = review_from_handoff(_payload())
    titles = {item["title"] for item in result["observations"]}
    assert result["ok"] is True
    assert "Very little peak headroom" in titles
    assert "Potential mono-compatibility risk" in titles
    assert result["automix"]["available"] is False


def test_review_reports_recent_clipping_when_feature_frame_includes_it():
    result = review_from_handoff(_payload(clipped_samples=4, crest_db=7.0, transient_ratio=1.2))
    titles = {item["title"] for item in result["observations"]}
    assert result["ok"] is True
    assert "Recent samples reached digital full scale" in titles


def test_ingests_session_scoped_live_context_without_audio():
    result = ingest_live_context(_payload(assistant_mode="assist", plugin_state={"assistant_mode": "assist", "target_lufs": -14.0, "analysis_enabled": True, "live_context_enabled": False}), session_id="plugin-session")
    assert result["ok"] is True
    context = live_context_summary("plugin-session")
    assert context and context["schema"] == "kenn.live_mix_context.v1"
    assert context["peak_dbfs"] == -0.1
    assert context["assistant_mode"] == "assist"
    assert context["plugin_state"]["target_lufs"] == -14.0


def test_ask_mode_returns_observations_but_not_action_proposals():
    result = ingest_live_context(_payload(assistant_mode="ask"), session_id="ask-plugin-session")
    assert result["ok"] is True
    assert result["assistant_mode"] == "ask"
    assert result["action_proposals"] == []


class _Handler(server.Handler):
    def __init__(self, body: bytes):
        self.path = "/api/plugin-handoff"
        self.headers = {"Content-Length": str(len(body))}
        self.client_address = ("127.0.0.1", 0)
        self.rfile = io.BytesIO(body)
        self.status = 0
        self.sent_json = {}

    def send_json(self, status, payload):
        self.status, self.sent_json = status, payload

    def enforce_rate_limit(self, scope):
        return True


class _AutoMixLimitHandler(_Handler):
    def __init__(self, length: int):
        self.path = "/api/automix-upload"
        self.headers = {"Content-Type": "multipart/form-data; boundary=test", "Content-Length": str(length)}
        self.client_address = ("127.0.0.1", 0)
        self.rfile = io.BytesIO()
        self.status = 0
        self.sent_json = {}


def test_local_plugin_handoff_endpoint_returns_a_review():
    handler = _Handler(json.dumps(_payload()).encode())
    server.Handler.do_POST(handler)
    assert handler.status == 200
    assert handler.sent_json["schema"] == "kenn.plugin_review.v1"


def test_local_plugin_handoff_returns_a_confirmable_scoped_proposal():
    handler = _Handler(json.dumps(_payload(target_lufs=-14.0, session_id="plugin-session")).encode())
    server.Handler.do_POST(handler)
    proposal = handler.sent_json["action_proposals"][0]
    assert handler.sent_json["session_id"] == "plugin-session"
    assert proposal["schema"] == "kenn.action_proposal.v1"
    assert proposal["target"] == "kenn_mix_assistant"
    assert proposal["parameter"] == "target_lufs"
    assert proposal["requires_confirmation"] is True
    assert proposal["undo"]["value"] == -14.0


def test_automix_upload_limit_is_500_mb_not_the_old_150_mb_cap():
    handler = _AutoMixLimitHandler(500 * 1024 * 1024 + 1)
    server.Handler.do_POST(handler)
    assert handler.status == 413
    assert "500 MB" in handler.sent_json["error"]


def test_live_context_turn_marks_its_measurement_boundary():
    ingest_live_context(_payload(), session_id="chat-plugin")
    turn = server._plugin_live_context_turn("chat-plugin")
    assert turn and turn["content"].startswith("KENN_EVIDENCE_PACKET_V1:")
    from kenn.core.evidence import packets_from_history
    packets = packets_from_history([turn])
    assert len(packets) == 1
    assert any(fact.name == "peak_dbfs" and fact.value == -0.1 for fact in packets[0].facts)
    assert "no track" in packets[0].limitations[0].lower()
