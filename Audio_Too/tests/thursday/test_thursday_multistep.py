"""Multi-step brain-plan execution + pause/resume
(docs/THURSDAY_KENN_AGENT_PLAN_2026-07-20.md, Slices 1 & 1b).

Thursday's brain can plan an N-step sequence; the orchestrator historically ran
only steps[0]. Now it runs the whole plan: safe (non-confirmation) steps run in
order, threading each result into the next; the first confirmation-requiring
step PAUSES the plan and, on `confirm <token>`, the plan resumes -- running the
just-confirmed step then continuing, pausing again at the next risky step.

The one safety invariant, enforced below: a confirmation-requiring step is
executed only when it is the explicitly-confirmed step on resume. Every other
risky step pauses. No unconfirmed mutation is possible, even across a resume.
"""

from __future__ import annotations

import types


from thursday import orchestrator
from thursday.registry import ActionRisk
from thursday.registry.core import ServiceDef


def _service(name: str, action):
    """A real ServiceDef so both the multi-step path (.name/.action) and the
    single-step fallback path (.requires_context/.post_process/...) work."""
    return ServiceDef(name=name, description=f"{name} test service", action=action)


def _all_read_only(_service_id, _text):
    return ActionRisk.READ_ONLY


# ── _map_brain_step_to_service ────────────────────────────────────────────


def test_map_service_step():
    assert orchestrator._map_brain_step_to_service(
        {"kind": "service", "service_id": "client_info"}, {"client_info": object()}
    ) == "client_info"


def test_map_unknown_service_returns_none():
    assert orchestrator._map_brain_step_to_service(
        {"kind": "service", "service_id": "nope"}, {}
    ) is None


def test_map_subagent_step():
    assert orchestrator._map_brain_step_to_service({"kind": "subagent", "agent": "research"}, {}) == "research_agent"


def test_map_malformed_step_returns_none():
    assert orchestrator._map_brain_step_to_service(None, {}) is None
    assert orchestrator._map_brain_step_to_service({"kind": "mystery"}, {}) is None


# ── StepResult (Slice 2 typed results) ────────────────────────────────────


def test_stepresult_round_trips_through_dict():
    r = orchestrator.StepResult("svc", "Svc", "hello", ok=True)
    assert orchestrator.StepResult.from_dict(r.to_dict()) == r


def test_stepresult_from_dict_tolerates_legacy_and_missing_fields():
    # Legacy persisted shape used "result"; missing ok defaults True.
    r = orchestrator.StepResult.from_dict({"service_id": "s", "result": "out"})
    assert r.output == "out" and r.service_name == "s" and r.ok is True


# ── _execute_plan_from: pure execution/pause logic ────────────────────────


def _exec(mapped, services, *, start=0, preconfirmed=False, prior=None, risk=None, text="x"):
    return orchestrator._execute_plan_from(
        mapped, start,
        first_is_preconfirmed=preconfirmed,
        prior_results=prior or [],
        services=services, api=None, handler_ctx={}, resolved_text=text,
    )


def test_all_safe_steps_complete_in_order(monkeypatch):
    monkeypatch.setattr(orchestrator, "request_risk", _all_read_only)
    order = []
    services = {
        "a": _service("A", lambda ctx, api, text: order.append("a") or "ra"),
        "b": _service("B", lambda ctx, api, text: order.append("b") or "rb"),
    }
    outcome = _exec(["a", "b"], services)
    assert outcome["status"] == "completed"
    assert order == ["a", "b"]
    assert [r.output for r in outcome["results"]] == ["ra", "rb"]


def test_pauses_at_first_risky_step_without_running_it(monkeypatch):
    """SAFETY: safe steps before a risky one run; the risky one does NOT."""
    ran = []

    def risk(service_id, _text):
        return ActionRisk.EXTERNAL_COMMUNICATION if service_id == "email" else ActionRisk.READ_ONLY

    monkeypatch.setattr(orchestrator, "request_risk", risk)
    services = {
        "look": _service("Look", lambda ctx, api, text: ran.append("look") or "info"),
        "email": _service("Email", lambda ctx, api, text: ran.append("email") or "SENT"),
        "after": _service("After", lambda ctx, api, text: ran.append("after") or "later"),
    }
    outcome = _exec(["look", "email", "after"], services)
    assert outcome["status"] == "paused"
    assert outcome["pause_service_id"] == "email"
    assert outcome["pause_index"] == 1
    assert ran == ["look"]  # safe step ran; risky 'email' and everything after did NOT


def test_preconfirmed_first_step_runs_even_if_risky(monkeypatch):
    """On resume, the explicitly-confirmed (first) step runs pre-approved."""
    ran = []

    def risk(service_id, _text):
        return ActionRisk.EXTERNAL_COMMUNICATION if service_id == "email" else ActionRisk.READ_ONLY

    monkeypatch.setattr(orchestrator, "request_risk", risk)
    services = {
        "email": _service("Email", lambda ctx, api, text: ran.append("email") or "SENT"),
        "after": _service("After", lambda ctx, api, text: ran.append("after") or "later"),
    }
    outcome = _exec(["email", "after"], services, preconfirmed=True)
    assert outcome["status"] == "completed"
    assert ran == ["email", "after"]  # confirmed email ran, then safe 'after'


def test_preconfirmed_does_not_extend_to_a_second_risky_step(monkeypatch):
    """SAFETY: the pre-approval applies ONLY to the first (confirmed) step. A
    second risky step still pauses."""
    ran = []

    def risk(service_id, _text):
        return ActionRisk.LOCAL_MUTATION if service_id.startswith("write") else ActionRisk.READ_ONLY

    monkeypatch.setattr(orchestrator, "request_risk", risk)
    services = {
        "write1": _service("Write1", lambda ctx, api, text: ran.append("write1") or "w1"),
        "write2": _service("Write2", lambda ctx, api, text: ran.append("write2") or "w2"),
    }
    outcome = _exec(["write1", "write2"], services, preconfirmed=True)
    assert outcome["status"] == "paused"
    assert outcome["pause_service_id"] == "write2"
    assert ran == ["write1"]  # confirmed write1 ran; write2 paused, not executed


def test_prior_results_threaded_into_later_steps(monkeypatch):
    monkeypatch.setattr(orchestrator, "request_risk", _all_read_only)
    seen = {}
    services = {
        "a": _service("A", lambda ctx, api, text: "alpha"),
        "b": _service("B", lambda ctx, api, text: seen.setdefault("b", ctx.get("_prior_step_results")) or "beta"),
    }
    _exec(["a", "b"], services)
    assert seen["b"] == [{"service_id": "a", "service_name": "A", "output": "alpha", "ok": True}]


def test_step_error_stops_with_honest_report(monkeypatch):
    monkeypatch.setattr(orchestrator, "request_risk", _all_read_only)
    ran = []

    def boom(ctx, api, text):
        raise RuntimeError("kaboom")

    services = {
        "a": _service("A", lambda ctx, api, text: ran.append("a") or "ra"),
        "b": _service("B", boom),
        "c": _service("C", lambda ctx, api, text: ran.append("c") or "rc"),
    }
    outcome = _exec(["a", "b", "c"], services)
    assert outcome["status"] == "completed"  # stopped, not raised
    assert ran == ["a"]  # c never ran (fail-closed)
    assert outcome["results"][-1].ok is False
    assert "failed" in outcome["results"][-1].output.lower()


# ── run_brain_plan: fallback conditions ───────────────────────────────────


def test_single_step_plan_falls_back(monkeypatch):
    monkeypatch.setattr(orchestrator, "request_risk", _all_read_only)
    services = {"a": _service("A", lambda ctx, api, text: "ra")}
    assert orchestrator.run_brain_plan(
        [{"kind": "service", "service_id": "a"}],
        session={"session_id": "s", "context": {}}, services=services, api=None,
        handler_ctx={}, resolved_text="x",
    ) is None


def test_unmappable_and_overcap_plans_fall_back(monkeypatch):
    monkeypatch.setattr(orchestrator, "request_risk", _all_read_only)
    services = {"a": _service("A", lambda ctx, api, text: "ra")}
    assert orchestrator.run_brain_plan(
        [{"kind": "service", "service_id": "a"}, {"kind": "service", "service_id": "ghost"}],
        session={"session_id": "s", "context": {}}, services=services, api=None,
        handler_ctx={}, resolved_text="x",
    ) is None
    big = {f"s{i}": _service(f"S{i}", lambda ctx, api, text: "r") for i in range(orchestrator._MAX_PLAN_STEPS + 1)}
    steps = [{"kind": "service", "service_id": f"s{i}"} for i in range(orchestrator._MAX_PLAN_STEPS + 1)]
    assert orchestrator.run_brain_plan(
        steps, session={"session_id": "s", "context": {}}, services=big, api=None,
        handler_ctx={}, resolved_text="x",
    ) is None


# ── End-to-end through handle(): the full pause/resume flow ────────────────


def _e2e_setup(monkeypatch, tmp_path, services, brain_steps, risk_fn):
    from thursday import session_manager

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_CONFIRMATION_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3"))
    monkeypatch.setattr(orchestrator, "should_check", lambda *a, **k: False)
    monkeypatch.setattr(orchestrator, "get_pending_alerts", lambda *a, **k: [])
    monkeypatch.setattr(orchestrator, "request_risk", risk_fn)
    monkeypatch.setattr(orchestrator, "build_services", lambda api: services)

    intent = types.SimpleNamespace(name="contextual", entities={})
    brain_decision = types.SimpleNamespace(type="plan", abstract="plan", steps=brain_steps)
    decision = orchestrator.RequestDecision(
        resolved_text="do the plan", resolved_entities={}, intent=intent,
        execution_target="brain", brain_decision=brain_decision,
    )
    monkeypatch.setattr(orchestrator, "classify_request", lambda text, session: decision)
    return session_manager


def test_handle_runs_all_safe_plan(monkeypatch, tmp_path):
    ran = []
    services = {
        "a": _service("A", lambda ctx, api, text: ran.append("a") or "ra"),
        "b": _service("B", lambda ctx, api, text: ran.append("b") or "rb"),
    }
    sm = _e2e_setup(monkeypatch, tmp_path, services,
                    [{"kind": "service", "service_id": "a"}, {"kind": "service", "service_id": "b"}],
                    _all_read_only)
    session = sm.get_or_create_session("all-safe")
    resp = orchestrator.handle("do the plan", session=session, list_records=lambda _n: [])
    assert ran == ["a", "b"]
    assert "ra" in resp and "rb" in resp


def _mixed_risk(service_id, _text):
    return ActionRisk.EXTERNAL_COMMUNICATION if service_id == "email" else ActionRisk.READ_ONLY


def test_handle_pauses_at_risky_step_then_resumes_on_confirm(monkeypatch, tmp_path):
    ran = []
    services = {
        "summary": _service("Summary", lambda ctx, api, text: ran.append("summary") or "Jordan owes 500"),
        "email": _service("Email", lambda ctx, api, text: ran.append("email") or "email sent"),
        "log": _service("Log", lambda ctx, api, text: ran.append("log") or "logged"),
    }
    sm = _e2e_setup(monkeypatch, tmp_path, services, [
        {"kind": "service", "service_id": "summary"},
        {"kind": "service", "service_id": "email"},
        {"kind": "service", "service_id": "log"},
    ], _mixed_risk)
    session = sm.get_or_create_session("pause-resume")

    # Turn 1: safe 'summary' runs, pause at 'email' (not run), 'log' not run yet.
    resp1 = orchestrator.handle("do the plan", session=session, list_records=lambda _n: [])
    assert ran == ["summary"]
    assert "Jordan owes 500" in resp1
    assert "confirm " in resp1.lower()

    token = resp1.split("confirm ")[1].split()[0].rstrip(".")

    # Turn 2: confirm -> 'email' runs (pre-approved) AND 'log' continues.
    resp2 = orchestrator.handle(f"confirm {token}", session=session, list_records=lambda _n: [])
    assert ran == ["summary", "email", "log"]
    assert "email sent" in resp2 and "logged" in resp2


def test_handle_confirming_first_risky_step_does_not_run_a_second_risky_step(monkeypatch, tmp_path):
    """SAFETY across resume: a plan [safe, risky1, risky2] confirmed once runs
    only risky1, then pauses again at risky2 -- never auto-runs risky2."""
    ran = []

    def risk(service_id, _text):
        return ActionRisk.LOCAL_MUTATION if service_id in ("write1", "write2") else ActionRisk.READ_ONLY

    services = {
        "read": _service("Read", lambda ctx, api, text: ran.append("read") or "info"),
        "write1": _service("Write1", lambda ctx, api, text: ran.append("write1") or "wrote 1"),
        "write2": _service("Write2", lambda ctx, api, text: ran.append("write2") or "wrote 2"),
    }
    sm = _e2e_setup(monkeypatch, tmp_path, services, [
        {"kind": "service", "service_id": "read"},
        {"kind": "service", "service_id": "write1"},
        {"kind": "service", "service_id": "write2"},
    ], risk)
    session = sm.get_or_create_session("double-risky")

    resp1 = orchestrator.handle("do the plan", session=session, list_records=lambda _n: [])
    assert ran == ["read"]
    token1 = resp1.split("confirm ")[1].split()[0].rstrip(".")

    resp2 = orchestrator.handle(f"confirm {token1}", session=session, list_records=lambda _n: [])
    assert ran == ["read", "write1"]  # write1 ran (confirmed); write2 did NOT
    assert "confirm " in resp2.lower()  # paused again at write2
    token2 = resp2.split("confirm ")[1].split()[0].rstrip(".")
    assert token2 != token1

    orchestrator.handle(f"confirm {token2}", session=session, list_records=lambda _n: [])
    assert ran == ["read", "write1", "write2"]  # only now, with its own confirm


def test_handle_confirming_a_plan_step_twice_runs_it_once(monkeypatch, tmp_path):
    """Receipt guard: replaying the same confirmation does not re-run the step."""
    ran = []
    services = {
        "summary": _service("Summary", lambda ctx, api, text: ran.append("summary") or "s"),
        "email": _service("Email", lambda ctx, api, text: ran.append("email") or "email sent"),
    }
    sm = _e2e_setup(monkeypatch, tmp_path, services, [
        {"kind": "service", "service_id": "summary"},
        {"kind": "service", "service_id": "email"},
    ], _mixed_risk)
    session = sm.get_or_create_session("replay")

    resp1 = orchestrator.handle("do the plan", session=session, list_records=lambda _n: [])
    token = resp1.split("confirm ")[1].split()[0].rstrip(".")
    orchestrator.handle(f"confirm {token}", session=session, list_records=lambda _n: [])
    orchestrator.handle(f"confirm {token}", session=session, list_records=lambda _n: [])
    assert ran.count("email") == 1  # the external step ran exactly once
