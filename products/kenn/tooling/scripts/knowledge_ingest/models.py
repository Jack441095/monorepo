"""Data structures shared by the knowledge ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    name: str
    publisher: str
    tier: int
    seed_urls: tuple[str, ...]
    allowed_prefixes: tuple[str, ...]
    license: str
    terms_url: str | None
    raw_storage_allowed: bool = False
    max_pages: int = 100
    delay_seconds: float = 2.0
    follow_links: bool = True

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceSpec":
        return cls(
            source_id=str(value["source_id"]),
            name=str(value["name"]),
            publisher=str(value["publisher"]),
            tier=int(value["tier"]),
            seed_urls=tuple(value.get("seed_urls", ())),
            allowed_prefixes=tuple(value.get("allowed_prefixes", ())),
            license=str(value.get("license", "unknown")),
            terms_url=value.get("terms_url"),
            raw_storage_allowed=bool(value.get("raw_storage_allowed", False)),
            max_pages=int(value.get("max_pages", 100)),
            delay_seconds=float(value.get("delay_seconds", 2.0)),
            follow_links=bool(value.get("follow_links", True)),
        )


@dataclass
class DocumentRecord:
    source_id: str
    canonical_url: str
    title: str
    publisher: str
    source_tier: int
    license: str
    terms_url: str | None
    retrieved_at: str
    published_at: str | None
    content_hash: str
    language: str
    topics: list[str] = field(default_factory=list)
    summary: str = ""
    key_concepts: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    raw_storage_allowed: bool = False
    quality_score: float = 0.0
    text_chars: int = 0
    status: str = "accepted"
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "publisher": self.publisher,
            "source_tier": self.source_tier,
            "license": self.license,
            "terms_url": self.terms_url,
            "retrieved_at": self.retrieved_at,
            "published_at": self.published_at,
            "content_hash": self.content_hash,
            "language": self.language,
            "topics": self.topics,
            "summary": self.summary,
            "key_concepts": self.key_concepts,
            "citations": self.citations,
            "raw_storage_allowed": self.raw_storage_allowed,
            "quality_score": self.quality_score,
            "text_chars": self.text_chars,
            "status": self.status,
            "error": self.error,
        }
