import os
import json
import pytest
from unittest.mock import MagicMock, patch

from thursday.macros import Macro, MacroStep, execute_macro, MacroStepError
from thursday.registry import ServiceDef
from thursday.session_manager import get_or_create_session
from server.app.routes.thursday_routes import handle_thursday_post


class FakeHandler:
    def __init__(self, body_dict):
        self.body_dict = body_dict
        self.response_status = None
        self.response_headers = {}
        self.response_body = None

    def read_body_bytes(self):
        return json.dumps(self.body_dict).encode("utf-8")

    def read_json_body(self):
        return self.body_dict

    def send_json(self, status, body):
        self.response_status = status
        self.response_body = body

    def send_response(self, status):
        self.response_status = status

    def send_header(self, key, value):
        self.response_headers[key] = value

    def end_headers(self):
        pass

    @property
    def wfile(self):
        class FakeWFile:
            def __init__(self, handler):
                self.handler = handler
            def write(self, data):
                self.handler.response_body = data
            def flush(self):
                pass
        return FakeWFile(self)


def test_macro_execution_success_path():
    macro_data = {
        "description": "Test Success Macro",
        "steps": [
            {"say": "Hello user"},
            {"service": "test_service_1"}
        ]
    }
    macro = Macro("TestSuccess", macro_data)
    
    # Mock services
    mock_service_1 = ServiceDef(
        name="Test Service 1",
        description="Test Service 1 Description",
        triggers=[],
        action=lambda ctx, api, text: "Service 1 Output"
    )
    
    with patch("thursday.registry.build_services", return_value={"test_service_1": mock_service_1}):
        session = {"turns": [], "context": {}}
        results = execute_macro(macro, lambda t, s: f"NLU {t}", session)
        
        assert len(results) == 2
        assert results[0] == "Hello user"
        assert results[1] == "Service 1 Output"


def test_macro_execution_failure_propagation():
    macro_data = {
        "description": "Test Failure Macro",
        "steps": [
            {"say": "Starting"},
            {"service": "test_service_success"},
            {"service": "test_service_fail"},
            {"service": "test_service_should_not_run"}
        ]
    }
    macro = Macro("TestFailure", macro_data)
    
    # Mock services
    mock_service_success = ServiceDef(
        name="Success Service",
        description="Success Service Description",
        triggers=[],
        action=lambda ctx, api, text: "Success Output"
    )
    mock_service_fail = ServiceDef(
        name="Fail Service",
        description="Fail Service Description",
        triggers=[],
        action=MagicMock(side_effect=ValueError("Database connection timeout"))
    )
    mock_service_should_not_run = ServiceDef(
        name="Should Not Run",
        description="Should Not Run Description",
        triggers=[],
        action=lambda ctx, api, text: "Should not see this"
    )
    
    services_map = {
        "test_service_success": mock_service_success,
        "test_service_fail": mock_service_fail,
        "test_service_should_not_run": mock_service_should_not_run
    }
    
    with patch("thursday.registry.build_services", return_value=services_map):
        session = {"turns": [], "context": {}}
        results = execute_macro(macro, lambda t, s: f"NLU {t}", session)
        
        # Should halt after failure of step 3
        assert len(results) == 3
        assert results[0] == "Starting"
        assert results[1] == "Success Output"
        
        # Check structured partial success message
        error_result = results[2]
        assert "Stages Stage 1 (Say), Stage 2 (test_service_success) completed." in error_result
        assert "Stage 3 (test_service_fail) failed:" in error_result
        assert "Database connection timeout" in error_result
        assert "Recovery suggestions:" in error_result


def test_thursday_feedback_endpoint_api(tmp_path, monkeypatch):
    monkeypatch.setattr("thursday.session_manager.SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr("thursday.session_manager.SESSION_FILE", tmp_path / ".session")
    monkeypatch.setattr("thursday.feedback.FEEDBACK_LOG", tmp_path / "feedback.jsonl")

    # Create dummy session
    session = get_or_create_session("sess-1")
    session["turns"] = [
        {
            "role": "user",
            "text": "hello",
            "timestamp": "2026-08-08T19:00:00.000000",
            "intent": "greeting",
            "service_used": ""
        },
        {
            "role": "thursday",
            "text": "Hi there!",
            "timestamp": "2026-08-08T19:00:01.000000",
            "intent": "greeting",
            "service_used": "greeting"
        }
    ]
    from thursday.session_manager import _save_session
    _save_session(session)

    # Test valid POST
    handler = FakeHandler({
        "turn_id": "2026-08-08T19:00:01.000000",
        "rating": 1,
        "session_id": "sess-1"
    })
    
    handled = handle_thursday_post(handler, "/api/thursday/feedback")
    assert handled is True
    assert handler.response_status == 200
    assert handler.response_body["ok"] is True
    assert handler.response_body["rating"] == 1

    # Verify feedback file content
    feedback_file = tmp_path / "feedback.jsonl"
    assert feedback_file.exists()
    lines = feedback_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    feedback_record = json.loads(lines[0])
    assert feedback_record["turn_id"] == "2026-08-08T19:00:01.000000"
    assert feedback_record["explicit_rating"] == 1
    assert feedback_record["service_id"] == "greeting"

    # Test invalid rating POST
    handler_invalid = FakeHandler({
        "turn_id": "2026-08-08T19:00:01.000000",
        "rating": "not-an-int",
        "session_id": "sess-1"
    })
    handled = handle_thursday_post(handler_invalid, "/api/thursday/feedback")
    assert handled is True
    assert handler_invalid.response_status == 400
