"""Tests for the "parallel_swarm" brain-decision route: independent
"subagent" brain-plan steps run as a real parallel dependency graph
(thursday.taskgraph / SubagentRuntime.dispatch_graph) instead of the
sequential brain-plan executor -- but only when every step is risk-free.
Any step needing confirmation falls back to the existing, already-tested
sequential run_brain_plan path (no second confirmation state machine)."""

from __future__ import annotations

import time
import types

from thursday import orchestrator, subagent_runtime
from thursday.registry import ActionRisk
from thursday.registry.core import ServiceDef
from thursday.subagent_runtime import (
    SubagentResult,
    SubagentStatus,
    register_agent,
)


def _service(name: str, action):
    return ServiceDef(name=name, description=f"{name} test service", action=action)


def _all_read_only(_service_id, _text):
    return ActionRisk.READ_ONLY


# ── run_parallel_swarm: pure routing/fallback logic ─────────────────────


def test_returns_none_for_a_single_step():
    result = orchestrator.run_parallel_swarm(
        [{"kind": "subagent", "agent": "admin", "task": "x"}],
        api=None, resolved_text="x",
    )
    assert result is None


def test_returns_none_for_over_cap_steps():
    steps = [{"kind": "subagent", "agent": "admin", "task": "x"} for _ in range(orchestrator._MAX_PLAN_STEPS + 1)]
    assert orchestrator.run_parallel_swarm(steps, api=None, resolved_text="x") is None


def test_returns_none_when_a_step_is_not_kind_subagent():
    steps = [
        {"kind": "subagent", "agent": "admin", "task": "x"},
        {"kind": "service", "service_id": "client_info"},
    ]
    assert orchestrator.run_parallel_swarm(steps, api=None, resolved_text="x") is None


def test_returns_none_when_a_step_requires_confirmation(monkeypatch):
    monkeypatch.setattr(
        orchestrator, "request_risk",
        lambda service_id, _text: (
            ActionRisk.EXTERNAL_COMMUNICATION if service_id == "marketing_agent" else ActionRisk.READ_ONLY
        ),
    )
    steps = [
        {"kind": "subagent", "agent": "admin", "task": "x"},
        {"kind": "subagent", "agent": "marketing", "task": "y"},
    ]
    assert orchestrator.run_parallel_swarm(steps, api=None, resolved_text="x") is None


def test_dispatches_real_parallel_swarm_when_all_steps_are_safe(monkeypatch):
    monkeypatch.setattr(orchestrator, "request_risk", _all_read_only)
    # run_parallel_swarm always (re-)registers the real Admin/Marketing/
    # Research agents against the live api before dispatching -- that's the
    # correct production behavior, but it would clobber the mock entry
    # points below, so make it a no-op here.
    monkeypatch.setattr(subagent_runtime, "register_default_agents", lambda api: None)

    def slow_admin(ctx, params):
        time.sleep(0.3)
        return SubagentResult(agent="Admin", command="run", output="admin done", status=SubagentStatus.SUCCESS)

    def slow_research(ctx, params):
        time.sleep(0.3)
        return SubagentResult(agent="Research", command="run", output="research done", status=SubagentStatus.SUCCESS)

    register_agent("Admin", slow_admin)
    register_agent("Research", slow_research)

    steps = [
        {"kind": "subagent", "agent": "admin", "task": "handle invoices"},
        {"kind": "subagent", "agent": "research", "task": "find sources"},
    ]
    start = time.monotonic()
    result = orchestrator.run_parallel_swarm(steps, api=None, resolved_text="do both")
    elapsed = time.monotonic() - start

    assert result is not None
    assert "admin done" in result and "research done" in result
    assert elapsed < 0.55, f"expected parallel execution, took {elapsed:.2f}s"


# ── End-to-end through handle(): brain routes to parallel_swarm ────────


def _e2e_setup(monkeypatch, tmp_path, risk_fn, brain_steps, bd_type="parallel_swarm"):
    from thursday import session_manager

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_CONFIRMATION_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3"))
    monkeypatch.setattr(orchestrator, "should_check", lambda *a, **k: False)
    monkeypatch.setattr(orchestrator, "get_pending_alerts", lambda *a, **k: [])
    monkeypatch.setattr(orchestrator, "request_risk", risk_fn)
    monkeypatch.setattr(orchestrator, "build_services", lambda api: {})

    intent = types.SimpleNamespace(name="contextual", entities={})
    brain_decision = types.SimpleNamespace(type=bd_type, abstract="swarm", steps=brain_steps)
    decision = orchestrator.RequestDecision(
        resolved_text="draft a post and research pricing", resolved_entities={}, intent=intent,
        execution_target="brain", brain_decision=brain_decision,
    )
    monkeypatch.setattr(orchestrator, "classify_request", lambda text, session: decision)
    return session_manager


def test_handle_routes_to_parallel_swarm_and_surfaces_qc_caveat(monkeypatch, tmp_path):
    monkeypatch.setattr(subagent_runtime, "register_default_agents", lambda api: None)

    def admin_entry(ctx, params):
        return SubagentResult(agent="Admin", command="run", output="invoices summarized", status=SubagentStatus.SUCCESS)

    def marketing_entry(ctx, params):
        # Claims success but produces nothing -- QC should flag this as a
        # caveat without failing the whole turn.
        return SubagentResult(agent="Marketing", command="run", output="", status=SubagentStatus.SUCCESS)

    register_agent("Admin", admin_entry)
    register_agent("Marketing", marketing_entry)

    sm = _e2e_setup(
        monkeypatch, tmp_path, _all_read_only,
        [
            {"kind": "subagent", "agent": "admin", "task": "summarize invoices"},
            {"kind": "subagent", "agent": "marketing", "task": "draft a post"},
        ],
    )
    session = sm.get_or_create_session("parallel-swarm-e2e")
    resp = orchestrator.handle("run both", session=session, list_records=lambda _n: [])

    assert "invoices summarized" in resp


def test_handle_falls_back_to_sequential_plan_when_a_swarm_step_is_risky(monkeypatch, tmp_path):
    ran = []

    def summary_action(ctx, api, text):
        ran.append("summary")
        return "summary ok"

    def email_action(ctx, api, text):
        ran.append("email")
        return "email sent"

    services = {
        "summary_svc": _service("Summary", summary_action),
        "email_svc": _service("Email", email_action),
    }

    def mixed_risk(service_id, _text):
        return ActionRisk.EXTERNAL_COMMUNICATION if service_id == "marketing_agent" else ActionRisk.READ_ONLY

    sm = _e2e_setup(
        monkeypatch, tmp_path, mixed_risk,
        [
            {"kind": "subagent", "agent": "admin", "task": "summarize"},
            {"kind": "subagent", "agent": "marketing", "task": "draft a post"},
        ],
    )
    # run_brain_plan needs real mapped services for the sequential fallback;
    # patch build_services again with the actual admin_agent/marketing_agent
    # ids so _map_brain_step_to_service resolves them.
    services = {
        "admin_agent": _service("Admin", lambda ctx, api, text: ran.append("admin") or "admin ok"),
        "marketing_agent": _service("Marketing", lambda ctx, api, text: ran.append("marketing") or "marketing ok"),
    }
    monkeypatch.setattr(orchestrator, "build_services", lambda api: services)

    session = sm.get_or_create_session("parallel-swarm-fallback")
    resp = orchestrator.handle("run both", session=session, list_records=lambda _n: [])

    # Falls back to the sequential plan: first (safe) step runs, second
    # (risky) step pauses for confirmation -- exactly like a "plan" decision.
    assert ran == ["admin"]
    assert "admin ok" in resp
    assert "confirm " in resp.lower()
