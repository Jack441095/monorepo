"""Tests for Thursday Phase 4: Dynamic Multi-Agent Swarm & Task Mesh."""



from thursday.subagent_runtime import (
    AgentArtifact,
    SubagentResult,
    SubagentStatus,
    SubagentRuntime,
    SwarmResult,
    register_agent,
)


def test_agent_artifact_creation():
    art = AgentArtifact(source_agent="Research", content="Found 3 vocal compression papers", artifact_type="data")
    assert art.source_agent == "Research"
    assert art.content == "Found 3 vocal compression papers"
    assert art.artifact_type == "data"
    assert len(art.artifact_id) == 12


def test_dispatch_swarm_success():
    def mock_research_entry(ctx, params):
        return SubagentResult(agent="SwarmResearch", command="research", output="Research completed: 2 sources found.", status=SubagentStatus.SUCCESS)

    def mock_admin_entry(ctx, params):
        # Verify upstream artifact context was passed
        upstream = ctx.get("_upstream_artifacts", [])
        assert len(upstream) == 1
        assert upstream[0]["source_agent"] == "SwarmResearch"
        return SubagentResult(agent="SwarmAdmin", command="draft", output="Draft invoice created.", status=SubagentStatus.SUCCESS)

    register_agent("SwarmResearch", mock_research_entry)
    register_agent("SwarmAdmin", mock_admin_entry)

    runtime = SubagentRuntime()
    swarm_chain = [
        {"agent": "SwarmResearch", "params": ["task1"]},
        {"agent": "SwarmAdmin", "params": ["task2"]},
    ]

    result = runtime.dispatch_swarm(swarm_chain)

    assert isinstance(result, SwarmResult)
    assert result.ok is True
    assert len(result.agent_results) == 2
    assert len(result.produced_artifacts) == 2
    assert "[SwarmResearch]" in result.final_summary
    assert "[SwarmAdmin]" in result.final_summary


def test_dispatch_swarm_partial_failure():
    def mock_success_entry(ctx, params):
        return SubagentResult(agent="SwarmSuccess", command="step1", output="Step 1 OK", status=SubagentStatus.SUCCESS)

    def mock_fail_entry(ctx, params):
        return SubagentResult(agent="SwarmFail", command="step2", output="", status=SubagentStatus.ERROR, error="Failed step 2")

    register_agent("SwarmSuccess", mock_success_entry)
    register_agent("SwarmFail", mock_fail_entry)

    runtime = SubagentRuntime()
    swarm_chain = [
        {"agent": "SwarmSuccess", "params": ["task1"]},
        {"agent": "SwarmFail", "params": ["task2"]},
    ]

    result = runtime.dispatch_swarm(swarm_chain)

    assert result.ok is False
    assert len(result.agent_results) == 2
    assert len(result.produced_artifacts) == 1
    assert result.produced_artifacts[0].source_agent == "SwarmSuccess"
