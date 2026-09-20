"""Tests for thursday/ops/notify_ops.py (founder request, 2026-09-02).

No real network calls -- ntfy's HTTP call is mocked at the
urllib.request.urlopen boundary, same discipline as
test_thursday_research_ops.py.
"""

from __future__ import annotations

import urllib.error

import thursday.ops.notify_ops as no


class _FakeResponse:
    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_push_notification_reports_evidence_missing_without_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    result = no.send_push_notification("title", "message")
    assert result["ok"] is False
    assert "NTFY_TOPIC" in result["error"]


def test_send_push_notification_posts_to_configured_topic(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-secret-topic")
    captured = {}

    def _fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["title"] = req.headers.get("Title")
        captured["data"] = req.data
        return _FakeResponse()

    monkeypatch.setattr(no.urllib.request, "urlopen", _fake_urlopen)
    result = no.send_push_notification("Alert!", "something happened")
    assert result["ok"] is True
    assert captured["url"] == "https://ntfy.sh/my-secret-topic"
    assert captured["title"] == "Alert!"
    assert captured["data"] == b"something happened"


def test_send_push_notification_respects_custom_server(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "topic")
    monkeypatch.setenv("NTFY_SERVER_URL", "https://ntfy.example.com/")
    captured = {}

    def _fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        return _FakeResponse()

    monkeypatch.setattr(no.urllib.request, "urlopen", _fake_urlopen)
    no.send_push_notification("t", "m")
    assert captured["url"] == "https://ntfy.example.com/topic"


def test_send_push_notification_handles_http_error(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "topic")

    def _raise(req, timeout):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr(no.urllib.request, "urlopen", _raise)
    result = no.send_push_notification("t", "m")
    assert result["ok"] is False
    assert "404" in result["error"]


def test_notify_from_alert_skips_info_severity(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "topic")
    result = no.notify_from_alert({"severity": "info", "type": "new_lead", "message": "x"})
    assert result["ok"] is False
    assert "not pushed" in result["error"]


def test_notify_from_alert_pushes_warning_and_critical(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "topic")
    captured = []

    def _fake_urlopen(req, timeout):
        captured.append(req.headers.get("Priority"))
        return _FakeResponse()

    monkeypatch.setattr(no.urllib.request, "urlopen", _fake_urlopen)

    result_warn = no.notify_from_alert({"severity": "warning", "type": "overdue_invoice", "message": "Invoice overdue"})
    result_crit = no.notify_from_alert({"severity": "critical", "type": "financial_health", "message": "Cash low"})
    assert result_warn["ok"] is True
    assert result_crit["ok"] is True
    assert captured == ["high", "urgent"]


def test_parse_notify_me_command_matches_prefixes():
    assert no.parse_notify_me_command("notify me: check the beta feedback") == "check the beta feedback"
    assert no.parse_notify_me_command("send notification: test") == "test"


def test_parse_notify_me_command_empty_tail_is_a_miss():
    assert no.parse_notify_me_command("notify me:") is None


def test_parse_notify_me_command_unrelated_text_is_none():
    assert no.parse_notify_me_command("totally unrelated text") is None


def test_render_notify_result_never_fabricates_on_error():
    out = no.render_notify_result({"ok": False, "error": "boom"})
    assert "boom" in out


def test_render_notify_result_success():
    out = no.render_notify_result({"ok": True, "error": None})
    assert "sent" in out.lower()


def test_register_alert_push_handler_wires_to_real_event_bus(monkeypatch):
    # Confirms notify_ops actually subscribes to the same PROACTIVE_ALERT
    # event type monitor.run_checks() already publishes to (see
    # monitor.py's run_checks()) -- an end-to-end wiring check, not just
    # the formatting logic in isolation.
    from thursday.events import Event, EventPriority, get_event_bus

    monkeypatch.setenv("NTFY_TOPIC", "topic")
    captured = []

    def _fake_urlopen(req, timeout):
        captured.append(req.headers.get("Title"))
        return _FakeResponse()

    monkeypatch.setattr(no.urllib.request, "urlopen", _fake_urlopen)
    no.register_alert_push_handler()
    try:
        bus = get_event_bus()
        bus.publish(Event(
            event_type="PROACTIVE_ALERT",
            topic="monitor",
            priority=EventPriority.HIGH,
            payload={"severity": "warning", "type": "overdue_invoice", "message": "Invoice #4 overdue"},
            source="monitor",
        ))
        assert captured == ["Thursday: Overdue Invoice"]
    finally:
        no.unregister_alert_push_handler()
