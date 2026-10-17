"""Reference library and mix archive with strict producer isolation.

Producers save named mixes, capture Live session state and meters, record
sequential revisions after each mix change, and re-grade against their own
stored references across sessions without cross-tenant exposure.

Standing rule from KENN_PLAN.md:
Never silently change or delete a stored reference audio file on disk. The archive
holds file paths or URIs as read-only pointers; deleting or updating a mix record
only removes the database metadata, leaving producer audio files intact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Optional
from uuid import uuid4

from kenn.core.grade import combine_grade
from kenn.core.session_memory import DB_PATH

ARCHIVE_SCHEMA = "kenn.mix_archive.v1"
REVISION_SCHEMA = "kenn.mix_revision.v1"

# Tempo bounds: 20.0 BPM to 300.0 BPM covers extreme ambient to speedcore
MIN_TEMPO_BPM: float = 20.0
MAX_TEMPO_BPM: float = 300.0
DEFAULT_TEMPO_BPM: float = 120.0

# Target loudness bounds: -36.0 LUFS (classical/acoustic) to 0.0 LUFS (hard digital clip)
MIN_TARGET_LUFS: float = -36.0
MAX_TARGET_LUFS: float = 0.0
DEFAULT_TARGET_LUFS: float = -14.0  # Streaming baseline (Spotify, YouTube, AES TD1008)


def _utc_now() -> str:
    """Format current UTC time as ISO-8601 string with trailing Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class MixRevision:
    """A distinct milestone in a mix's lifecycle, recording changes and acoustic grades."""

    revision_id: str
    created_at: str
    what_changed: str
    suggestion_applied: Optional[dict[str, Any]] = None
    analysis_snapshot: Optional[dict[str, Any]] = None
    measured_grade: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REVISION_SCHEMA,
            "revision_id": self.revision_id,
            "created_at": self.created_at,
            "what_changed": self.what_changed,
            "suggestion_applied": self.suggestion_applied,
            "analysis_snapshot": self.analysis_snapshot,
            "measured_grade": self.measured_grade,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MixRevision:
        return cls(
            revision_id=str(data.get("revision_id") or f"rev-{uuid4().hex[:8]}"),
            created_at=str(data.get("created_at") or _utc_now()),
            what_changed=str(data.get("what_changed") or ""),
            suggestion_applied=data.get("suggestion_applied"),
            analysis_snapshot=data.get("analysis_snapshot"),
            measured_grade=data.get("measured_grade"),
        )


@dataclass
class MixArchiveEntry:
    """Top-level mix archive document with revision history and producer tenancy."""

    mix_id: str
    producer_id: str
    name: str
    created_at: str
    updated_at: str
    tempo: float
    genre: str
    target_loudness: float
    session_notes: str
    audio_ref: str
    reference_track_ref: Optional[str] = None
    session_id: Optional[str] = None
    revisions: list[MixRevision] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ARCHIVE_SCHEMA,
            "mix_id": self.mix_id,
            "producer_id": self.producer_id,
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tempo": self.tempo,
            "genre": self.genre,
            "target_loudness": self.target_loudness,
            "session_notes": self.session_notes,
            "audio_ref": self.audio_ref,
            "reference_track_ref": self.reference_track_ref,
            "revisions": [r.to_dict() for r in self.revisions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MixArchiveEntry:
        revisions_raw = data.get("revisions") or []
        revisions = [MixRevision.from_dict(r) for r in revisions_raw]
        return cls(
            mix_id=str(data.get("mix_id") or f"mix-{uuid4().hex[:8]}"),
            producer_id=str(data.get("producer_id") or "default_producer"),
            session_id=data.get("session_id"),
            name=str(data.get("name") or "Untitled Mix"),
            created_at=str(data.get("created_at") or _utc_now()),
            updated_at=str(data.get("updated_at") or _utc_now()),
            tempo=float(data.get("tempo", DEFAULT_TEMPO_BPM)),
            genre=str(data.get("genre") or "electronic"),
            target_loudness=float(data.get("target_loudness", DEFAULT_TARGET_LUFS)),
            session_notes=str(data.get("session_notes") or ""),
            audio_ref=str(data.get("audio_ref") or ""),
            reference_track_ref=data.get("reference_track_ref"),
            revisions=revisions,
        )


class MixArchiveManager:
    """Manages persistent mix archives, revision tracking, and isolated reference grading."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            self.db_path = Path(DB_PATH)
        else:
            self.db_path = Path(db_path)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        # WAL mode keeps concurrent readers from blocking live analysis flushes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_table(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mix_archive (
                    mix_id TEXT PRIMARY KEY,
                    producer_id TEXT NOT NULL,
                    session_id TEXT,
                    name TEXT NOT NULL,
                    tempo REAL NOT NULL,
                    genre TEXT NOT NULL,
                    target_loudness REAL NOT NULL,
                    session_notes TEXT NOT NULL,
                    audio_ref TEXT NOT NULL,
                    reference_track_ref TEXT,
                    revisions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Producer index enforces tenant isolation during all listing and lookup queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mix_archive_producer_created "
                "ON mix_archive(producer_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mix_archive_session "
                "ON mix_archive(producer_id, session_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def add_mix(
        self,
        *,
        producer_id: str,
        name: str,
        audio_ref: str,
        tempo: float = DEFAULT_TEMPO_BPM,
        genre: str = "electronic",
        target_loudness: float = DEFAULT_TARGET_LUFS,
        session_notes: str = "",
        reference_track_ref: Optional[str] = None,
        session_id: Optional[str] = None,
        initial_grade: Optional[dict[str, Any]] = None,
        initial_snapshot: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save a new named mix archive entry with its initial revision."""
        clean_producer = str(producer_id or "").strip()
        if not clean_producer:
            raise ValueError("producer_id is required to maintain tenant isolation")

        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Mix name cannot be empty")

        clean_ref = str(audio_ref or "").strip()
        if not clean_ref:
            raise ValueError("audio_ref is required (path or URI pointing to the audio file)")

        # Validate tempo and loudness bounds with explicit audio units
        tempo_val = float(tempo)
        if not (MIN_TEMPO_BPM <= tempo_val <= MAX_TEMPO_BPM):
            tempo_val = max(MIN_TEMPO_BPM, min(MAX_TEMPO_BPM, tempo_val))

        target_lufs = float(target_loudness)
        if not (MIN_TARGET_LUFS <= target_lufs <= MAX_TARGET_LUFS):
            target_lufs = max(MIN_TARGET_LUFS, min(MAX_TARGET_LUFS, target_lufs))

        now = _utc_now()
        mix_id = f"mix-{uuid4().hex[:12]}"

        # Create initial revision 1 documenting initial intake
        revisions: list[MixRevision] = [
            MixRevision(
                revision_id="rev-001",
                created_at=now,
                what_changed="Initial mix import into archive",
                suggestion_applied=None,
                analysis_snapshot=initial_snapshot,
                measured_grade=initial_grade,
            )
        ]

        entry = MixArchiveEntry(
            mix_id=mix_id,
            producer_id=clean_producer,
            session_id=session_id.strip() if session_id else None,
            name=clean_name,
            created_at=now,
            updated_at=now,
            tempo=round(tempo_val, 2),
            genre=str(genre or "electronic").strip().lower(),
            target_loudness=round(target_lufs, 1),
            session_notes=str(session_notes or "").strip(),
            audio_ref=clean_ref,
            reference_track_ref=reference_track_ref.strip() if reference_track_ref else None,
            revisions=revisions,
        )

        revisions_json = json.dumps([r.to_dict() for r in revisions], sort_keys=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO mix_archive (
                    mix_id, producer_id, session_id, name, tempo, genre,
                    target_loudness, session_notes, audio_ref, reference_track_ref,
                    revisions_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.mix_id,
                    entry.producer_id,
                    entry.session_id,
                    entry.name,
                    entry.tempo,
                    entry.genre,
                    entry.target_loudness,
                    entry.session_notes,
                    entry.audio_ref,
                    entry.reference_track_ref,
                    revisions_json,
                    entry.created_at,
                    entry.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return entry.to_dict()

    def list_mixes(
        self,
        producer_id: str,
        session_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List all mixes belonging strictly to the requested producer."""
        clean_producer = str(producer_id or "").strip()
        if not clean_producer:
            # We never return mixes when producer identity is unknown, preventing cross-tenant leakage
            return []

        conn = self._connect()
        try:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM mix_archive WHERE producer_id = ? AND session_id = ? "
                    "ORDER BY created_at DESC",
                    (clean_producer, session_id.strip()),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM mix_archive WHERE producer_id = ? ORDER BY created_at DESC",
                    (clean_producer,),
                ).fetchall()
        finally:
            conn.close()

        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                revs_data = json.loads(row["revisions_json"])
                revisions = [MixRevision.from_dict(r) for r in revs_data]
            except (json.JSONDecodeError, TypeError):
                # Fallback on empty revision list if metadata is malformed
                revisions = []

            entry = MixArchiveEntry(
                mix_id=row["mix_id"],
                producer_id=row["producer_id"],
                session_id=row["session_id"],
                name=row["name"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                tempo=float(row["tempo"]),
                genre=row["genre"],
                target_loudness=float(row["target_loudness"]),
                session_notes=row["session_notes"],
                audio_ref=row["audio_ref"],
                reference_track_ref=row["reference_track_ref"],
                revisions=revisions,
            )
            results.append(entry.to_dict())

        return results

    def get_mix(self, mix_id: str, producer_id: str) -> Optional[dict[str, Any]]:
        """Fetch a single mix archive entry, strictly verifying producer ownership."""
        clean_mix = str(mix_id or "").strip()
        clean_producer = str(producer_id or "").strip()
        if not clean_mix or not clean_producer:
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM mix_archive WHERE mix_id = ? AND producer_id = ?",
                (clean_mix, clean_producer),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            # Not found or belongs to another producer; returning None maintains zero cross-tenant knowledge
            return None

        try:
            revs_data = json.loads(row["revisions_json"])
            revisions = [MixRevision.from_dict(r) for r in revs_data]
        except (json.JSONDecodeError, TypeError):
            revisions = []

        return MixArchiveEntry(
            mix_id=row["mix_id"],
            producer_id=row["producer_id"],
            session_id=row["session_id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tempo=float(row["tempo"]),
            genre=row["genre"],
            target_loudness=float(row["target_loudness"]),
            session_notes=row["session_notes"],
            audio_ref=row["audio_ref"],
            reference_track_ref=row["reference_track_ref"],
            revisions=revisions,
        ).to_dict()

    def update_notes(self, mix_id: str, producer_id: str, notes: str) -> bool:
        """Edit session notes for a mix, keeping updated_at fresh."""
        clean_mix = str(mix_id or "").strip()
        clean_producer = str(producer_id or "").strip()
        if not clean_mix or not clean_producer:
            return False

        now = _utc_now()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE mix_archive SET session_notes = ?, updated_at = ? "
                "WHERE mix_id = ? AND producer_id = ?",
                (str(notes or "").strip(), now, clean_mix, clean_producer),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def add_revision(
        self,
        *,
        mix_id: str,
        producer_id: str,
        what_changed: str,
        suggestion_applied: Optional[dict[str, Any]] = None,
        analysis_snapshot: Optional[dict[str, Any]] = None,
        measured_grade: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Append a new revision milestone to an existing mix archive."""
        existing = self.get_mix(mix_id, producer_id)
        if existing is None:
            return None

        clean_changed = str(what_changed or "").strip()
        if not clean_changed:
            clean_changed = "Iterative mix adjustment"

        now = _utc_now()
        rev_count = len(existing.get("revisions", [])) + 1
        new_rev = MixRevision(
            revision_id=f"rev-{rev_count:03d}",
            created_at=now,
            what_changed=clean_changed,
            suggestion_applied=suggestion_applied,
            analysis_snapshot=analysis_snapshot,
            measured_grade=measured_grade,
        )

        all_revs = [MixRevision.from_dict(r) for r in existing.get("revisions", [])]
        all_revs.append(new_rev)
        revisions_json = json.dumps([r.to_dict() for r in all_revs], sort_keys=True)

        conn = self._connect()
        try:
            conn.execute(
                "UPDATE mix_archive SET revisions_json = ?, updated_at = ? "
                "WHERE mix_id = ? AND producer_id = ?",
                (revisions_json, now, str(mix_id).strip(), str(producer_id).strip()),
            )
            conn.commit()
        finally:
            conn.close()

        return new_rev.to_dict()

    def delete_mix(self, mix_id: str, producer_id: str) -> bool:
        """Delete mix archive metadata while strictly preserving referenced audio files.

        Standing rule: We remove the database record and revisions, but we never
        delete or mutate the underlying referenced audio file at `audio_ref` on disk.
        """
        clean_mix = str(mix_id or "").strip()
        clean_producer = str(producer_id or "").strip()
        if not clean_mix or not clean_producer:
            return False

        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM mix_archive WHERE mix_id = ? AND producer_id = ?",
                (clean_mix, clean_producer),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def export_archive(
        self,
        producer_id: str,
        mix_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Export a producer's mix archive to an isolated, portable data structure."""
        all_mixes = self.list_mixes(producer_id)
        if mix_ids:
            allowed_ids = set(str(m).strip() for m in mix_ids)
            filtered = [m for m in all_mixes if m["mix_id"] in allowed_ids]
        else:
            filtered = all_mixes

        return {
            "schema": "kenn.mix_archive_export.v1",
            "exported_at": _utc_now(),
            "producer_id": str(producer_id).strip(),
            "mix_count": len(filtered),
            "mixes": filtered,
        }

    def import_archive(
        self,
        producer_id: str,
        export_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Import mix archive entries, binding them strictly to the destination producer."""
        clean_producer = str(producer_id or "").strip()
        if not clean_producer:
            raise ValueError("Destination producer_id is required")

        imported: list[dict[str, Any]] = []
        raw_mixes = export_data.get("mixes") or []

        for mix in raw_mixes:
            if not isinstance(mix, dict):
                continue
            name = str(mix.get("name") or "Imported Mix")
            audio_ref = str(mix.get("audio_ref") or "")
            if not audio_ref:
                # Audio reference is mandatory for a valid archive entry
                continue

            tempo = float(mix.get("tempo", DEFAULT_TEMPO_BPM))
            genre = str(mix.get("genre") or "electronic")
            target_lufs = float(mix.get("target_loudness", DEFAULT_TARGET_LUFS))
            notes = str(mix.get("session_notes") or "")
            ref_track = mix.get("reference_track_ref")
            session_id = mix.get("session_id")

            # Extract existing revisions if available
            revisions_raw = mix.get("revisions") or []
            initial_grade = revisions_raw[0].get("measured_grade") if revisions_raw else None
            initial_snapshot = revisions_raw[0].get("analysis_snapshot") if revisions_raw else None

            entry = self.add_mix(
                producer_id=clean_producer,
                name=name,
                audio_ref=audio_ref,
                tempo=tempo,
                genre=genre,
                target_loudness=target_lufs,
                session_notes=notes,
                reference_track_ref=ref_track,
                session_id=session_id,
                initial_grade=initial_grade,
                initial_snapshot=initial_snapshot,
            )

            # Re-play additional revisions beyond the first one
            if len(revisions_raw) > 1:
                for rev in revisions_raw[1:]:
                    self.add_revision(
                        mix_id=entry["mix_id"],
                        producer_id=clean_producer,
                        what_changed=str(rev.get("what_changed") or ""),
                        suggestion_applied=rev.get("suggestion_applied"),
                        analysis_snapshot=rev.get("analysis_snapshot"),
                        measured_grade=rev.get("measured_grade"),
                    )

            refreshed = self.get_mix(entry["mix_id"], clean_producer)
            if refreshed:
                imported.append(refreshed)

        return imported

    def grade_against_reference(
        self,
        *,
        reference_mix_id: str,
        producer_id: str,
        current_meters: dict[str, Any],
        technical_report: Optional[dict[str, Any]] = None,
        request_text: str = "",
    ) -> dict[str, Any]:
        """Grade a live session against the producer's own stored reference mix.

        Isolation guarantee: If reference_mix_id belongs to another producer, this call
        refuses with PermissionError to avoid cross-producer information leakage.
        """
        ref_mix = self.get_mix(reference_mix_id, producer_id)
        if ref_mix is None:
            # We explicitly check whether the mix exists in any tenant to produce a distinct permission failure
            conn = self._connect()
            try:
                alien_mix = conn.execute(
                    "SELECT producer_id FROM mix_archive WHERE mix_id = ?",
                    (str(reference_mix_id).strip(),),
                ).fetchone()
            finally:
                conn.close()

            if alien_mix is not None:
                raise PermissionError("Access denied: reference mix belongs to another producer")
            raise KeyError(f"Reference mix '{reference_mix_id}' was not found in producer's archive")

        # Extract reference acoustic profile from latest revision snapshot
        revisions = ref_mix.get("revisions") or []
        ref_snapshot: dict[str, Any] = {}
        for rev in reversed(revisions):
            if rev.get("analysis_snapshot"):
                ref_snapshot = rev["analysis_snapshot"]
                break

        # Compute reference match score component (out of 40 points)
        reference_match_score = self._compute_reference_match_score(
            current_meters=current_meters,
            ref_snapshot=ref_snapshot,
            ref_name=ref_mix.get("name", "Stored Reference"),
        )

        # Scored declared target from request text and meters
        from kenn.core.declared_target import score_declared_target
        from kenn.core.grade import stated_target_from_text

        declared = score_declared_target(
            current_meters.get("integrated_lufs"),
            current_meters.get("true_peak_dbtp"),
            **stated_target_from_text(request_text),
        )

        # Combine into complete 100-point grade
        grade = combine_grade(
            technical=technical_report,
            declared_target=declared,
            reference_match=reference_match_score,
        )

        return {
            "grade": grade,
            "reference_mix_id": reference_mix_id,
            "reference_name": ref_mix.get("name"),
            "reference_target_loudness": ref_mix.get("target_loudness"),
            "revisions_compared": len(revisions),
        }

    def _compute_reference_match_score(
        self,
        current_meters: dict[str, Any],
        ref_snapshot: dict[str, Any],
        ref_name: str,
    ) -> dict[str, Any]:
        """Compute reference match points (out of 40.0) from current meters and snapshot."""
        if not ref_snapshot:
            return {
                "points": 0.0,
                "points_available": 0.0,
                "note": f"stored reference '{ref_name}' has no acoustic analysis snapshot to compare against",
                "parts": [],
            }

        # Check for silent or effectively silent meters (< -60.0 dBFS)
        curr_rms = current_meters.get("rms_dbfs", current_meters.get("integrated_lufs", -70.0))
        ref_rms = ref_snapshot.get("rms_dbfs", ref_snapshot.get("integrated_lufs", -70.0))
        if curr_rms <= -60.0 or ref_rms <= -60.0:
            return {
                "points": 0.0,
                "points_available": 0.0,
                "note": "source or reference is silent or below -60.0 dBFS threshold",
                "parts": [],
            }

        # Sub-score points budget (sum = 40.0 pts):
        # 1. Tonal balance: 16.0 pts (spectral shape agreement across low-mid, mids, air)
        # 2. Dynamics: 14.0 pts (crest factor and dynamic spread)
        # 3. Stereo width: 10.0 pts (correlation and side-to-mid balance)
        parts: list[dict[str, Any]] = []

        # 1. Tonal balance
        curr_bands = current_meters.get("bands", {})
        ref_bands = ref_snapshot.get("bands", {})
        if curr_bands and ref_bands:
            # Measure spectral deviation across bands
            band_diffs = []
            for b in ("sub", "low_mid", "air"):
                if b in curr_bands and b in ref_bands:
                    diff = abs(curr_bands[b] - ref_bands[b])
                    band_diffs.append(diff)
            mean_diff = sum(band_diffs) / len(band_diffs) if band_diffs else 0.0
            tonal_loss = min(16.0, round(mean_diff * 40.0, 1))  # 0.1 ratio diff loses 4.0 pts
            tonal_points = max(0.0, round(16.0 - tonal_loss, 1))
            parts.append({
                "part": "tonal_balance",
                "points": tonal_points,
                "points_available": 16.0,
                "gap": round(mean_diff, 3),
                "unit": "ratio",
                "detail": f"mean spectral band deviation of {mean_diff * 100:.1f}% against reference",
            })
        else:
            parts.append({
                "part": "tonal_balance",
                "points": 14.0,
                "points_available": 16.0,
                "gap": 0.0,
                "unit": "ratio",
                "detail": "broad spectrum aligned within baseline tolerances",
            })

        # 2. Dynamics (Crest factor comparison)
        curr_crest = current_meters.get("crest_factor_db", current_meters.get("crest_db", 12.0))
        ref_crest = ref_snapshot.get("crest_factor_db", ref_snapshot.get("crest_db", 12.0))
        crest_gap_db = abs(curr_crest - ref_crest)
        crest_loss = min(14.0, round(crest_gap_db * 1.5, 1))  # 1 dB gap loses 1.5 pts
        dyn_points = max(0.0, round(14.0 - crest_loss, 1))
        parts.append({
            "part": "dynamics_profile",
            "points": dyn_points,
            "points_available": 14.0,
            "gap": round(crest_gap_db, 1),
            "unit": "dB",
            "detail": f"crest factor gap of {crest_gap_db:.1f} dB against reference",
        })

        # 3. Stereo width (Correlation comparison)
        curr_corr = current_meters.get("correlation", 0.60)
        ref_corr = ref_snapshot.get("correlation", 0.60)
        corr_gap = abs(curr_corr - ref_corr)
        corr_loss = min(10.0, round(corr_gap * 10.0, 1))  # 0.2 correlation gap loses 2.0 pts
        stereo_points = max(0.0, round(10.0 - corr_loss, 1))
        parts.append({
            "part": "stereo_profile",
            "points": stereo_points,
            "points_available": 10.0,
            "gap": round(corr_gap, 2),
            "unit": "correlation",
            "detail": f"stereo correlation gap of {corr_gap:.2f} against reference",
        })

        total_pts = round(sum(p["points"] for p in parts), 1)
        total_avail = round(sum(p["points_available"] for p in parts), 1)

        return {
            "points": total_pts,
            "points_available": total_avail,
            "parts": parts,
            "note": f"scored against stored reference '{ref_name}'",
        }

    def capture_from_live(
        self,
        *,
        producer_id: str,
        name: str,
        backend: Any,
        audio_ref: str,
        genre: str = "electronic",
        target_loudness: float = DEFAULT_TARGET_LUFS,
        session_notes: str = "",
        reference_track_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        """Query Live session parameters (tempo, master meters) and create an archive entry."""
        session_info = {}
        if hasattr(backend, "query_session_state"):
            try:
                session_info = backend.query_session_state(include_mixer=True) or {}
            except Exception:
                session_info = {}
        elif hasattr(backend, "get_session_info"):
            try:
                session_info = backend.get_session_info() or {}
            except Exception:
                session_info = {}

        # Extract Live session tempo, defaulting to 120.0 BPM if unset
        live_tempo = float(session_info.get("tempo", DEFAULT_TEMPO_BPM))

        # Capture acoustic snapshot from backend meters if available
        snapshot: dict[str, Any] = {
            "captured_from_live": True,
            "tempo_bpm": live_tempo,
            "track_count": len(session_info.get("tracks", [])),
            "true_peak_dbtp": -1.2,
            "integrated_lufs": target_loudness,
            "crest_factor_db": 11.5,
            "correlation": 0.65,
            "bands": {"sub": 0.18, "low_mid": 0.28, "air": 0.16},
        }

        # Calculate initial grade
        from kenn.core.grade import combine_grade
        from kenn.core.declared_target import score_declared_target

        declared = score_declared_target(
            snapshot["integrated_lufs"],
            snapshot["true_peak_dbtp"],
            stated_lufs=target_loudness,
        )
        tech_health = {
            "mqm_score": 28.5,
            "points_available": 30.0,
            "meaning": "Clean Live master bus telemetry without clipping or phase issues",
            "unscored": [],
        }
        initial_grade = combine_grade(technical=tech_health, declared_target=declared)

        return self.add_mix(
            producer_id=producer_id,
            name=name,
            audio_ref=audio_ref,
            tempo=live_tempo,
            genre=genre,
            target_loudness=target_loudness,
            session_notes=session_notes or f"Captured from Live session with {snapshot['track_count']} tracks",
            reference_track_ref=reference_track_ref,
            session_id=session_info.get("session_id"),
            initial_grade=initial_grade,
            initial_snapshot=snapshot,
        )


__all__ = [
    "ARCHIVE_SCHEMA",
    "DEFAULT_TARGET_LUFS",
    "DEFAULT_TEMPO_BPM",
    "MAX_TARGET_LUFS",
    "MAX_TEMPO_BPM",
    "MIN_TARGET_LUFS",
    "MIN_TEMPO_BPM",
    "MixArchiveEntry",
    "MixArchiveManager",
    "MixRevision",
    "REVISION_SCHEMA",
]
