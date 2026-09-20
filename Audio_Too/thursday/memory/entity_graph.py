"""Semantic Entity Graph for Thursday.

Stores and queries structured relationships between entities (Clients, Projects,
Audio Assets, Preferences, Invoices, Services).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

from thursday.atomic_io import atomic_write
from thursday.redaction import redact
from thursday.runtime_paths import MEMORY_DIR

logger = logging.getLogger(__name__)


@dataclass
class EntityNode:
    """Represents an entity node in Thursday's semantic knowledge graph."""

    name: str
    entity_type: str  # "client", "project", "audio_asset", "invoice", "preference"
    attributes: dict[str, Any] = field(default_factory=dict)
    entity_id: str = field(default_factory=lambda: "")
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.entity_id:
            cleaned = re.sub(r"[^\w]+", "_", self.name.lower()).strip("_")
            self.entity_id = f"{self.entity_type}:{cleaned}"


@dataclass
class Relationship:
    """Represents a directed relationship between two entity nodes."""

    source_id: str
    target_id: str
    relation_type: str  # "owns_project", "has_preference", "billed_by", "has_stem"
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SemanticEntityGraph:
    """JSON/SQLite-backed knowledge graph for Thursday's memory subsystem."""

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or MEMORY_DIR
        self.graph_file = self.storage_dir / "entity_graph.json"
        self._nodes: dict[str, EntityNode] = {}
        self._relationships: list[Relationship] = []
        self._load()

    def _load(self) -> None:
        """Load graph state from storage."""
        if self.graph_file.exists():
            try:
                data = json.loads(self.graph_file.read_text(encoding="utf-8"))
                for n_data in data.get("nodes", []):
                    node = EntityNode(
                        name=n_data["name"],
                        entity_type=n_data["entity_type"],
                        attributes=n_data.get("attributes", {}),
                        entity_id=n_data.get("entity_id", ""),
                        created_at=n_data.get("created_at", ""),
                        updated_at=n_data.get("updated_at", ""),
                    )
                    self._nodes[node.entity_id] = node
                for r_data in data.get("relationships", []):
                    rel = Relationship(
                        source_id=r_data["source_id"],
                        target_id=r_data["target_id"],
                        relation_type=r_data["relation_type"],
                        attributes=r_data.get("attributes", {}),
                        created_at=r_data.get("created_at", ""),
                    )
                    self._relationships.append(rel)
            except Exception as e:
                logger.warning(f"Failed to load entity graph: {redact(str(e))}")

    def save(self) -> None:
        """Save graph state to storage atomically."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [asdict(node) for node in self._nodes.values()],
            "relationships": [asdict(rel) for rel in self._relationships],
        }
        try:
            atomic_write(self.graph_file, json.dumps(data, indent=2))
        except OSError as e:
            logger.warning(f"Failed to save entity graph: {redact(str(e))}")

    def add_entity(self, name: str, entity_type: str, attributes: dict[str, Any] | None = None) -> EntityNode:
        """Add or update an entity node."""
        attributes = attributes or {}
        node = EntityNode(name=name, entity_type=entity_type, attributes=attributes)
        if node.entity_id in self._nodes:
            existing = self._nodes[node.entity_id]
            existing.attributes.update(attributes)
            existing.updated_at = datetime.now().isoformat()
            node = existing
        else:
            self._nodes[node.entity_id] = node
        self.save()
        return node

    def add_relationship(
        self, source_name: str, source_type: str, target_name: str, target_type: str, relation_type: str, attributes: dict[str, Any] | None = None
    ) -> Relationship:
        """Add a directed relationship between two entities, creating nodes if missing."""
        source = self.add_entity(source_name, source_type)
        target = self.add_entity(target_name, target_type)

        # Check for existing duplicate relationship
        for rel in self._relationships:
            if rel.source_id == source.entity_id and rel.target_id == target.entity_id and rel.relation_type == relation_type:
                rel.attributes.update(attributes or {})
                self.save()
                return rel

        rel = Relationship(
            source_id=source.entity_id,
            target_id=target.entity_id,
            relation_type=relation_type,
            attributes=attributes or {},
        )
        self._relationships.append(rel)
        self.save()
        return rel

    def get_entity(self, name_or_id: str) -> EntityNode | None:
        """Lookup entity node by exact entity_id or case-insensitive name match."""
        if name_or_id in self._nodes:
            return self._nodes[name_or_id]
        name_clean = name_or_id.lower().strip()
        for node in self._nodes.values():
            if node.name.lower().strip() == name_clean:
                return node
        return None

    def get_entity_facts(self, name_or_id: str) -> dict[str, Any]:
        """Get an entity node along with all incoming and outgoing relationships and facts."""
        node = self.get_entity(name_or_id)
        if not node:
            return {"found": False, "query": name_or_id}

        outgoing = []
        incoming = []

        for rel in self._relationships:
            if rel.source_id == node.entity_id:
                target_node = self._nodes.get(rel.target_id)
                outgoing.append({
                    "relation": rel.relation_type,
                    "target_name": target_node.name if target_node else rel.target_id,
                    "target_type": target_node.entity_type if target_node else "unknown",
                    "attributes": rel.attributes,
                })
            elif rel.target_id == node.entity_id:
                source_node = self._nodes.get(rel.source_id)
                incoming.append({
                    "relation": rel.relation_type,
                    "source_name": source_node.name if source_node else rel.source_id,
                    "source_type": source_node.entity_type if source_node else "unknown",
                    "attributes": rel.attributes,
                })

        return {
            "found": True,
            "entity": asdict(node),
            "outgoing_relations": outgoing,
            "incoming_relations": incoming,
        }

    def search_graph(self, query: str) -> list[EntityNode]:
        """Search entity nodes by keyword match in name or attributes."""
        q = query.lower().strip()
        matches = []
        for node in self._nodes.values():
            if q in node.name.lower() or q in node.entity_type.lower():
                matches.append(node)
                continue
            for val in node.attributes.values():
                if q in str(val).lower():
                    matches.append(node)
                    break
        return matches
