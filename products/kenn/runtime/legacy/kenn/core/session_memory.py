"""Lightweight session memory with SQLite persistence.

Stores session state per-session_id in KENN/chats/kenn.db.
Backward-compatible: falls back to JSON file if DB is unavailable.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Where session memory lives
CHATS_DIR = Path(os.environ.get("KENN_CHATS_DIR", str(ROOT / "chats"))).expanduser()
SESSION_FILE = Path(
    os.environ.get("KENN_SESSION_FILE", str(CHATS_DIR / "session.json"))
).expanduser()
DB_PATH = Path(os.environ.get("KENN_DB_PATH", str(CHATS_DIR / "kenn.db"))).expanduser()

# Default TTL for a session
SESSION_TTL_HOURS = 6

# We track this many recent queries for topic continuity
MAX_HISTORY = 8


# ---------------------------------------------------------------------------
# Session state structure
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SQLite session storage (persistent across restarts)
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    """Get or create the SQLite database for session storage."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mix_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            version_label TEXT NOT NULL,
            metrics_snapshot TEXT NOT NULL,
            repair_chain_applied TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_id TEXT UNIQUE,
            explicit_rating INTEGER,
            dwell_seconds REAL,
            has_followup BOOLEAN,
            followup_interval_seconds REAL,
            route TEXT,
            topics TEXT,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT UNIQUE,
            embedding_json TEXT NOT NULL,
            events_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            last_used_at INTEGER NOT NULL
        )
        """
    )
    conn.row_factory = sqlite3.Row
    return conn


SEMANTIC_CACHE_TTL_SECONDS = 3600  # 1 hour


def get_semantic_cache_hit(query: str, threshold: float = 0.95) -> dict | None:
    """Check the SQLite semantic cache for a query with similar embedding.

    Returns the parsed events list if found and not stale, otherwise None.

    Live-tested 2026-08-04: this cache has no TTL, no invalidation, and every
    error is silently swallowed by the caller in chat_answer.py. A query
    tested during a bug investigation got cached with `confidence: "high"`
    (its accepted quality bar for caching), and the broken answer kept being
    served verbatim after the underlying bug was fixed in code -- with zero
    visible indication anything was cached or stale. A code fix (not just an
    index rebuild) can't be detected via any version/hash check here, so a
    TTL is the one safety net that protects against every kind of
    staleness, not just index changes.
    """
    clean_query = query.strip().lower()
    if not clean_query:
        return None
    min_created_at = int(time.time()) - SEMANTIC_CACHE_TTL_SECONDS
    try:
        conn = _get_db()
        # 1. First check for exact query match (instant, no embedding required)
        row = conn.execute(
            "SELECT events_json FROM semantic_cache WHERE LOWER(query) = ? AND created_at >= ?",
            (clean_query, min_created_at),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE semantic_cache SET last_used_at = ? WHERE LOWER(query) = ?",
                (int(time.time()), clean_query)
            )
            conn.commit()
            return json.loads(row["events_json"])

        # 2. Semantic search using embeddings
        # Local import to avoid circular imports
        from kenn.retrieval.retrieval import embed_text
        query_emb = embed_text(query)
        if query_emb is None or len(query_emb) == 0:
            return None

        rows = conn.execute(
            "SELECT query, embedding_json, events_json FROM semantic_cache WHERE created_at >= ?",
            (min_created_at,),
        ).fetchall()
        best_score = -1.0
        best_events_json = None
        best_query = None

        for r in rows:
            try:
                cached_emb = json.loads(r["embedding_json"])
                if len(cached_emb) != len(query_emb):
                    continue
                # Dot product (since vectors are L2-normalized, this is exactly cosine similarity)
                score = sum(q * c for q, c in zip(query_emb, cached_emb))
                if score > best_score:
                    best_score = score
                    best_events_json = r["events_json"]
                    best_query = r["query"]
            except Exception:
                continue

        if best_score >= threshold and best_events_json is not None:
            conn.execute(
                "UPDATE semantic_cache SET last_used_at = ? WHERE query = ?",
                (int(time.time()), best_query)
            )
            conn.commit()
            return json.loads(best_events_json)
    except Exception as exc:
        print(f"WARNING: get_semantic_cache_hit failed: {exc}")
    return None


def save_to_semantic_cache(query: str, events: list) -> None:
    """Save a query, its embedding, and final generated events to the SQLite cache."""
    clean_query = query.strip()
    if not clean_query or not events:
        return
    try:
        from kenn.retrieval.retrieval import embed_text
        query_emb = embed_text(clean_query)
        if query_emb is None or len(query_emb) == 0:
            return
            
        conn = _get_db()
        now = int(time.time())
        conn.execute(
            """
            INSERT OR REPLACE INTO semantic_cache (query, embedding_json, events_json, created_at, last_used_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                clean_query,
                json.dumps(query_emb.tolist()),
                json.dumps(events),
                now,
                now
            )
        )
        # Opportunistic cleanup so the table doesn't grow unbounded -- no
        # separate cron job needed, expired rows get swept on the next write.
        conn.execute(
            "DELETE FROM semantic_cache WHERE created_at < ?",
            (now - SEMANTIC_CACHE_TTL_SECONDS,),
        )
        conn.commit()
    except Exception as exc:
        print(f"WARNING: save_to_semantic_cache failed: {exc}")


def load_session_from_db(session_id: str) -> dict[str, Any] | None:
    """Load a specific session from SQLite, or return None if not found."""
    sid = session_id.strip()
    if not sid:
        return None
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT state FROM sessions WHERE session_id = ?", (sid,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["state"])
        merged = dict(EMPTY_SESSION)
        merged.update(data)
        return merged
    except (sqlite3.Error, json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: load_session_from_db failed for session {sid!r} ({exc!r}) -- "
              f"treating this session as new; prior conversation context will be lost")
        return None


def save_session_to_db(state: dict[str, Any]) -> None:
    """Save session state to SQLite."""
    session_id = state.get("session_id", "").strip()
    if not session_id:
        return
    try:
        conn = _get_db()
        now = int(time.time())
        conn.execute(
            """INSERT OR REPLACE INTO sessions (session_id, state, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, json.dumps(state), state.get("created_at", now), now),
        )
        conn.commit()
    except (sqlite3.Error, OSError) as exc:
        print(f"WARNING: save_session_to_db failed for session {session_id!r} ({exc!r}) -- "
              f"this turn's conversation memory was not persisted")


def list_db_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """List recent sessions from the database."""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT session_id, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    except (sqlite3.Error, OSError):
        return []


def configured_retention_hours() -> int:
    try:
        return max(1, min(8760, int(os.getenv("AUDIO_TOO_KENN_SESSION_RETENTION_HOURS", "168"))))
    except ValueError:
        return 168


def delete_old_sessions(keep_hours: int | None = None) -> int:
    """Delete sessions older than keep_hours. Returns count deleted."""
    try:
        keep_hours = configured_retention_hours() if keep_hours is None else max(1, keep_hours)
        conn = _get_db()
        cutoff = int(time.time()) - (keep_hours * 3600)
        cursor = conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
        conn.commit()
        return cursor.rowcount
    except (sqlite3.Error, OSError):
        return 0


# ---------------------------------------------------------------------------
# Session state structure
# ---------------------------------------------------------------------------
EMPTY_SESSION: dict[str, Any] = {
    "last_question": "",
    "last_answer": "",
    "last_route": "",
    "last_answer_mode": "",
    "last_confidence": "",
    "last_intent": "",
    "topics_mentioned": [],
    "techniques_mentioned": [],
    "track_names": [],
    "current_project": "",
    "preferences": {},
    "followup_count": 0,
    "turn_count": 0,
    "last_updated": 0,
    "created_at": 0,
    "session_id": "",
}


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def _ensure_chats_dir() -> Path:
    """Make sure chats/ exists."""
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    return CHATS_DIR


def load_session(session_id: str = "") -> dict[str, Any]:
    """Load session memory, preferring SQLite, falling back to JSON file.

    If session_id is provided, tries SQLite first. If blank, creates
    a fresh session (does not read stale JSON).
    """
    if session_id:
        db_state = load_session_from_db(session_id)
        if db_state is not None:
            return db_state
        # Not in DB yet — return empty state with this session_id
        state = dict(EMPTY_SESSION)
        state["session_id"] = session_id
        return state
    # No session_id — return fresh state
    return dict(EMPTY_SESSION)


def save_session(state: dict[str, Any]) -> None:
    """Save session memory to disk (SQLite). Legacy JSON removed."""
    _ensure_chats_dir()
    # Save to SQLite
    try:
        save_session_to_db(state)
    except Exception:
        pass
    # Clean up legacy JSON if we're SQLite-based
    if state.get("session_id"):
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
        except OSError:
            pass


def clear_session(session_id: str = "") -> None:
    """Reset session memory completely."""
    if session_id:
        try:
            conn = _get_db()
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        except (sqlite3.Error, OSError):
            pass
    save_session(dict(EMPTY_SESSION))


# ---------------------------------------------------------------------------
# AutoMix project linkage — lets a chat session remember which AutoMix
# project a "make it brighter" follow-up refers to, without the caller
# having to repeat project_id on every turn. Distinct from "current_project"
# above, which is a free-text name extracted from conversation for KENN's
# own context-building, not an automix_jobs foreign key.
# ---------------------------------------------------------------------------


def remember_automix_project(session_id: str, project_id: str) -> None:
    if not session_id or not project_id:
        return
    state = load_session(session_id)
    state["session_id"] = session_id
    state["automix_project_id"] = project_id
    save_session(state)


def get_remembered_automix_project(session_id: str) -> str:
    if not session_id:
        return ""
    state = load_session(session_id)
    return str(state.get("automix_project_id") or "")


# ---------------------------------------------------------------------------
# Pending AutoMix job tracking (D2.3, docs/KENN_FUTURE_PLAN.md Phase 2) --
# lets KENN proactively surface a revision job's completion in chat later,
# without the user having to ask "is it done yet?". Distinct from
# app.js's existing pollAndRenderToolResult, which only follows a job
# started in the SAME chat turn that queued it -- a job queued via
# _handle_mix_revision (business/app/ableton_bridge.py) returns
# immediately with "this runs in the background", and nothing previously
# ever told the frontend when that background job actually finished.
# ---------------------------------------------------------------------------


def remember_pending_automix_job(session_id: str, job_id: str) -> None:
    if not session_id or not job_id:
        return
    state = load_session(session_id)
    state["session_id"] = session_id
    pending = list(state.get("pending_automix_jobs") or [])
    if job_id not in pending:
        pending.append(job_id)
    state["pending_automix_jobs"] = pending
    save_session(state)


def get_pending_automix_jobs(session_id: str) -> list[str]:
    if not session_id:
        return []
    state = load_session(session_id)
    return [str(j) for j in (state.get("pending_automix_jobs") or [])]


def clear_pending_automix_job(session_id: str, job_id: str) -> None:
    """Remove a job from the pending list once its completion has been
    surfaced to the user -- a one-shot notification, not a repeated poll
    result. No-ops silently if the job isn't in the list (already cleared,
    or never tracked)."""
    if not session_id or not job_id:
        return
    state = load_session(session_id)
    pending = [j for j in (state.get("pending_automix_jobs") or []) if str(j) != str(job_id)]
    state["pending_automix_jobs"] = pending
    save_session(state)


# ---------------------------------------------------------------------------
# Listening checkpoints (D2.4, docs/KENN_FUTURE_PLAN.md Phase 2) -- when
# KENN proposes a specific, concrete change (a queued revision, a DAW
# write it just executed, an EQ-move suggestion), it can attach a
# checkpoint asking the user to confirm after listening. Only the VERY
# NEXT reply in this session is checked against it -- see
# server.py::_maybe_handle_checkpoint_reply(), which clears the
# checkpoint unconditionally after that one check, matched or not, so a
# checkpoint can never linger and misinterpret a much later unrelated
# "yes" as an answer to a stale proposal.
# ---------------------------------------------------------------------------


def remember_pending_checkpoint(session_id: str, description: str, revision_history_id: int | None = None) -> None:
    """``revision_history_id`` (added for §13.6.2, "applied revisions log
    -- track what KENN applied + whether you kept it") is the
    `project_revision_history` row this checkpoint corresponds to, if
    any -- lets the accept/reject reply feed back into that row's
    `outcome` column via `song_projects.record_revision_outcome()`. None
    when the checkpoint isn't tied to a specific persisted revision
    (e.g. an EQ-move suggestion checkpoint has no revision_history row)."""
    if not session_id or not description:
        return
    state = load_session(session_id)
    state["session_id"] = session_id
    state["pending_checkpoint"] = {
        "description": description,
        "created_at": time.time(),
        "revision_history_id": revision_history_id,
    }
    save_session(state)


def get_pending_checkpoint(session_id: str) -> dict | None:
    if not session_id:
        return None
    state = load_session(session_id)
    checkpoint = state.get("pending_checkpoint")
    return dict(checkpoint) if checkpoint else None


def clear_pending_checkpoint(session_id: str) -> None:
    if not session_id:
        return
    state = load_session(session_id)
    if "pending_checkpoint" in state:
        state["pending_checkpoint"] = None
        save_session(state)


# ---------------------------------------------------------------------------
# Topic extraction helpers
# ---------------------------------------------------------------------------

# Pattern-based technique extraction — matches common audio engineering terms
_TECHNIQUE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bhigh.pass\b", re.I), "high-pass filtering"),
    (re.compile(r"\blow.pass\b", re.I), "low-pass filtering"),
    (re.compile(r"\bparallel\s+(comp|compress|compr)", re.I), "parallel compression"),
    (re.compile(r"\bbus\s+comp", re.I), "bus compression"),
    (re.compile(r"\bside.?.?chain\b", re.I), "sidechain processing"),
    (re.compile(r"\bmid.side\b", re.I), "mid-side processing"),
    (re.compile(r"\bMS\s+eq\b", re.I), "mid-side EQ"),
    (re.compile(r"\bM/S\b", re.I), "mid-side processing"),
    (re.compile(r"\bEQ sweep\b", re.I), "EQ sweep technique"),
    (re.compile(r"\bnotch\b", re.I), "notch filtering"),
    (re.compile(r"\bbell\s+curve\b", re.I), "bell curve EQ"),
    (re.compile(r"\bshelf\b", re.I), "shelving EQ"),
    (re.compile(r"\bmulti.band\b", re.I), "multiband processing"),
    (re.compile(r"\bgain.staging?\b", re.I), "gain staging"),
    (re.compile(r"\bsaturation?\b", re.I), "saturation"),
    (re.compile(r"\bclipping?\b", re.I), "clipping"),
    (re.compile(r"\bcompression\b", re.I), "compression"),
    (re.compile(r"\blimiting\b", re.I), "limiting"),
    (re.compile(r"\breverb?\b", re.I), "reverb"),
    (re.compile(r"\bdelay\b", re.I), "delay"),
    (re.compile(r"\bde.esser\b", re.I), "de-essing"),
    (re.compile(r"\bdeesser\b", re.I), "de-essing"),
    (re.compile(r"\bdenois(e|ing)\b", re.I), "noise reduction"),
    (re.compile(r"\bgate\b", re.I), "gating"),
    (re.compile(r"\bexpander\b", re.I), "expansion"),
    (re.compile(r"\btransient\b", re.I), "transient shaping"),
    (re.compile(r"\bwarp(ing)?\b", re.I), "warping"),
    (re.compile(r"\bfreeze\b", re.I), "freezing"),
    (re.compile(r"\bbounce\b", re.I), "bouncing"),
    (re.compile(r"\bresample\b", re.I), "resampling"),
    (re.compile(r"\bautomation\b", re.I), "automation"),
    (re.compile(r"\bgroove\b", re.I), "groove"),
    (re.compile(r"\bquantiz(e|ation)\b", re.I), "quantization"),
    (re.compile(r"\btempo\b", re.I), "tempo mapping"),
    (re.compile(r"\btuning?\b", re.I), "tuning"),
    (re.compile(r"\btrack\s+layering\b", re.I), "track layering"),
    (re.compile(r"\bstereo\s+width\b", re.I), "stereo width"),
    (re.compile(r"\bmono\b", re.I), "mono compatibility"),
    (re.compile(r"\bLUFS\b", re.I), "loudness standards"),
    (re.compile(r"\btrue\s+peak\b", re.I), "true peak limiting"),
    (re.compile(r"\bcrest\s+factor\b", re.I), "crest factor"),
    (re.compile(r"\broom\s+tone\b", re.I), "room tone"),
    (re.compile(r"\bphase\b", re.I), "phase alignment"),
    (re.compile(r"\bpolarity\b", re.I), "polarity"),
    (re.compile(r"\bheadroom\b", re.I), "headroom"),
    (re.compile(r"\bmonitoring?\b", re.I), "monitoring"),
    (re.compile(r"\bA/B\b", re.I), "A/B comparison"),
    (re.compile(r"\blevel.match\b", re.I), "level-matched comparison"),
]


def extract_techniques(text: str) -> list[str]:
    """Extract audio engineering techniques mentioned in a text."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern, label in _TECHNIQUE_PATTERNS:
        if pattern.search(text) and label not in seen:
            found.append(label)
            seen.add(label)
    return found


# Track name patterns — "the vocal", "my kick", "the snare", "that bass line"
# Deliberately excludes bare "track[s]?"/"mix"/"master" from the first
# pattern -- "the track"/"the mix" is a self-referential generic phrase, not
# an identifiable element, and rendering it back as "tracks like the track"
# reads as nonsense.
_TRACK_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(?:my|the|that|this)\s+(vocal[s]?|kick|snare|hi.?hat|hat|cymbal[s]?|crash|ride|tom[s]?|bass|sub|guitar|piano|pad[s]?|lead|synth|string[s]?|brass|horn[s]?|fx|fx?x|fx?fx|drum[s]?|stem[s]?)\b", re.I),
    re.compile(r"\b(vocal[s]?|kick\sdrum|snare\sdrum|bass\sline|lead\svocal)[s]?\b", re.I),
    re.compile(r"\b(bass\sguitar|lead\sguitar|rhythm\sguitar|acoustic\sguitar|electric\sguitar)\b", re.I),
    re.compile(r"\b(sub\s?bass|808|sub)\b", re.I),
    re.compile(r"\b(room|overhead[s]?|ambient|pzm)\b", re.I),
    re.compile(r"\b(master|mix\s?bus|stereo\s?bus|drum\s?bus|vocal\s?bus)\s+(bus|chain)?\b", re.I),
]

_TRACK_NAME_ARTICLE_RE = re.compile(r"^(?:my|the|that|this)\s+", re.I)
_TRACK_NAME_SINGULAR = {
    "vocals": "vocal", "cymbals": "cymbal", "toms": "tom", "pads": "pad",
    "strings": "string", "horns": "horn", "drums": "drum", "stems": "stem",
}


def extract_track_names(text: str) -> list[str]:
    """Extract likely track names from a query or answer."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _TRACK_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(0).strip().lower()
            name = _TRACK_NAME_ARTICLE_RE.sub("", name)
            name = _TRACK_NAME_SINGULAR.get(name, name)
            if name not in seen:
                seen.add(name)
                found.append(name)
    return found


# Common project-related terms
_PROJECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(?:project|session|song|piece|composition|beat|idea)\s+["\']([^"\']{2,})["\']', re.I), ""),
    (re.compile(r'\bworking on\s+["\']([^"\']{2,})["\']', re.I), ""),
    (re.compile(r'\bcall(?:ed| it)?\s+["\']([^"\']{2,})["\']', re.I), ""),
]


def extract_project_name(text: str) -> str:
    """Extract a project or track name from text, if present."""
    for pattern, _ in _PROJECT_PATTERNS:
        match = pattern.search(text)
        if match:
            # Try to get the captured group (the name)
            groups = match.groups()
            for g in groups:
                if g and len(g) > 2 and g.lower() not in {
                    "name", "it", "this", "that", "my", "your", "the", "a",
                    "project", "track", "song", "piece", "idea", "beat",
                }:
                    return g
    return ""


# ---------------------------------------------------------------------------
# Preference hints — infer from query language
# ---------------------------------------------------------------------------

_PREFERENCE_HINTS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\bheadphones?\b", re.I), "monitoring", "headphones"),
    (re.compile(r"\bmonitors?\b", re.I), "monitoring", "monitors"),
    (re.compile(r"\b(small|cheap|laptop|phone|earbuds?)\b", re.I), "monitoring", "consumer speakers"),
    (re.compile(r"\bparallel\b", re.I), "compression_style", "parallel"),
    (re.compile(r"\bbus\s+comp", re.I), "compression_style", "bus"),
    (re.compile(r"\b1176\b", re.I), "compressor_preference", "1176"),
    (re.compile(r"\bLA.2[AE]\b", re.I), "compressor_preference", "LA-2A"),
    (re.compile(r"\bCLA.76\b", re.I), "compressor_preference", "CLA-76"),
    (re.compile(r"\bSSL\b", re.I), "compressor_preference", "SSL bus"),
    (re.compile(r"\bAbleton\b(?!\s+Live)", re.I), "daw", "Ableton Live"),
    (re.compile(r"\bLogic\b", re.I), "daw", "Logic Pro"),
    (re.compile(r"\bCubase\b", re.I), "daw", "Cubase"),
    (re.compile(r"\bPro\s+Tools\b", re.I), "daw", "Pro Tools"),
    (re.compile(r"\bFL\s+Studio\b", re.I), "daw", "FL Studio"),
    (re.compile(r"\bstudio\s+one\b", re.I), "daw", "Studio One"),
    (re.compile(r"\b(reference|professional|commercial|streaming)\s+(track|mix)", re.I), "reference_tracks", "reference tracks mentioned"),
    (re.compile(r"\bmixing\s+(in|with)\s+headphones?\b", re.I), "monitoring", "headphones"),
    (re.compile(r"\b(sub|subwoofer)\b", re.I), "subwoofer", "yes"),
    # Skill-level cues -- deliberately conservative: only explicit self-description,
    # not a jargon-density heuristic, since misreading a beginner as advanced (or
    # vice versa) is worse than saying nothing and defaulting to the model's
    # normal tone.
    (re.compile(r"\b(i'?m|i am)\s+(a\s+)?(complete\s+)?(beginner|newbie|new\s+to\s+(mixing|production|this|ableton|music production))\b", re.I), "skill_level", "beginner"),
    (re.compile(r"\b(never\s+(mixed|produced)|first\s+(time|track|song)\s+(mixing|producing)|just\s+start(ed|ing)\s+out)\b", re.I), "skill_level", "beginner"),
    (re.compile(r"\b(i'?ve\s+been\s+(mixing|producing|engineering)\s+for\s+\d+\s*\+?\s*years?|professional\s+(mix(ing)?|mastering)\s+engineer|(?:i'?m|i\s+am)\s+an?\s+(experienced|advanced|professional)\s+(engineer|producer|mixer))\b", re.I), "skill_level", "advanced"),
]

_GENRE_PATTERN = re.compile(
    r"\b(pop|hip.?hop|trap|edm|house|techno|drum\s*(?:and|&)\s*bass|dnb|rock|metal|indie|folk|jazz|r&b|rnb|reggaeton|lofi|lo-fi|ambient|country|funk|disco)\b",
    re.I,
)

_CREATIVE_GOAL_PATTERN = re.compile(
    r"\b(?:i\s+(?:want|need)|(?>i'?m|i\s+am)\s+(?:going|aiming)\s+for|the\s+goal\s+is|target(?:ing)?\s+a?)\s+"
    r"((?:dark|bright|warm|clean|raw|intimate|aggressive|soft|wide|narrow|dry|lush|vintage|modern|punchy|smooth|upfront|distant)(?:[\s,/-]+(?:and\s+)?(?:dark|bright|warm|clean|raw|intimate|aggressive|soft|wide|narrow|dry|lush|vintage|modern|punchy|smooth|upfront|distant)){0,3})\b",
    re.I,
)


def infer_genre(text: str) -> str:
    """Infer a genre keyword from the text, if one is mentioned directly."""
    match = _GENRE_PATTERN.search(text)
    return match.group(1).lower() if match else ""


def infer_preferences(text: str) -> dict[str, str]:
    """Infer user preferences from the text (e.g. monitoring type, DAW preference)."""
    prefs: dict[str, str] = {}
    for pattern, key, value in _PREFERENCE_HINTS:
        if pattern.search(text) and key not in prefs:
            prefs[key] = value
    genre = infer_genre(text)
    if genre:
        prefs["genre"] = genre
    creative_goal = _CREATIVE_GOAL_PATTERN.search(text)
    if creative_goal:
        prefs["creative_direction"] = re.sub(r"\s+", " ", creative_goal.group(1).strip().lower())
    return prefs


def skill_level_for_session(session_id: str = "") -> str:
    """Return the inferred skill level ("beginner"/"advanced"/"") for a session.

    Deliberately only returns an explicit prior self-description -- never guessed
    from a single message -- so a wrong guess can't calibrate the wrong tone for
    an entire session.
    """
    if not session_id:
        return ""
    state = load_session(session_id=session_id)
    return str((state.get("preferences") or {}).get("skill_level", ""))


# ---------------------------------------------------------------------------
# Main API — update session from a query+answer exchange
# ---------------------------------------------------------------------------


def update_session(
    query: str,
    answer: str,
    route: str = "",
    answer_mode: str = "",
    confidence: str = "medium",
    intent: str = "general",
    *,
    session_id: str = "",
    extra_topics: list[str] | None = None,
    retrieved_results: list | None = None,
) -> dict[str, Any]:
    """Update session memory with the latest exchange.

    Call this after generating an answer, before returning the payload.
    Accepts an optional session_id for multi-session persistence.
    Returns the updated session state.
    """
    state = load_session(session_id=session_id)
    now = int(time.time())

    # First-time setup — always preserve an explicit session_id
    if not state.get("created_at"):
        state["created_at"] = now
        state["session_id"] = session_id or str(uuid.uuid4())[:8]
    elif session_id:
        state["session_id"] = session_id

    # Update turn tracking
    state["turn_count"] = int(state.get("turn_count", 0)) + 1
    state["followup_count"] = int(state.get("followup_count", 0)) + 1
    state["last_updated"] = now

    # Store the last query + answer summaries
    state["last_question"] = query[:500]
    state["last_answer"] = answer[:1000]
    state["last_route"] = route
    state["last_answer_mode"] = answer_mode
    state["last_confidence"] = confidence
    state["last_intent"] = intent

    if retrieved_results is not None:
        state["last_retrieved_results"] = retrieved_results

    # Extract and accumulate topics
    combined = f"{query} {answer}"
    new_topics = extra_topics or _extract_common_topics(query)
    existing_topics = list(state.get("topics_mentioned", []))
    for t in new_topics:
        if t not in existing_topics:
            existing_topics.append(t)
    state["topics_mentioned"] = existing_topics[-MAX_HISTORY:]

    # Extract and accumulate techniques
    new_techniques = extract_techniques(combined)
    existing_techniques = list(state.get("techniques_mentioned", []))
    for t in new_techniques:
        if t not in existing_techniques:
            existing_techniques.append(t)
    state["techniques_mentioned"] = existing_techniques[-MAX_HISTORY:]

    # Extract track names from the user's own words only -- found live-testing
    # 2026-08-03 that scanning `combined` (query + generated answer) picked up
    # every generic instrument word KENN's own explanatory prose happened to
    # use (e.g. "such as a bass synth, drum loop, or pad" from an unrelated
    # answer), producing a session summary like "tracks like the track,
    # vocal, vocals" that had nothing to do with what the user was actually
    # working on.
    new_tracks = extract_track_names(query)
    existing_tracks = list(state.get("track_names", []))
    for t in new_tracks:
        if t not in existing_tracks:
            existing_tracks.append(t)
    state["track_names"] = existing_tracks[-MAX_HISTORY:]

    # Extract project name
    project = extract_project_name(combined)
    if project:
        state["current_project"] = project

    # Infer preferences (merge, don't replace)
    # Preferences are facts about the user and must only come from the user's
    # own words.  Parsing generated answer text here used to let KENN's
    # generic examples become remembered as a monitoring/genre preference.
    prefs = infer_preferences(query)
    existing_prefs = dict(state.get("preferences", {}))
    existing_prefs.update(prefs)
    state["preferences"] = existing_prefs

    # Preserve only user-reported troubleshooting outcomes.  This is not
    # hidden reasoning: it records that a named technique helped or did not
    # help, so the next diagnostic answer can select an untried test.
    try:
        from kenn.core.diagnostic_state import update as update_diagnostic_state
        diagnostic_state = update_diagnostic_state(state, query)
        if diagnostic_state:
            state["diagnostic_state"] = diagnostic_state

    except Exception:
        pass
    save_session(state)

    # Sync with Thursday Episodic & Semantic Memory Graph
    try:
        from thursday.memory.memory_manager import get_memory_manager
        mm = get_memory_manager()
        entities = {}
        if state.get("current_project"):
            entities["project_name"] = state["current_project"]
        mm.remember_turn(
            session_id=state["session_id"],
            user_text=query,
            assistant_response=answer,
            intent=intent,
            service_used=f"kenn:{route}:{answer_mode}",
            entities=entities,
        )
    except Exception:
        pass

    return state


def _extract_common_topics(query: str) -> list[str]:
    """Extract common audio engineering topics from a query."""
    lowered = query.lower()
    topics: list[str] = []
    topic_map: list[tuple[str, str]] = [
        ("vocal", "vocals"),
        ("mix", "mixing"),
        ("master", "mastering"),
        ("eq", "EQ"),
        ("compressor", "compression"),
        ("bass", "bass"),
        ("kick", "drums"),
        ("snare", "drums"),
        ("drum", "drums"),
        ("reverb", "reverb"),
        ("delay", "delay"),
        ("warp", "warping"),
        ("ableton", "Ableton"),
        ("live", "Ableton Live"),
        ("midi", "MIDI"),
        ("audio clip", "audio clips"),
        ("routing", "routing"),
        ("send", "sends"),
        ("return track", "return tracks"),
        ("sidechain", "sidechaining"),
        ("gain stage", "gain staging"),
        ("loudness", "loudness"),
        ("lufs", "loudness"),
        ("true peak", "true peak"),
        ("monitor", "monitoring"),
        ("headphone", "headphones"),
        ("translation", "translation"),
        ("game audio", "game_audio"),
        ("wwise", "Wwise"),
        ("game", "game_audio"),
        ("client", "client delivery"),
        ("delivery", "client delivery"),
        ("stem", "stems"),
        ("podcast", "dialogue"),
        ("dialogue", "dialogue"),
        ("voice", "vocals"),
        ("studio", "studio setup"),
        ("room", "room acoustics"),
        ("acoustic", "room acoustics"),
        ("plugin", "plugins"),
        ("vst", "plugins"),
        ("tuning", "tuning"),
        ("automation", "automation"),
        ("arrangement", "arrangement"),
        ("compos", "composition"),
        ("creativ", "creative"),
        ("effect", "effects"),
        ("sound design", "sound design"),
        ("hi hat", "drums"),
        ("cymbals", "drums"),
        ("overheads", "drums"),
        ("808", "bass"),
        ("sub", "bass"),
        ("low end", "low end"),
        ("low mid", "low mids"),
        ("high end", "high end"),
        ("presence", "presence"),
        ("air", "air frequencies"),
        ("clarity", "clarity"),
        ("punch", "punch"),
        ("warmth", "warmth"),
        ("width", "stereo width"),
        ("stereo", "stereo width"),
        ("mono", "mono compatibility"),
        ("phase", "phase"),
        ("clipping", "clipping"),
    ]
    seen: set[str] = set()
    for keyword, topic in topic_map:
        if keyword in lowered and topic not in seen:
            topics.append(topic)
            seen.add(topic)
    return topics


# ---------------------------------------------------------------------------
# Context builder — inject session memory into the answer
# ---------------------------------------------------------------------------


def build_session_context(state: dict[str, Any] | None = None, *, session_id: str = "") -> str:
    """Build a context string about the session history.

    Returns a short string like:
    "Earlier you were asking about fixing muddy vocals and trying high-pass filtering.
     You mentioned the kick and snare. Let me know how that went."

    Returns empty string if there's no meaningful history.
    """
    if state is None:
        state = load_session(session_id=session_id)

    turn_count = int(state.get("turn_count", 0))
    if turn_count < 2:
        return ""

    parts: list[str] = []
    last_q = str(state.get("last_question", "")).strip()

    # What we last talked about
    topics = list(state.get("topics_mentioned", []))
    techniques = list(state.get("techniques_mentioned", []))
    tracks = list(state.get("track_names", []))
    project = str(state.get("current_project", "")).strip()
    creative_direction = str((state.get("preferences") or {}).get("creative_direction") or "").strip()

    # Build a "previously on" line. topics_mentioned/techniques_mentioned are
    # populated by separate extractors that can both tag the same word (e.g.
    # "warping" as both a topic and a technique) -- track everything already
    # used so it isn't repeated verbatim later in the same sentence.
    previous_parts: list[str] = []
    already_mentioned: set[str] = set()

    if project:
        previous_parts.append(f"the {project} project")

    if tracks:
        track_str = ", ".join(tracks[:3])
        previous_parts.append(f"track{'s' if len(tracks) > 1 else ''} like {track_str}")
        already_mentioned.update(t.lower() for t in tracks[:3])

    techniques = [t for t in techniques if t.lower() not in already_mentioned]
    if techniques:
        if len(techniques) <= 2:
            tech_str = " and ".join(techniques[:2])
        else:
            tech_str = ", ".join(techniques[:3])
        previous_parts.append(f"techniques like {tech_str}")
        already_mentioned.update(t.lower() for t in techniques[:3])

    topics = [t for t in topics if t.lower() not in already_mentioned]
    if topics:
        topic_str = ", ".join(topics[:3])
        previous_parts.append(f"topics around {topic_str}")

    if previous_parts:
        context = "Earlier, we were discussing " + ", ".join(previous_parts[:3]) + "."
        parts.append(context)
    elif last_q:
        # Fall back: mention the last question indirectly
        short_q = last_q[:60].rstrip("?.")
        parts.append(f"Last time you asked about {short_q}.")

    if creative_direction:
        parts.append(f"Your stated creative direction is {creative_direction}; that is a preference, not a technical fault to optimise automatically.")

    # Add a follow-up prompt
    last_confidence = str(state.get("last_confidence", "")).strip()
    last_answer_mode = str(state.get("last_answer_mode", "")).strip()

    if last_answer_mode == "mix_diagnosis" and last_confidence in {"high", "medium"}:
        parts.append("Did that change help the symptom?")
    elif last_answer_mode == "ableton_steps":
        parts.append("Did you get a chance to try that Live workflow?")
    elif last_answer_mode == "quick_fix":
        parts.append("Did that quick move do what you needed?")

    if not parts:
        return ""

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Session info for the answer payload — lightweight
# ---------------------------------------------------------------------------


def session_info(state: dict[str, Any] | None = None, *, session_id: str = "") -> dict[str, Any]:
    """Return a compact session info dict for inclusion in the answer payload."""
    if state is None:
        state = load_session(session_id=session_id)
    return {
        "session_id": state.get("session_id", ""),
        "turn_count": state.get("turn_count", 0),
        "topics_mentioned": state.get("topics_mentioned", [])[-5:],
        "techniques_mentioned": state.get("techniques_mentioned", [])[-5:],
        "track_names": state.get("track_names", [])[-5:],
        "current_project": state.get("current_project", ""),
        "last_question": state.get("last_question", "")[:200],
        "preferences": state.get("preferences", {}),
    }


def get_cross_session_trends() -> dict[str, Any]:
    """Mine SQLite session db to aggregate topic and technique frequency."""
    topic_counts: dict[str, int] = {}
    technique_counts: dict[str, int] = {}
    total_sessions = 0
    try:
        conn = _get_db()
        seven_days_ago = int(time.time()) - (7 * 24 * 3600)
        rows = conn.execute(
            "SELECT state FROM sessions WHERE updated_at >= ?", (seven_days_ago,)
        ).fetchall()
        
        if len(rows) < 3:
            rows = conn.execute("SELECT state FROM sessions").fetchall()
            
        for row in rows:
            try:
                state_data = json.loads(row["state"])
                total_sessions += 1
                for topic in state_data.get("topics_mentioned", []):
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1
                for tech in state_data.get("techniques_mentioned", []):
                    technique_counts[tech] = technique_counts.get(tech, 0) + 1
            except Exception:
                continue
    except Exception:
        pass
        
    top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_techniques = sorted(technique_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "ok": True,
        "total_sessions_analyzed": total_sessions,
        "topics": [{"topic": t, "count": c} for t, c in top_topics],
        "techniques": [{"technique": t, "count": c} for t, c in top_techniques],
    }


def save_mix_version(session_id: str, version_label: str, metrics: dict, repair_chain: dict) -> None:
    """Save a new mix version iteration snapshot to SQLite."""
    try:
        conn = _get_db()
        now = int(time.time())
        conn.execute(
            """INSERT INTO mix_versions (session_id, version_label, metrics_snapshot, repair_chain_applied, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id.strip(), version_label.strip(), json.dumps(metrics), json.dumps(repair_chain), now),
        )
        conn.commit()
    except (sqlite3.Error, OSError):
        pass


def list_mix_versions(session_id: str) -> list[dict[str, Any]]:
    """List version iteration history for a KENN session."""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, version_label, metrics_snapshot, repair_chain_applied, created_at FROM mix_versions WHERE session_id = ? ORDER BY created_at ASC",
            (session_id.strip(),),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "version_label": row["version_label"],
                "metrics": json.loads(row["metrics_snapshot"]),
                "repair_chain": json.loads(row["repair_chain_applied"]),
                "created_at": row["created_at"]
            }
            for row in rows
        ]
    except (sqlite3.Error, OSError):
        return []


def save_session_feedback(
    turn_id: str,
    explicit_rating: int | None = None,
    dwell_seconds: float | None = None,
    has_followup: bool | None = None,
    followup_interval_seconds: float | None = None,
    route: str | None = None,
    topics: list[str] | str | None = None,
) -> None:
    """Save or update engagement metrics for a KENN chat turn."""
    try:
        conn = _get_db()
        now_ts = int(time.time())
        # Check if record already exists
        row = conn.execute("SELECT id, explicit_rating, dwell_seconds, has_followup, followup_interval_seconds, route, topics FROM session_feedback WHERE turn_id = ?", (turn_id.strip(),)).fetchone()
        topics_str = json.dumps(topics) if isinstance(topics, list) else (topics if isinstance(topics, str) else None)
        if row:
            rating = explicit_rating if explicit_rating is not None else row["explicit_rating"]
            dwell = dwell_seconds if dwell_seconds is not None else row["dwell_seconds"]
            followup = has_followup if has_followup is not None else row["has_followup"]
            interval = followup_interval_seconds if followup_interval_seconds is not None else row["followup_interval_seconds"]
            db_route = route if route is not None else row["route"]
            db_topics = topics_str if topics_str is not None else row["topics"]
            conn.execute(
                """UPDATE session_feedback
                   SET explicit_rating = ?, dwell_seconds = ?, has_followup = ?, followup_interval_seconds = ?, route = ?, topics = ?
                   WHERE turn_id = ?""",
                (rating, dwell, followup, interval, db_route, db_topics, turn_id.strip()),
            )
        else:
            conn.execute(
                """INSERT INTO session_feedback (turn_id, explicit_rating, dwell_seconds, has_followup, followup_interval_seconds, route, topics, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    turn_id.strip(),
                    explicit_rating,
                    dwell_seconds,
                    has_followup,
                    followup_interval_seconds,
                    route,
                    topics_str,
                    now_ts,
                ),
            )
        conn.commit()
    except (sqlite3.Error, OSError) as e:
        print(f"Error saving session feedback: {e}")
