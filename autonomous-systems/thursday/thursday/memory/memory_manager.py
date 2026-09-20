"""Memory Manager Facade for Thursday.

Coordinates Semantic Entity Graph, Episodic Memory, and Plan Memory to provide
contextual memory retrieval for entity resolution and LLM reasoning.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from thursday.memory.entity_graph import SemanticEntityGraph
from thursday.memory.episodic_memory import EpisodicMemory
from thursday.redaction import get_logger as _get_redacting_logger
from thursday.runtime_paths import MEMORY_DIR

logger = _get_redacting_logger(__name__)


class MemoryManager:
    """Central facade coordinating Thursday's memory subsystems."""

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or MEMORY_DIR
        self.entity_graph = SemanticEntityGraph(self.storage_dir)
        self.episodic_memory = EpisodicMemory(self.storage_dir)

    def remember_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_response: str,
        intent: str = "unknown",
        service_used: str = "",
        entities: dict[str, Any] | None = None,
    ) -> None:
        """Record a completed conversation turn into episodic memory and populate the entity graph."""
        entities = entities or {}
        # 1. Record episode
        self.episodic_memory.record_episode(
            session_id=session_id,
            user_text=user_text,
            assistant_response=assistant_response,
            intent=intent,
            service_used=service_used,
            entities_extracted=entities,
        )

        # 2. Extract and auto-populate entity graph relationships
        try:
            client_name = entities.get("client_name") or entities.get("name")
            project_name = entities.get("project_name") or entities.get("project")
            
            if client_name:
                self.entity_graph.add_entity(client_name, "client")
                if project_name:
                    self.entity_graph.add_relationship(
                        source_name=client_name,
                        source_type="client",
                        target_name=project_name,
                        target_type="project",
                        relation_type="owns_project",
                    )
                # Auto-populate preferences if mentioned
                genre = entities.get("genre")
                if genre:
                    self.entity_graph.add_relationship(
                        source_name=client_name,
                        source_type="client",
                        target_name=genre,
                        target_type="preference",
                        relation_type="prefers_genre",
                    )
        except Exception as e:
            logger.warning(f"Entity graph auto-population failed: {e}")

    def query_context(self, user_text: str, limit: int = 3, max_tokens: int | None = None) -> str:
        """Build a formatted memory context markdown block for prompt injection into brain.py.

        `max_tokens`, when given, caps the assembled block: the entity-graph
        section is kept over the episodic-memory section if both can't fit
        (see `thursday.budget.BudgetedContext`). Default `None` preserves
        the original unbounded behavior for any existing caller.
        """
        parts = []

        # 1. Query relevant entity facts from the graph
        words = [w.strip() for w in user_text.split() if len(w.strip()) > 2]
        facts_found = []
        for word in words:
            node = self.entity_graph.get_entity(word)
            if node:
                facts = self.entity_graph.get_entity_facts(node.entity_id)
                if facts.get("found"):
                    lines = [f"- Entity '{node.name}' ({node.entity_type}):"]
                    for rel in facts.get("outgoing_relations", []):
                        lines.append(f"    -> {rel['relation']} {rel['target_name']}")
                    for rel in facts.get("incoming_relations", []):
                        lines.append(f"    <- {rel['source_name']} {rel['relation']}")
                    facts_found.append("\n".join(lines))

        if facts_found:
            parts.append("## Semantic Memory (Entity Knowledge Graph)\n" + "\n".join(facts_found))

        # 2. Query relevant past episodes
        episodes = self.episodic_memory.query_episodes(user_text, limit=limit)
        if episodes:
            ep_lines = ["## Episodic Memory (Past Interactions)"]
            for ep in episodes:
                ep_lines.append(f"- User: \"{ep.user_text}\" -> Thursday: \"{ep.assistant_response[:120]}...\" ({ep.intent})")
            parts.append("\n".join(ep_lines))

        if not parts:
            return ""
        if max_tokens is None:
            return "\n\n".join(parts)

        from thursday.budget import BudgetedContext

        budgeted = BudgetedContext(max_tokens=max_tokens)
        for i, part in enumerate(parts):
            budgeted.add(f"memory_part_{i}", part, priority=i)
        return budgeted.build()


# Global Singleton
_MEMORY_MANAGER_INSTANCE: MemoryManager | None = None
_MEMORY_LOCK = threading.Lock()


def get_memory_manager() -> MemoryManager:
    """Retrieve the global MemoryManager singleton instance."""
    global _MEMORY_MANAGER_INSTANCE
    if _MEMORY_MANAGER_INSTANCE is None:
        with _MEMORY_LOCK:
            if _MEMORY_MANAGER_INSTANCE is None:
                _MEMORY_MANAGER_INSTANCE = MemoryManager()
    return _MEMORY_MANAGER_INSTANCE
