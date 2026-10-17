"""Structured mixing curriculum and pedagogical progression for KENN (Milestone E8).

Keeps a formal mixing curriculum completely separate from ad-hoc producer questions:
- Defines structured curriculum topics (spectral clarity, low-end control, peak headroom,
  stereo correlation, dynamic snap) with measurable session objectives, starting grades,
  suggested action paths, and failure gap logging.
- Guarantees isolation: ad-hoc chat questions never mutate or corrupt curriculum state,
  and active curriculum sessions never block or interfere with normal answering.
- Tracks failed suggestions to identify producer skill gaps and guide follow-up learning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from uuid import uuid4

from kenn.core.grade import combine_grade
from kenn.core.session_memory import DB_PATH
from kenn.core.suggestion_levers import (
    AES_TD1008_RULE,
    CORRELATION_CONVENTION_RULE,
    EBU_TECH_3343_RULE,
    HOUSE_RULE,
    SPOTIFY_PEAK_RULE,
    WILSON_FAZENDA_RULE,
)

CURRICULUM_SCHEMA = "kenn.curriculum_session.v1"
OBJECTIVE_SCHEMA = "kenn.curriculum_objective.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class CurriculumObjective:
    """A concrete, verifiable mixing goal with numerical threshold and auditory guide."""

    topic_id: str
    title: str
    objective_description: str
    target_metric: str
    target_operator: str  # "<=", ">=", "<", ">"
    target_value: float
    unit: str
    suggested_steps: List[str]
    lesson_notes: str
    cited_standards: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": OBJECTIVE_SCHEMA,
            "topic_id": self.topic_id,
            "title": self.title,
            "objective_description": self.objective_description,
            "target_metric": self.target_metric,
            "target_operator": self.target_operator,
            "target_value": self.target_value,
            "unit": self.unit,
            "suggested_steps": self.suggested_steps,
            "lesson_notes": self.lesson_notes,
            "cited_standards": self.cited_standards,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CurriculumObjective:
        return cls(
            topic_id=str(data.get("topic_id", "general")),
            title=str(data.get("title", "Mixing Objective")),
            objective_description=str(data.get("objective_description", "")),
            target_metric=str(data.get("target_metric", "")),
            target_operator=str(data.get("target_operator", "<=")),
            target_value=float(data.get("target_value", 0.0)),
            unit=str(data.get("unit", "")),
            suggested_steps=list(data.get("suggested_steps", [])),
            lesson_notes=str(data.get("lesson_notes", "")),
            cited_standards=list(data.get("cited_standards", [])),
        )


@dataclass
class CurriculumSession:
    """An active pedagogical session tracking starting vs current grade and gaps."""

    session_id: str
    topic_id: str
    title: str
    objective: CurriculumObjective
    starting_meters: Dict[str, Any]
    starting_grade: Dict[str, Any]
    current_meters: Optional[Dict[str, Any]] = None
    current_grade: Optional[Dict[str, Any]] = None
    status: str = "in_progress"  # "in_progress", "completed", "paused", "abandoned"
    failed_suggestions_log: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": CURRICULUM_SCHEMA,
            "session_id": self.session_id,
            "topic_id": self.topic_id,
            "title": self.title,
            "objective": self.objective.to_dict(),
            "starting_meters": self.starting_meters,
            "starting_grade": self.starting_grade,
            "current_meters": self.current_meters,
            "current_grade": self.current_grade,
            "status": self.status,
            "failed_suggestions_log": self.failed_suggestions_log,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CurriculumSession:
        obj_raw = data.get("objective") or {}
        objective = CurriculumObjective.from_dict(obj_raw)
        return cls(
            session_id=str(data.get("session_id", "")),
            topic_id=str(data.get("topic_id", "")),
            title=str(data.get("title", "")),
            objective=objective,
            starting_meters=dict(data.get("starting_meters", {})),
            starting_grade=dict(data.get("starting_grade", {})),
            current_meters=data.get("current_meters"),
            current_grade=data.get("current_grade"),
            status=str(data.get("status", "in_progress")),
            failed_suggestions_log=list(data.get("failed_suggestions_log", [])),
            created_at=str(data.get("created_at", _utc_now())),
            updated_at=str(data.get("updated_at", _utc_now())),
            completed_at=data.get("completed_at"),
        )


# In-house authoring of standard pedagogical mixing curriculum catalog
CURRICULUM_CATALOG: Dict[str, CurriculumObjective] = {
    "spectral_clarity": CurriculumObjective(
        topic_id="spectral_clarity",
        title="Low-Mid De-Cluttering & Vocal Unmasking",
        objective_description="Tame energy in the 200-500 Hz band below 38.0% to unmask vocal presence and eliminate muddy boxiness.",
        target_metric="low_mid_energy_pct",
        target_operator="<=",
        target_value=38.0,  # 38.0% energy threshold from empirical mix review benchmark
        unit="%",
        suggested_steps=[
            "Identify accompanying mid instruments (bass body, electric guitar, synth pads, acoustic piano).",
            "Apply narrow parametric bell cuts (2.0 to 3.0 dB, Q approx 1.5) at the offending resonant center (250-400 Hz) on accompaniment tracks.",
            "Audition in mono to verify that the lead vocal steps forward without losing its fundamental warmth.",
        ],
        lesson_notes=(
            "The 200-500 Hz octave is where acoustic instruments store weight, but accumulative summing from multiple tracks "
            "creates severe boxy build-up. Through the psychoacoustic upward spread of masking, excessive low-mid energy directly "
            "degrades vocal intelligibility in the 1-3 kHz presence band."
        ),
        cited_standards=[HOUSE_RULE, WILSON_FAZENDA_RULE],
    ),
    "low_end_control": CurriculumObjective(
        topic_id="low_end_control",
        title="Sub Bass Containment & Kick Alignment",
        objective_description="Contain sub-bass (20-60 Hz) energy below 45.0% and establish clean phase alignment between kick and sub.",
        target_metric="sub_energy_pct",
        target_operator="<=",
        target_value=45.0,  # 45.0% sub energy ceiling
        unit="%",
        suggested_steps=[
            "High-pass filter all non-bass elements (guitars, vocals, cymbals, effects) between 40 Hz and 80 Hz with 12-18 dB/oct slopes.",
            "Decide which instrument anchors the deep sub octave (30-60 Hz): sub-bass body or kick fundamental.",
            "Carve a complementary frequency notch on the counterpart element or configure fast sidechain ducking.",
        ],
        lesson_notes=(
            "Frequencies below 60 Hz consume massive amplifier and digital headroom while conveying minimal pitch information. "
            "When sub energy exceeds 45.0%, master limiters trigger prematurely, squashing transients across the entire audible spectrum."
        ),
        cited_standards=[HOUSE_RULE, AES_TD1008_RULE],
    ),
    "loudness_and_peaks": CurriculumObjective(
        topic_id="loudness_and_peaks",
        title="Inter-Sample True Peak Headroom & Streaming Delivery",
        objective_description="Maintain true peak <= -1.0 dBTP (EBU Tech 3343 and Spotify delivery compliance) with zero inter-sample clipping.",
        target_metric="true_peak_dbtp",
        target_operator="<=",
        target_value=-1.0,  # -1.0 dBTP standard delivery ceiling
        unit="dBTP",
        suggested_steps=[
            "Audit master bus limiter ceiling; clamp to -1.0 dBTP (or -2.0 dBTP for hot masters louder than -14 LUFS).",
            "Pull down channel faders or sub-mix groups by 1.5 to 2.5 dB if the master bus is driving hard into limiting.",
            "Audition transient snare hits and kick punches on consumer DACs to verify zero crunchy clipping distortion.",
        ],
        lesson_notes=(
            "Digital D/A converters reconstruct continuous analog waveforms from discrete digital samples. Consecutive near-zero "
            "digital samples peak significantly higher in the analog domain. Intersample peaks exceeding -1.0 dBTP clip consumer DACs "
            "and distort when lossy encoders (AAC/MP3) process the stream."
        ),
        cited_standards=[EBU_TECH_3343_RULE, SPOTIFY_PEAK_RULE, AES_TD1008_RULE],
    ),
    "stereo_imaging": CurriculumObjective(
        topic_id="stereo_imaging",
        title="Mono Compatibility & Stereo Phase Correlation",
        objective_description="Achieve stereo correlation >= +0.50 with zero phase cancellation when collapsed to mono.",
        target_metric="correlation",
        target_operator=">=",
        target_value=0.50,  # 0.50 correlation threshold for mono compatibility
        unit="correlation",
        suggested_steps=[
            "Ensure low frequencies below 120 Hz remain mono-centered across all tracks.",
            "Check stereo chorus, widener plug-ins, and micro-pitch delays for excessive anti-phase side energy.",
            "Sum monitoring to mono and confirm that lead vocals, kick, and bass body do not hollow out or drop in volume.",
        ],
        lesson_notes=(
            "Stereo correlation measures phase agreement between left and right channels. Values below 0.0 mean left and right "
            "channels are in opposite polarity; when summed to mono on a phone speaker, bluetooth speaker, or club sound system, "
            "these signals destructively cancel and vanish."
        ),
        cited_standards=[CORRELATION_CONVENTION_RULE, HOUSE_RULE],
    ),
    "dynamic_control": CurriculumObjective(
        topic_id="dynamic_control",
        title="Crest Factor Preservation & Transient Snap",
        objective_description="Maintain a crest factor (peak-to-loudness ratio) of at least 6.0 dB to avoid choking transient punch.",
        target_metric="crest_factor_db",
        target_operator=">=",
        target_value=6.0,  # 6.0 dB crest factor floor
        unit="dB",
        suggested_steps=[
            "Audit compressor attack times on drums; slow attack to 15-30 ms to let initial transient spikes pass through unattenuated.",
            "Back off aggressive master limiter threshold settings.",
            "Employ sequential, gentle gain reduction across multiple stages rather than heavy compression on a single bus.",
        ],
        lesson_notes=(
            "Crest factor represents the dynamic headroom between peak transients and average RMS level. Over-compressing a mix "
            "below 6.0 dB squashes rhythmic punch, robs drums of dynamic impact, and causes listener ear fatigue."
        ),
        cited_standards=[HOUSE_RULE, AES_TD1008_RULE],
    ),
}


class MixCurriculumManager:
    """Manages active curriculum sessions, objective evaluation, and gap tracking."""

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
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_table(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS curriculum_sessions (
                    session_id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_curriculum_status "
                "ON curriculum_sessions(status, updated_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def list_catalog(self) -> List[Dict[str, Any]]:
        """Return all authored curriculum topics and objectives."""
        return [obj.to_dict() for obj in CURRICULUM_CATALOG.values()]

    def get_topic_objective(self, topic_id: str) -> Optional[CurriculumObjective]:
        """Fetch objective definition for a topic ID."""
        clean_id = str(topic_id or "").strip().lower()
        return CURRICULUM_CATALOG.get(clean_id)

    def start_lesson(
        self,
        *,
        session_id: str,
        topic_id: str,
        current_meters: Dict[str, Any],
        current_grade: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Start a curriculum session with a clear objective, starting grade, and suggested path."""
        clean_session = str(session_id or "").strip()[:128]
        if not clean_session:
            raise ValueError("session_id is required")

        clean_topic = str(topic_id or "").strip().lower()
        objective = self.get_topic_objective(clean_topic)
        if objective is None:
            raise KeyError(f"Curriculum topic '{clean_topic}' not found in catalog")

        now = _utc_now()
        # Default starting grade from technical health if not supplied
        if current_grade is None:
            tech_report = {
                "mqm_score": 20.0,
                "points_available": 30.0,
                "meaning": "Initial intake before curriculum lesson",
                "unscored": [],
            }
            starting_grade = combine_grade(technical=tech_report)
        else:
            starting_grade = current_grade

        session = CurriculumSession(
            session_id=clean_session,
            topic_id=clean_topic,
            title=objective.title,
            objective=objective,
            starting_meters=current_meters,
            starting_grade=starting_grade,
            current_meters=current_meters,
            current_grade=starting_grade,
            status="in_progress",
            failed_suggestions_log=[],
            created_at=now,
            updated_at=now,
        )

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO curriculum_sessions (
                    session_id, topic_id, status, state_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.topic_id,
                    session.status,
                    json.dumps(session.to_dict(), sort_keys=True),
                    session.created_at,
                    session.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return session.to_dict()

    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve active or completed curriculum session state."""
        clean_session = str(session_id or "").strip()[:128]
        if not clean_session:
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT state_json FROM curriculum_sessions WHERE session_id = ?",
                (clean_session,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        try:
            data = json.loads(row["state_json"])
            return CurriculumSession.from_dict(data).to_dict()
        except (json.JSONDecodeError, TypeError):
            return None

    def evaluate_progress(
        self,
        *,
        session_id: str,
        current_meters: Dict[str, Any],
        current_grade: Optional[Dict[str, Any]] = None,
        last_applied_lever: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Evaluate current mix telemetry against the active curriculum objective."""
        session_data = self.get_session_status(session_id)
        if session_data is None:
            return {"ok": False, "error": f"No active curriculum session found for session '{session_id}'"}

        session = CurriculumSession.from_dict(session_data)
        if session.status not in ("in_progress", "paused"):
            return {
                "ok": True,
                "status": session.status,
                "message": f"Curriculum session is already {session.status}",
                "session": session.to_dict(),
            }

        now = _utc_now()
        obj = session.objective
        metric_key = obj.target_metric
        measured_value = self._extract_metric_value(current_meters, metric_key)

        # Calculate grade progression
        start_pts = float(session.starting_grade.get("points", 0.0))
        curr_pts = float(current_grade.get("points", start_pts)) if current_grade else start_pts
        grade_delta = round(curr_pts - start_pts, 1)

        # Check objective condition
        objective_met = False
        gap_identified: Optional[str] = None

        if measured_value is not None:
            if obj.target_operator == "<=":
                objective_met = measured_value <= obj.target_value
                if not objective_met:
                    gap_excess = round(measured_value - obj.target_value, 2)
                    gap_identified = f"Target was {obj.target_value}{obj.unit}, but measured {measured_value}{obj.unit} ({gap_excess:+.1f}{obj.unit} excess)"
            elif obj.target_operator == ">=":
                objective_met = measured_value >= obj.target_value
                if not objective_met:
                    gap_deficit = round(obj.target_value - measured_value, 2)
                    gap_identified = f"Target was {obj.target_value}{obj.unit}, but measured {measured_value}{obj.unit} ({gap_deficit:.1f}{obj.unit} deficit)"
        else:
            gap_identified = f"Metric '{metric_key}' was not present in current analysis telemetry"

        session.current_meters = current_meters
        session.current_grade = current_grade or session.starting_grade
        session.updated_at = now

        feedback: str
        if objective_met:
            session.status = "completed"
            session.completed_at = now
            feedback = (
                f"Objective achieved: {obj.title}. "
                f"Measured {measured_value}{obj.unit} successfully met the {obj.target_operator} {obj.target_value}{obj.unit} target. "
                f"Grade score progressed by {grade_delta:+.1f} points (from {start_pts:.1f} to {curr_pts:.1f})."
            )
        else:
            feedback = (
                f"Objective in progress: {gap_identified}. "
                f"Suggested path: {' '.join(obj.suggested_steps)}"
            )
            # Log gap into failed suggestions log if an action was attempted
            if last_applied_lever or grade_delta < 0.0:
                session.failed_suggestions_log.append({
                    "timestamp": now,
                    "lever_applied": last_applied_lever,
                    "measured_value": measured_value,
                    "gap": gap_identified,
                    "grade_delta": grade_delta,
                })

        # Save updated curriculum state
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE curriculum_sessions
                SET status = ?, state_json = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    session.status,
                    json.dumps(session.to_dict(), sort_keys=True),
                    now,
                    session.session_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "ok": True,
            "objective_met": objective_met,
            "status": session.status,
            "metric_key": metric_key,
            "measured_value": measured_value,
            "target_value": obj.target_value,
            "unit": obj.unit,
            "grade_delta": grade_delta,
            "feedback": feedback,
            "gap_identified": gap_identified,
            "failed_suggestions_count": len(session.failed_suggestions_log),
            "session": session.to_dict(),
        }

    def _extract_metric_value(self, meters: Dict[str, Any], key: str) -> Optional[float]:
        """Extract named metric from meters dictionary."""
        if not meters:
            return None

        if key == "true_peak_dbtp":
            val = meters.get("true_peak_dbtp")
            return float(val) if isinstance(val, (int, float)) and math.isfinite(val) else None

        if key == "correlation":
            val = meters.get("correlation", meters.get("phase_correlation"))
            return float(val) if isinstance(val, (int, float)) and math.isfinite(val) else None

        if key == "crest_factor_db":
            val = meters.get("crest_factor_db", meters.get("crest_db"))
            return float(val) if isinstance(val, (int, float)) and math.isfinite(val) else None

        # Spectral percentage bands
        spec = meters.get("bands") or meters.get("spectral_energy") or {}
        if key == "low_mid_energy_pct":
            val = spec.get("low_mid", spec.get("low_mid_200_500hz"))
            return round(float(val) * 100.0, 1) if isinstance(val, (int, float)) and math.isfinite(val) else None

        if key == "sub_energy_pct":
            val = spec.get("sub", spec.get("sub_20_60hz"))
            return round(float(val) * 100.0, 1) if isinstance(val, (int, float)) and math.isfinite(val) else None

        if key == "air_energy_pct":
            val = spec.get("air", spec.get("air_10_20khz"))
            return round(float(val) * 100.0, 1) if isinstance(val, (int, float)) and math.isfinite(val) else None

        # Direct key lookup
        val = meters.get(key)
        return float(val) if isinstance(val, (int, float)) and math.isfinite(val) else None

    def pause_lesson(self, session_id: str) -> bool:
        """Pause active curriculum session."""
        return self._set_session_status(session_id, "paused")

    def resume_lesson(self, session_id: str) -> bool:
        """Resume paused curriculum session."""
        return self._set_session_status(session_id, "in_progress")

    def abandon_lesson(self, session_id: str) -> bool:
        """Abandon curriculum session."""
        return self._set_session_status(session_id, "abandoned")

    def _set_session_status(self, session_id: str, new_status: str) -> bool:
        clean_session = str(session_id or "").strip()[:128]
        if not clean_session:
            return False

        existing = self.get_session_status(clean_session)
        if existing is None:
            return False

        now = _utc_now()
        existing["status"] = new_status
        existing["updated_at"] = now

        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                UPDATE curriculum_sessions
                SET status = ?, state_json = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (new_status, json.dumps(existing, sort_keys=True), now, clean_session),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


__all__ = [
    "CURRICULUM_CATALOG",
    "CURRICULUM_SCHEMA",
    "CurriculumObjective",
    "CurriculumSession",
    "MixCurriculumManager",
    "OBJECTIVE_SCHEMA",
]
