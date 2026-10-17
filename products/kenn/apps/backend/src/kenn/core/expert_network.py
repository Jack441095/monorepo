"""Expert Network knowledge contribution and vetting engine (Milestone E11).

Provides versioned, peer-reviewed engineering knowledge ingestion for KENN:
- Allows working mix/mastering engineers to contribute practical notes, lessons, and benchmarks.
- Enforces strict vetting gatekeeping: nothing unvetted or rejected is EVER surfaced to
  producers, retrieval indexes, or LLM reasoning prompts.
- Maintains cryptographic SHA-256 provenance and linear versioning across all revisions.
- Treats expert content as a qualified reference source, not an absolute guarantee of correctness.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from kenn.core.session_memory import DB_PATH

SCHEMA_CONTRIBUTION = "kenn.expert_contribution.v1"
SCHEMA_REVISION = "kenn.expert_revision.v1"

ALLOWED_CONTENT_TYPES = frozenset({"note", "lesson", "benchmark"})
ALLOWED_VETTING_STATUSES = frozenset({"pending_review", "approved", "rejected"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ExpertContribution:
    """A vetted knowledge artifact submitted by a working mixing/mastering engineer."""

    contribution_id: str
    contributor_name: str
    credentials: str
    content_type: str  # "note", "lesson", "benchmark"
    topic: str  # e.g., "spectral_balance", "low_end_phase", "crest_factor"
    title: str
    content_markdown: str
    target_standards: List[str]
    vetted: bool = False
    vetting_status: str = "pending_review"  # "pending_review", "approved", "rejected"
    vetted_by: Optional[str] = None
    vetted_at: Optional[str] = None
    review_feedback: str = ""
    version: int = 1
    sha256_digest: str = ""
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.sha256_digest:
            self.sha256_digest = _compute_sha256(self.content_markdown)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA_CONTRIBUTION,
            "contribution_id": self.contribution_id,
            "contributor_name": self.contributor_name,
            "credentials": self.credentials,
            "content_type": self.content_type,
            "topic": self.topic,
            "title": self.title,
            "content_markdown": self.content_markdown,
            "target_standards": self.target_standards,
            "vetted": self.vetted,
            "vetting_status": self.vetting_status,
            "vetted_by": self.vetted_by,
            "vetted_at": self.vetted_at,
            "review_feedback": self.review_feedback,
            "version": self.version,
            "sha256_digest": self.sha256_digest,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExpertContribution:
        return cls(
            contribution_id=str(data.get("contribution_id", "")),
            contributor_name=str(data.get("contributor_name", "")),
            credentials=str(data.get("credentials", "")),
            content_type=str(data.get("content_type", "note")),
            topic=str(data.get("topic", "general")),
            title=str(data.get("title", "")),
            content_markdown=str(data.get("content_markdown", "")),
            target_standards=list(data.get("target_standards", [])),
            vetted=bool(data.get("vetted", False)),
            vetting_status=str(data.get("vetting_status", "pending_review")),
            vetted_by=data.get("vetted_by"),
            vetted_at=data.get("vetted_at"),
            review_feedback=str(data.get("review_feedback", "")),
            version=int(data.get("version", 1)),
            sha256_digest=str(data.get("sha256_digest", "")),
            created_at=str(data.get("created_at", _utc_now())),
            updated_at=str(data.get("updated_at", _utc_now())),
        )


class ExpertNetworkStore:
    """Stores, versions, and gates expert knowledge contributions in SQLite."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            self.db_path = Path(DB_PATH)
        else:
            self.db_path = Path(db_path)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_tables(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_contributions (
                    contribution_id TEXT PRIMARY KEY,
                    contributor_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    vetted INTEGER NOT NULL DEFAULT 0,
                    vetting_status TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    sha256_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_expert_vetted "
                "ON expert_contributions(vetted, vetting_status, topic)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_contribution_revisions (
                    revision_id TEXT PRIMARY KEY,
                    contribution_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    sha256_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(contribution_id) REFERENCES expert_contributions(contribution_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_expert_revisions_lookup "
                "ON expert_contribution_revisions(contribution_id, version DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def submit_contribution(
        self,
        *,
        contributor_name: str,
        credentials: str,
        content_type: str,
        topic: str,
        title: str,
        content_markdown: str,
        target_standards: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Register a new unvetted expert contribution in pending_review status."""
        c_type = str(content_type or "").strip().lower()
        if c_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"content_type must be one of {sorted(ALLOWED_CONTENT_TYPES)}")

        clean_title = str(title or "").strip()[:256]
        if not clean_title:
            raise ValueError("title is required")

        clean_text = str(content_markdown or "").strip()
        if len(clean_text) < 20:
            raise ValueError("content_markdown must contain at least 20 characters of pedagogical instruction")

        cid = f"exp-{uuid4().hex[:12]}"
        now = _utc_now()
        digest = _compute_sha256(clean_text)

        contrib = ExpertContribution(
            contribution_id=cid,
            contributor_name=str(contributor_name or "Anonymous Engineer").strip()[:128],
            credentials=str(credentials or "Working Audio Engineer").strip()[:256],
            content_type=c_type,
            topic=str(topic or "general").strip().lower()[:64],
            title=clean_title,
            content_markdown=clean_text,
            target_standards=list(target_standards or []),
            vetted=False,  # Strictly unvetted upon initial submission
            vetting_status="pending_review",
            version=1,
            sha256_digest=digest,
            created_at=now,
            updated_at=now,
        )

        conn = self._connect()
        try:
            payload = json.dumps(contrib.to_dict(), sort_keys=True)
            conn.execute(
                """
                INSERT INTO expert_contributions (
                    contribution_id, contributor_name, content_type, topic,
                    vetted, vetting_status, version, sha256_digest, payload_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contrib.contribution_id,
                    contrib.contributor_name,
                    contrib.content_type,
                    contrib.topic,
                    0,
                    contrib.vetting_status,
                    contrib.version,
                    contrib.sha256_digest,
                    payload,
                    contrib.created_at,
                    contrib.updated_at,
                ),
            )
            # Record initial revision
            conn.execute(
                """
                INSERT INTO expert_contribution_revisions (
                    revision_id, contribution_id, version, sha256_digest, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"rev-{uuid4().hex[:12]}",
                    contrib.contribution_id,
                    contrib.version,
                    contrib.sha256_digest,
                    payload,
                    contrib.created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return contrib.to_dict()

    def review_contribution(
        self,
        *,
        contribution_id: str,
        decision: str,  # "approved", "rejected"
        reviewer_name: str,
        feedback: str = "",
    ) -> Dict[str, Any]:
        """Adjudicate an expert submission. Only approved contributions become vetted."""
        clean_decision = str(decision or "").strip().lower()
        if clean_decision not in ("approved", "rejected"):
            raise ValueError("decision must be either 'approved' or 'rejected'")

        clean_reviewer = str(reviewer_name or "").strip()[:128]
        if not clean_reviewer:
            raise ValueError("reviewer_name is required")

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT payload_json FROM expert_contributions WHERE contribution_id = ?",
                (contribution_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Expert contribution '{contribution_id}' not found")

            contrib = ExpertContribution.from_dict(json.loads(row["payload_json"]))
            now = _utc_now()

            contrib.vetting_status = clean_decision
            contrib.vetted = clean_decision == "approved"
            contrib.vetted_by = clean_reviewer
            contrib.vetted_at = now
            contrib.review_feedback = str(feedback or "").strip()
            contrib.updated_at = now

            payload = json.dumps(contrib.to_dict(), sort_keys=True)
            conn.execute(
                """
                UPDATE expert_contributions
                SET vetted = ?, vetting_status = ?, payload_json = ?, updated_at = ?
                WHERE contribution_id = ?
                """,
                (
                    1 if contrib.vetted else 0,
                    contrib.vetting_status,
                    payload,
                    now,
                    contrib.contribution_id,
                ),
            )
            conn.commit()
            return contrib.to_dict()
        finally:
            conn.close()

    def update_contribution_content(
        self,
        *,
        contribution_id: str,
        content_markdown: str,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update content of a contribution, bumping version and resetting vetting status."""
        clean_text = str(content_markdown or "").strip()
        if len(clean_text) < 20:
            raise ValueError("content_markdown must contain at least 20 characters")

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT payload_json FROM expert_contributions WHERE contribution_id = ?",
                (contribution_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Expert contribution '{contribution_id}' not found")

            contrib = ExpertContribution.from_dict(json.loads(row["payload_json"]))
            now = _utc_now()
            new_version = contrib.version + 1
            new_digest = _compute_sha256(clean_text)

            contrib.content_markdown = clean_text
            if title:
                contrib.title = str(title).strip()[:256]
            contrib.version = new_version
            contrib.sha256_digest = new_digest
            contrib.updated_at = now
            # Content updates invalidate prior approval: must be re-vetted
            contrib.vetted = False
            contrib.vetting_status = "pending_review"

            payload = json.dumps(contrib.to_dict(), sort_keys=True)
            conn.execute(
                """
                UPDATE expert_contributions
                SET version = ?, sha256_digest = ?, vetted = 0, vetting_status = 'pending_review',
                    payload_json = ?, updated_at = ?
                WHERE contribution_id = ?
                """,
                (
                    new_version,
                    new_digest,
                    payload,
                    now,
                    contrib.contribution_id,
                ),
            )
            # Record immutable revision snapshot
            conn.execute(
                """
                INSERT INTO expert_contribution_revisions (
                    revision_id, contribution_id, version, sha256_digest, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"rev-{uuid4().hex[:12]}",
                    contrib.contribution_id,
                    new_version,
                    new_digest,
                    payload,
                    now,
                ),
            )
            conn.commit()
            return contrib.to_dict()
        finally:
            conn.close()

    def list_surfaced_expert_content(
        self,
        *,
        topic: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Strict gatekeeper: return ONLY vetted, approved contributions.

        Nothing unvetted, pending_review, or rejected is ever returned.
        """
        conn = self._connect()
        try:
            query = "SELECT payload_json FROM expert_contributions WHERE vetted = 1 AND vetting_status = 'approved'"
            params: List[Any] = []

            if topic:
                query += " AND topic = ?"
                params.append(str(topic).strip().lower())
            if content_type:
                query += " AND content_type = ?"
                params.append(str(content_type).strip().lower())

            query += " ORDER BY updated_at DESC"
            rows = conn.execute(query, params).fetchall()

            results: List[Dict[str, Any]] = []
            for row in rows:
                try:
                    data = json.loads(row["payload_json"])
                    # Double-check cryptographic hash integrity before surfacing
                    expected_digest = data.get("sha256_digest", "")
                    actual_digest = _compute_sha256(data.get("content_markdown", ""))
                    if expected_digest == actual_digest:
                        results.append(data)
                except (json.JSONDecodeError, TypeError):
                    continue
            return results
        finally:
            conn.close()

    def get_contribution_history(self, contribution_id: str) -> List[Dict[str, Any]]:
        """Retrieve complete linear version history for a contribution."""
        clean_cid = str(contribution_id or "").strip()
        if not clean_cid:
            return []

        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT version, sha256_digest, payload_json, created_at
                FROM expert_contribution_revisions
                WHERE contribution_id = ?
                ORDER BY version ASC
                """,
                (clean_cid,),
            ).fetchall()

            history = []
            for row in rows:
                try:
                    data = json.loads(row["payload_json"])
                    history.append({
                        "version": row["version"],
                        "sha256_digest": row["sha256_digest"],
                        "created_at": row["created_at"],
                        "title": data.get("title", ""),
                        "content_markdown": data.get("content_markdown", ""),
                        "vetted": data.get("vetted", False),
                    })
                except (json.JSONDecodeError, TypeError):
                    continue
            return history
        finally:
            conn.close()


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "ALLOWED_VETTING_STATUSES",
    "ExpertContribution",
    "ExpertNetworkStore",
    "SCHEMA_CONTRIBUTION",
    "SCHEMA_REVISION",
]
