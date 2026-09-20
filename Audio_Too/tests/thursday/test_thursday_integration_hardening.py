import os
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from thursday.brain import looks_like_audio_engineering_question
from thursday.orchestrator import classify_request
from thursday.subagent_runtime import SubagentRuntime, SubagentResult, SubagentStatus, register_agent


def test_looks_like_audio_engineering_question():
    # Audio queries
    assert looks_like_audio_engineering_question("How do I EQ my vocals?")
    assert looks_like_audio_engineering_question("What compression settings should I use?")
    assert looks_like_audio_engineering_question("Tell me about lufs and mastering")
    assert looks_like_audio_engineering_question("My mix is clipping in Ableton")
    
    # Non-audio queries
    assert not looks_like_audio_engineering_question("Who is Jordan?")
    assert not looks_like_audio_engineering_question("Show my invoices please")
    assert not looks_like_audio_engineering_question("What is the capital of Italy?")


def test_classify_request_intercepts_audio_questions():
    session = {"turns": [], "context": {}}
    
    # Audio question should be intercepted to production_qa / kenn_stream
    decision = classify_request("how do I EQ my mix?", session)
    assert decision.intent.name == "production_qa"
    assert decision.execution_target == "kenn_stream"


def test_subagent_runtime_writes_trace(tmp_path, monkeypatch):
    # Set custom THURSDAY_ANALYTICS_DIR to tmp_path
    monkeypatch.setenv("THURSDAY_ANALYTICS_DIR", str(tmp_path))
    
    # Register mock agent
    def fake_entry(ctx, params):
        return SubagentResult(
            agent="MockAgent",
            command="test_command",
            output="Mock agent output content",
            status=SubagentStatus.SUCCESS,
            exit_code=0
        )
    
    register_agent("MockAgent", fake_entry)
    
    runtime = SubagentRuntime(repo_root=tmp_path)
    result = runtime.dispatch("MockAgent", ["test_command"])
    
    assert result.status == SubagentStatus.SUCCESS
    assert result.elapsed_ms > 0
    
    # Verify trace file exists and contains the correct JSON record
    trace_file = tmp_path / "execution_traces.jsonl"
    assert trace_file.exists()
    
    lines = trace_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    
    trace_data = json.loads(lines[0])
    assert trace_data["agent"] == "MockAgent"
    assert trace_data["command"] == "test_command"
    assert trace_data["status"] == "success"
    assert trace_data["elapsed_ms"] == result.elapsed_ms
    assert trace_data["output_summary"] == "Mock agent output content"
    assert "timestamp" in trace_data
