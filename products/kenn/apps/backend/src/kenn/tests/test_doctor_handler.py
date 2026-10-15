"""The session doctor's audit route answers even when it finds something."""

from __future__ import annotations

import pytest

from kenn.routes import doctor_handler


class _Handler:
    def send_json(self, status, body) -> None:
        self.status, self.body = status, body


def test_an_audit_that_finds_issues_is_not_a_server_error(monkeypatch) -> None:
    # 26 Sept 2026: every audit with an issue read masking-only fields off the doctor's Issue and returned 500.
    from kenn import mixing_doctor

    hot = {"status": "connected", "tracks": [
        {"index": 0, "name": "Lead Vocal", "volume": 0.95, "pan": 0.0, "muted": False, "soloed": False, "devices": []},
        {"index": 1, "name": "Bass", "volume": 0.5, "pan": 0.0, "muted": False, "soloed": False, "devices": []}]}
    monkeypatch.setattr(mixing_doctor, "get_latest_session_state", lambda: hot)
    handler = _Handler()
    doctor_handler.handle_get_doctor_audit(handler)
    assert handler.status == 200 and handler.body["issues_found"] >= 1
    assert "conflict_track_name" not in handler.body["issues"][0]

    doctor_handler.handle_post_doctor_audit(handler, {"session_state": hot})
    assert handler.status == 200 and handler.body["issues_found"] >= 1


def test_handle_project_manager_report_success(monkeypatch) -> None:
    from kenn import mixing_doctor
    from kenn import project_analysis

    fake_session = {"status": "connected", "tracks": [{"name": "Lead Vocal"}]}
    monkeypatch.setattr(mixing_doctor, "get_latest_session_state", lambda: fake_session)
    monkeypatch.setattr(
        project_analysis,
        "project_manager_report",
        lambda state: {"schema": "kenn.project_manager_report.v1", "state": state},
    )

    code, body = doctor_handler.handle_project_manager_report()
    assert code == 200
    assert body["schema"] == "kenn.project_manager_report.v1"
    assert body["state"] == fake_session


def test_handle_project_health_report_success(monkeypatch) -> None:
    from kenn import mixing_doctor
    from kenn import project_analysis

    fake_session = {"status": "connected", "tracks": []}
    monkeypatch.setattr(mixing_doctor, "get_latest_session_state", lambda: fake_session)
    monkeypatch.setattr(
        project_analysis,
        "project_health_report",
        lambda state: {"schema": "kenn.project_health_report.v1", "health": "good"},
    )

    code, body = doctor_handler.handle_project_health_report()
    assert code == 200
    assert body["health"] == "good"


@pytest.mark.parametrize("rms,active", [(-100.0, False), (-80.0, False), (-79.9, True)])
@pytest.mark.parametrize("method", ["get", "post"])
def test_doctor_routes_withhold_quiet_meter_findings_and_keep_structural_advice(monkeypatch, rms, active, method) -> None:
    # Both cached and caller-supplied meter paths used to promote quiet peak/phase values into findings.
    from kenn import mixing_doctor, plugin_handoff

    state = {"status": "connected", "tracks": [{"index": 0, "name": "Lead", "volume": 0.95, "devices": []}]}
    meters = {"rms_dbfs": rms, "peak_dbfs": -0.1, "stereo_correlation": -0.9}
    monkeypatch.setattr(mixing_doctor, "get_latest_session_state", lambda: state)
    monkeypatch.setattr(plugin_handoff, "live_context_summary", lambda session_id: meters)
    handler = _Handler()
    if method == "get":
        doctor_handler.handle_get_doctor_audit(handler)
    else:
        doctor_handler.handle_post_doctor_audit(handler, {"session_state": state, "meters": meters})

    assert handler.status == 200 and handler.body["ok"]
    codes = {item["code"] for item in handler.body["issues"]}
    assert "HEADROOM_CLIPPING_RISK" in codes
    assert ("CAPTURE_SAMPLE_PEAK_RISK" in codes) is active
    assert ("CAPTURE_NEGATIVE_CORRELATION" in codes) is active
    assert handler.body["remediation_batch"]


@pytest.mark.parametrize("method", ["get", "post"])
def test_active_capture_findings_keep_insert_scope_and_do_not_claim_master_or_true_peak(monkeypatch, method) -> None:
    from kenn import mixing_doctor, plugin_handoff

    # A host label can say "Master", but this payload still measures one KENN insert, not the rendered master.
    state = {"status": "connected", "tracks": [
        {"index": 0, "name": "Master", "volume": 0.8, "devices": []},
        {"index": 1, "name": "Music", "volume": 0.8, "devices": []},
    ]}
    meters = {
        "scope": "plugin_bus",
        "host_track_name": "Master",
        "rms_dbfs": -18.0,
        "peak_dbfs": -0.1,
        "stereo_correlation": -0.9,
    }
    monkeypatch.setattr(mixing_doctor, "get_latest_session_state", lambda: state)
    monkeypatch.setattr(plugin_handoff, "live_context_summary", lambda session_id: meters)
    handler = _Handler()
    if method == "get":
        doctor_handler.handle_get_doctor_audit(handler)
    else:
        doctor_handler.handle_post_doctor_audit(handler, {"session_state": state, "meters": meters})

    assert handler.status == 200 and handler.body["ok"]
    findings = {item["code"]: item for item in handler.body["issues"]}
    peak = findings["CAPTURE_SAMPLE_PEAK_RISK"]
    correlation = findings["CAPTURE_NEGATIVE_CORRELATION"]
    for item in (peak, correlation):
        assert item["track_index"] == -1 and item["track_name"] == "Captured insert"
        assert item["severity"] == "advisory" and item["proposed_value"] is None
    assert "sample peak" in peak["description"].lower()
    assert "-0.1 dBFS" in peak["description"]
    assert "does not measure true peak" in peak["description"].lower()
    assert "or establish master-bus clipping" in peak["description"].lower()
    assert not any(term in peak["description"].lower() for term in ("master bus peak", "inter-sample", "dac"))
    assert not any(term in peak["suggested_action"].lower() for term in ("master", "track level", "limiter ceiling"))
    assert "audition this capture in mono" in correlation["suggested_action"].lower()
    assert not any(term in correlation["description"].lower() for term in ("master", "severe", "sub bass", "120 hz"))
    assert handler.body["remediation_batch"] == []
