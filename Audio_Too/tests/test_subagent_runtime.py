"""Contract tests for Stage 6 — Subagent Runtime Refactor.

Tests cover:
- SubagentResult construction and properties
- SubagentStatus enum values
- AgentCapability declarations
- SubagentRuntime dispatch (happy path, unknown agent, timeout, error)
- Agent entry point protocol (execute() signature)
- Concurrent dispatch (dispatch_many)
- Context isolation between dispatches
- KENN client in-process path
- Launcher in-process registration
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from thursday.subagent_runtime import (
    AGENT_CAPABILITIES,
    AgentCapability,
    DataScope,
    SubagentResult,
    SubagentRuntime,
    SubagentStatus,
    get_registered_agents,
    register_agent,
    _AGENT_ENTRY_POINTS,
)


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure agent registry is clean before/after each test."""
    saved = dict(_AGENT_ENTRY_POINTS)
    _AGENT_ENTRY_POINTS.clear()
    yield
    _AGENT_ENTRY_POINTS.clear()
    _AGENT_ENTRY_POINTS.update(saved)


def _echo_agent(context: dict, params: list[str]) -> SubagentResult:
    """Dummy agent that echoes params back as output."""
    command = params[0] if params else "unknown"
    output = f"echo: {' '.join(params)}"
    return SubagentResult(
        agent=context.get("agent", "Echo"),
        command=command,
        output=output,
        status=SubagentStatus.SUCCESS,
        exit_code=0,
        metadata={"params": params, "agent_context": context.get("agent")},
    )


def _slow_agent(context: dict, params: list[str]) -> SubagentResult:
    """Agent that sleeps for 5 seconds — used for timeout tests."""
    time.sleep(5)
    return SubagentResult(
        agent="Slow",
        command="sleep",
        output="done",
        status=SubagentStatus.SUCCESS,
    )


def _error_agent(context: dict, params: list[str]) -> SubagentResult:
    """Agent that always raises."""
    msg = " ".join(params[1:]) if len(params) > 1 else "test error"
    raise RuntimeError(msg)


# ═══════════════════════════════════════════════════════════════════════
# 1. SubagentResult
# ═══════════════════════════════════════════════════════════════════════


class TestSubagentResult:
    def test_success_result(self):
        r = SubagentResult(
            agent="Admin",
            command="email",
            output="Email drafted.",
            status=SubagentStatus.SUCCESS,
        )
        assert r.ok is True
        assert r.exit_code == 0
        assert r.agent == "Admin"
        assert r.command == "email"
        assert r.output == "Email drafted."
        assert r.error == ""

    def test_error_result(self):
        r = SubagentResult(
            agent="Admin",
            command="email",
            output="",
            status=SubagentStatus.ERROR,
            exit_code=1,
            error="Something failed.",
        )
        assert r.ok is False
        assert r.exit_code == 1
        assert r.error == "Something failed."

    def test_timeout_result(self):
        r = SubagentResult(
            agent="Slow",
            command="sleep",
            output="",
            status=SubagentStatus.TIMEOUT,
            exit_code=124,
        )
        assert r.ok is False
        assert r.status == SubagentStatus.TIMEOUT

    def test_cancelled_result(self):
        r = SubagentResult(
            agent="Test",
            command="cancel",
            output="",
            status=SubagentStatus.CANCELLED,
            exit_code=130,
        )
        assert r.ok is False
        assert r.status == SubagentStatus.CANCELLED

    def test_frozen(self):
        r = SubagentResult(
            agent="Admin", command="test", output="x", status=SubagentStatus.SUCCESS,
        )
        with pytest.raises(AttributeError):
            r.output = "y"  # type: ignore[misc]

    def test_metadata_default(self):
        r = SubagentResult(
            agent="Admin", command="test", output="", status=SubagentStatus.SUCCESS,
        )
        assert r.metadata == {}

    def test_elapsed_ms(self):
        r = SubagentResult(
            agent="Admin", command="test", output="", status=SubagentStatus.SUCCESS,
            elapsed_ms=42.5,
        )
        assert r.elapsed_ms == 42.5


# ═══════════════════════════════════════════════════════════════════════
# 2. SubagentStatus
# ═══════════════════════════════════════════════════════════════════════


class TestSubagentStatus:
    def test_enum_values(self):
        assert SubagentStatus.SUCCESS.value == "success"
        assert SubagentStatus.ERROR.value == "error"
        assert SubagentStatus.TIMEOUT.value == "timeout"
        assert SubagentStatus.CANCELLED.value == "cancelled"

    def test_all_statuses(self):
        assert len(SubagentStatus) == 4


# ═══════════════════════════════════════════════════════════════════════
# 3. AgentCapability
# ═══════════════════════════════════════════════════════════════════════


class TestAgentCapability:
    def test_default_capability(self):
        cap = AgentCapability()
        assert cap.writes is False
        assert cap.external_send is False
        assert cap.data_scope == DataScope.READ_ONLY
        assert cap.description == ""

    def test_admin_capability(self):
        cap = AGENT_CAPABILITIES["Admin"]
        assert cap.writes is True
        assert cap.external_send is True
        assert cap.data_scope == DataScope.FULL

    def test_marketing_capability(self):
        cap = AGENT_CAPABILITIES["Marketing"]
        assert cap.writes is True
        assert cap.external_send is True

    def test_research_capability(self):
        cap = AGENT_CAPABILITIES["Research"]
        assert cap.writes is False
        assert cap.external_send is False
        assert cap.data_scope == DataScope.READ_ONLY

    def test_all_agents_declared(self):
        for name in ("Admin", "Marketing", "Research"):
            assert name in AGENT_CAPABILITIES


# ═══════════════════════════════════════════════════════════════════════
# 4. Agent registration
# ═══════════════════════════════════════════════════════════════════════


class TestAgentRegistration:
    def test_register_and_retrieve(self):
        register_agent("Echo", _echo_agent)
        agents = get_registered_agents()
        assert "Echo" in agents
        assert agents["Echo"] is _echo_agent

    def test_register_overwrite(self):
        register_agent("Echo", _echo_agent)
        register_agent("Echo", _slow_agent)
        agents = get_registered_agents()
        assert agents["Echo"] is _slow_agent

    def test_snapshot_isolation(self):
        register_agent("Echo", _echo_agent)
        agents = get_registered_agents()
        agents["Fake"] = lambda *_: None  # type: ignore[assignment]
        assert "Fake" not in get_registered_agents()


# ═══════════════════════════════════════════════════════════════════════
# 5. SubagentRuntime — dispatch
# ═══════════════════════════════════════════════════════════════════════


class TestSubagentRuntimeDispatch:
    def setup_method(self):
        register_agent("Echo", _echo_agent)
        register_agent("Slow", _slow_agent)
        register_agent("Error", _error_agent)
        self.runtime = SubagentRuntime(max_workers=4, default_timeout=10.0)

    def teardown_method(self):
        self.runtime.shutdown(wait=False)

    def test_dispatch_success(self):
        result = self.runtime.dispatch("Echo", ["greet", "world"])
        assert result.ok is True
        assert result.agent == "Echo"
        assert result.command == "greet"
        assert "echo: greet world" in result.output
        assert result.elapsed_ms > 0

    def test_dispatch_unknown_agent(self):
        result = self.runtime.dispatch("NoSuchAgent", ["test"])
        assert result.ok is False
        assert result.status == SubagentStatus.ERROR
        assert "not registered" in result.error

    def test_dispatch_timeout(self):
        result = self.runtime.dispatch("Slow", ["sleep"], timeout=0.1)
        assert result.ok is False
        assert result.status == SubagentStatus.TIMEOUT
        assert result.exit_code == 124
        assert "timed out" in result.error.lower()

    def test_dispatch_exception(self):
        result = self.runtime.dispatch("Error", ["crash", "boom!"])
        assert result.ok is False
        assert result.status == SubagentStatus.ERROR
        assert "boom!" in result.error

    def test_dispatch_empty_params(self):
        result = self.runtime.dispatch("Echo", [])
        assert result.ok is True
        assert result.command == "unknown"

    def test_dispatch_elapsed_positive(self):
        result = self.runtime.dispatch("Echo", ["test"])
        assert result.elapsed_ms > 0

    def test_dispatch_preserves_metadata(self):
        result = self.runtime.dispatch("Echo", ["meta", "test"])
        assert result.metadata.get("params") == ["meta", "test"]


# ═══════════════════════════════════════════════════════════════════════
# 6. Context isolation
# ═══════════════════════════════════════════════════════════════════════


class TestContextIsolation:
    def setup_method(self):
        self.contexts = []

        def _capture_agent(context: dict, params: list[str]) -> SubagentResult:
            self.contexts.append(dict(context))
            return SubagentResult(
                agent=context["agent"],
                command="capture",
                output=str(context["agent"]),
                status=SubagentStatus.SUCCESS,
            )

        register_agent("CaptureA", _capture_agent)
        register_agent("CaptureB", _capture_agent)
        self.runtime = SubagentRuntime(max_workers=2, default_timeout=10.0)

    def teardown_method(self):
        self.runtime.shutdown(wait=False)

    def test_contexts_are_isolated(self):
        self.runtime.dispatch("CaptureA", ["test"])
        self.runtime.dispatch("CaptureB", ["test"])
        assert len(self.contexts) == 2
        assert self.contexts[0]["agent"] == "CaptureA"
        assert self.contexts[1]["agent"] == "CaptureB"

    def test_context_has_repo_root(self):
        self.runtime.dispatch("CaptureA", ["test"])
        ctx = self.contexts[0]
        assert "repo_root" in ctx
        assert "cwd" in ctx
        assert "env" in ctx


# ═══════════════════════════════════════════════════════════════════════
# 7. dispatch_many — concurrent dispatch
# ═══════════════════════════════════════════════════════════════════════


class TestDispatchMany:
    def setup_method(self):
        register_agent("Echo", _echo_agent)
        register_agent("Error", _error_agent)
        self.runtime = SubagentRuntime(max_workers=4, default_timeout=10.0)

    def teardown_method(self):
        self.runtime.shutdown(wait=False)

    def test_dispatch_many_all_success(self):
        tasks = [
            ("Echo", ["task1"]),
            ("Echo", ["task2"]),
            ("Echo", ["task3"]),
        ]
        results = self.runtime.dispatch_many(tasks)
        assert len(results) == 3
        assert all(r.ok for r in results)
        assert "task1" in results[0].output
        assert "task2" in results[1].output
        assert "task3" in results[2].output

    def test_dispatch_many_mixed(self):
        tasks = [
            ("Echo", ["good"]),
            ("Error", ["crash", "bad"]),
            ("NoSuch", ["test"]),
        ]
        results = self.runtime.dispatch_many(tasks)
        assert len(results) == 3
        assert results[0].ok is True
        assert results[1].ok is False
        # NoSuch returns an error from the error lambda
        assert results[2].ok is False

    def test_concurrent_no_corruption(self):
        """10 concurrent echo tasks should all complete without corruption."""
        tasks = [("Echo", [f"task{i}"]) for i in range(10)]
        results = self.runtime.dispatch_many(tasks)
        assert len(results) == 10
        assert all(r.ok for r in results)
        outputs = {r.output for r in results}
        assert len(outputs) == 10  # All unique


# ═══════════════════════════════════════════════════════════════════════
# 8. Runtime properties
# ═══════════════════════════════════════════════════════════════════════


class TestRuntimeProperties:
    def test_max_workers(self):
        runtime = SubagentRuntime(max_workers=8)
        assert runtime.max_workers == 8
        runtime.shutdown(wait=False)

    def test_active_count_zero(self):
        runtime = SubagentRuntime(max_workers=2)
        assert runtime.active_count == 0
        runtime.shutdown(wait=False)


# ═══════════════════════════════════════════════════════════════════════
# 9. KENN Client (in-process path)
# ═══════════════════════════════════════════════════════════════════════


class TestKENNClient:
    def test_ask_kenn_import_failure(self):
        """When KENN module not importable, returns a clear error."""
        from server.agents.Shared.kenn_client import ask_kenn

        # Without KENN_SUBPROCESS_FALLBACK, should return a descriptive message
        with patch.dict("os.environ", {"KENN_SUBPROCESS_FALLBACK": "0"}, clear=False):
            result = ask_kenn("What is sidechain compression?")
        # Should not crash; should return a string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_disabled(self):
        """When KENN_LM_ENABLED=0, returns None."""
        from server.agents.Shared.kenn_client import generate_agent_response

        with patch.dict("os.environ", {"KENN_LM_ENABLED": "0"}, clear=False):
            result = generate_agent_response("Admin", "task", "rule", "template")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# 10. DataScope enum
# ═══════════════════════════════════════════════════════════════════════


class TestDataScope:
    def test_enum_values(self):
        assert DataScope.READ_ONLY.value == "read_only"
        assert DataScope.LOCAL_MUTATION.value == "local_mutation"
        assert DataScope.FULL.value == "full"

    def test_all_scopes(self):
        assert len(DataScope) == 3
