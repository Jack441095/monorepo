"""Episodic Memory Store for Thursday.

Stores chronological summaries of user interactions and session turns across sessions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

from thursday.atomic_io import atomic_write
from thursday.redaction import redact
from thursday.runtime_paths import MEMORY_DIR

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """Represents a recorded conversation episode/turn in episodic memory."""

    session_id: str
    user_text: str
    assistant_response: str
    intent: str = "unknown"
    service_used: str = ""
    entities_extracted: dict[str, Any] = field(default_factory=dict)
    episode_id: str = field(default_factory=lambda: "")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.episode_id:
            import uuid
            self.episode_id = str(uuid.uuid4())[:12]


class EpisodicMemory:
    """Stores and retrieves historical conversation turns across sessions."""

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or MEMORY_DIR
        self.episodes_file = self.storage_dir / "episodes.json"
        self._episodes: list[Episode] = []
        self._load()

    def _load(self) -> None:
        """Load episodes from storage."""
        if self.episodes_file.exists():
            try:
                data = json.loads(self.episodes_file.read_text(encoding="utf-8"))
                for ep_data in data:
                    ep = Episode(
                        session_id=ep_data.get("session_id", ""),
                        user_text=ep_data.get("user_text", ""),
                        assistant_response=ep_data.get("assistant_response", ""),
                        intent=ep_data.get("intent", "unknown"),
                        service_used=ep_data.get("service_used", ""),
                        entities_extracted=ep_data.get("entities_extracted", {}),
                        episode_id=ep_data.get("episode_id", ""),
                        timestamp=ep_data.get("timestamp", ""),
                    )
                    self._episodes.append(ep)
            except Exception as e:
                logger.warning(f"Failed to load episodic memory: {redact(str(e))}")

    def save(self) -> None:
        """Save episodes to storage atomically."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # Retain last 1000 episodes
        data = [asdict(ep) for ep in self._episodes[-1000:]]
        try:
            atomic_write(self.episodes_file, json.dumps(data, indent=2))
        except OSError as e:
            logger.warning(f"Failed to save episodic memory: {redact(str(e))}")

    def record_episode(
        self,
        session_id: str,
        user_text: str,
        assistant_response: str,
        intent: str = "unknown",
        service_used: str = "",
        entities_extracted: dict[str, Any] | None = None,
    ) -> Episode:
        """Record a new conversation episode."""
        ep = Episode(
            session_id=session_id,
            user_text=user_text,
            assistant_response=assistant_response,
            intent=intent,
            service_used=service_used,
            entities_extracted=entities_extracted or {},
        )
        self._episodes.append(ep)
        self.save()
        return ep

    def query_episodes(self, query: str, limit: int = 5) -> list[Episode]:
        """Search episodes by keyword matching user_text or assistant_response."""
        q = query.lower().strip()
        matches = []
        for ep in reversed(self._episodes):
            if q in ep.user_text.lower() or q in ep.assistant_response.lower():
                matches.append(ep)
                if len(matches) >= limit:
                    break
        return matches

    def get_recent(self, limit: int = 5) -> list[Episode]:
        """Get recent episodes across sessions."""
        return list(reversed(self._episodes[-limit:]))
