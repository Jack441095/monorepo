"""Tests for Thursday Phase 3: Unified Semantic Memory & Knowledge Graph Engine."""

import pytest

from thursday.memory.entity_graph import SemanticEntityGraph
from thursday.memory.episodic_memory import EpisodicMemory
from thursday.memory.memory_manager import MemoryManager, get_memory_manager


@pytest.fixture
def temp_memory_dir(tmp_path):
    return tmp_path / "memory"


def test_entity_graph_node_and_relationship(temp_memory_dir):
    graph = SemanticEntityGraph(temp_memory_dir)

    node = graph.add_entity("Jordan", "client", {"genre": "Dark Pop"})
    assert node.name == "Jordan"
    assert node.entity_type == "client"
    assert node.attributes["genre"] == "Dark Pop"

    rel = graph.add_relationship(
        source_name="Jordan",
        source_type="client",
        target_name="Riverside EP",
        target_type="project",
        relation_type="owns_project",
    )
    assert rel.relation_type == "owns_project"

    facts = graph.get_entity_facts("Jordan")
    assert facts["found"] is True
    assert len(facts["outgoing_relations"]) == 1
    assert facts["outgoing_relations"][0]["target_name"] == "Riverside EP"


def test_episodic_memory_recording_and_query(temp_memory_dir):
    ep_mem = EpisodicMemory(temp_memory_dir)

    ep1 = ep_mem.record_episode(
        session_id="sess_1",
        user_text="Draft invoice for Jordan",
        assistant_response="Invoice INV-005 drafted for Jordan.",
        intent="financial",
        service_used="admin_agent",
        entities_extracted={"client_name": "Jordan"},
    )
    assert ep1.intent == "financial"

    matches = ep_mem.query_episodes("Jordan")
    assert len(matches) == 1
    assert matches[0].session_id == "sess_1"


def test_memory_manager_integration(temp_memory_dir):
    mm = MemoryManager(temp_memory_dir)

    mm.remember_turn(
        session_id="sess_2",
        user_text="Schedule mixing session with Jordan for Riverside EP",
        assistant_response="Session scheduled for Jordan.",
        intent="calendar_scheduling",
        service_used="calendar_agenda",
        entities={"client_name": "Jordan", "project_name": "Riverside EP", "genre": "Dark Pop"},
    )

    context = mm.query_context("Tell me about Jordan")
    assert "Jordan" in context
    assert "Riverside EP" in context or "Past Interactions" in context


def test_memory_manager_singleton():
    mm1 = get_memory_manager()
    mm2 = get_memory_manager()
    assert mm1 is mm2
