from __future__ import annotations
from typing import Callable

from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

from agents.MixReview.revision_agent import update_step_status
from audio_analysis.integration.closed_loop import append_feedback_record
from db import connect
from audio_analysis.integration.handoff import kenn_handoff

try:
    from audio_analysis.mix_features import extract_feature_vector
    MIX_FEATURES_AVAILABLE = True
except ImportError:
    MIX_FEATURES_AVAILABLE = False


def metric_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


FEATURE_HISTORY_SQL = """
    CREATE TABLE IF NOT EXISTS mix_feature_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        review_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        filename TEXT DEFAULT '',
        title TEXT DEFAULT '',
        version_label TEXT DEFAULT '',
        mix_goal_key TEXT DEFAULT '',
        feature_json TEXT NOT NULL,
        UNIQUE(review_id)
    )
"""

FEEDBACK_FEATURES_SQL = """
    CREATE TABLE IF NOT EXISTS mix_feedback_features (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        feedback_id TEXT NOT NULL,
        review_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        decision TEXT NOT NULL,
        note TEXT DEFAULT '',
        feature_json TEXT NOT NULL,
        UNIQUE(feedback_id)
    )
"""


def init_feature_history(connect_func: Callable) -> None:
    """Create feature history and feedback feature tables."""
    with connect_func() as conn:
        conn.execute(FEATURE_HISTORY_SQL)
        conn.execute(FEEDBACK_FEATURES_SQL)
        conn.commit()


def cache_feature_vector(report: dict, *, connect_func: Callable) -> None:
    """Extract and store feature vector for a report.

    ML models access this historical feature data without
    re-analysing audio files.
    """
    if not MIX_FEATURES_AVAILABLE:
        return
    metrics = report.get("metrics") or {}
    review_id = str(report.get("id") or "")
    if not review_id or not metrics:
        return
    vector = extract_feature_vector(metrics)
    if not vector:
        return
    goal = metrics.get("mix_goal") or {}
    with connect_func() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO mix_feature_history (
                review_id, created_at, filename, title, version_label,
                mix_goal_key, feature_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                str(report.get("created_at", "")),
                str(metrics.get("filename", "")),
                str(report.get("title", "")),
                str(report.get("version_label", "")),
                str(goal.get("key", "")),
                json.dumps(vector, sort_keys=True),
            ),
        )
        conn.commit()


def cache_feedback_feature_vector(
    feedback_id: str,
    review_id: str,
    decision: str,
    note: str,
    report: dict,
    *,
    connect_func: Callable,
) -> None:
    """Store feature vector alongside a feedback decision.

    This creates labelled training data for quality prediction models.
    """
    if not MIX_FEATURES_AVAILABLE:
        return
    metrics = report.get("metrics") or {}
    if not metrics:
        return
    vector = extract_feature_vector(metrics)
    if not vector:
        return
    with connect_func() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO mix_feedback_features (
                feedback_id, review_id, created_at, decision, note, feature_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(feedback_id),
                str(review_id),
                str(datetime.now(timezone.utc).isoformat()),
                str(decision)[:80],
                str(note)[:500],
                json.dumps(vector, sort_keys=True),
            ),
        )
        conn.commit()


def load_feature_history(
    *,
    connect_func: Callable,
    limit: int = 500,
    review_id: str | None = None,
) -> list[dict]:
    """Load cached feature vectors for ML training or inference.

    Args:
        limit: Maximum number of records.
        review_id: Return only matching record if provided.

    Returns:
        List of dicts with keys: review_id, created_at, filename, title,
        version_label, mix_goal_key, features (dict).
    """
    with connect_func() as conn:
        if review_id:
            rows = conn.execute(
                "SELECT * FROM mix_feature_history WHERE review_id = ? ORDER BY created_at DESC",
                (review_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM mix_feature_history ORDER BY created_at DESC LIMIT ?",
                (max(1, min(5000, limit)),),
            ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["features"] = json.loads(item.pop("feature_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            item["features"] = {}
        out.append(item)
    return out


def find_similar_reviews(
    feature_vector: dict,
    *,
    connect_func: Callable,
    limit: int = 3,
    exclude_review_id: str | None = None,
) -> list[dict]:
    """Return the k most similar stored reviews by cosine distance on cached feature vectors.

    Uses sklearn NearestNeighbors (no torch dependency).  Returns an empty list
    when fewer than limit+1 reviews are stored, when sklearn is unavailable, or
    when an error occurs.

    Each result dict has keys: review_id, title, filename, mix_goal_key, score.
    ``score`` is 1 - cosine_distance, clipped to [0, 1]; higher is more similar.
    """
    try:
        from sklearn.neighbors import NearestNeighbors
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return []

    try:
        history = load_feature_history(connect_func=connect_func, limit=500)
        if exclude_review_id:
            history = [h for h in history if h.get("review_id") != exclude_review_id]
        if len(history) < limit:
            return []

        # Build a stable key ordering from the query vector.
        keys = sorted(k for k, v in feature_vector.items() if isinstance(v, (int, float)) and v is not None)
        if not keys:
            return []

        def _row_to_vec(fv: dict) -> list[float]:
            return [float(fv.get(k) or 0.0) for k in keys]

        matrix = [_row_to_vec(h["features"]) for h in history]
        # Drop all-zero rows (reviews with no usable feature data)
        non_zero_idx = [i for i, row in enumerate(matrix) if any(v != 0.0 for v in row)]
        if len(non_zero_idx) < limit:
            return []
        filtered_history = [history[i] for i in non_zero_idx]
        filtered_matrix = [matrix[i] for i in non_zero_idx]

        n_neighbors = min(limit, len(filtered_matrix))
        scaler = StandardScaler()
        scaled_matrix = scaler.fit_transform(filtered_matrix)
        query_raw = _row_to_vec(feature_vector)
        scaled_query = scaler.transform([query_raw])

        nn = NearestNeighbors(n_neighbors=n_neighbors, metric="cosine", algorithm="brute")
        nn.fit(scaled_matrix)
        distances, indices = nn.kneighbors(scaled_query)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            h = filtered_history[idx]
            score = round(max(0.0, min(1.0, 1.0 - float(dist))), 3)
            results.append({
                "review_id": h.get("review_id", ""),
                "title": h.get("title") or h.get("filename") or "Untitled",
                "filename": h.get("filename", ""),
                "mix_goal_key": h.get("mix_goal_key", ""),
                "score": score,
            })
        return results
    except Exception:
        return []


def delete_feature_history(review_id: str, *, connect_func: Callable) -> None:
    """Remove feature history for a deleted review."""
    with connect_func() as conn:
        conn.execute("DELETE FROM mix_feature_history WHERE review_id = ?", (review_id,))
        conn.execute("DELETE FROM mix_feedback_features WHERE review_id = ?", (review_id,))
        conn.commit()


def load_feedback_training_data(
    *,
    connect_func: Callable,
    limit: int = 500,
) -> list[dict]:
    """Load feedback-labelled feature vectors for supervised training.

    Returns:
        List of dicts with keys: feedback_id, review_id, decision,
        note, features (dict).
    """
    rows = []
    try:
        with connect_func() as conn:
            rows = conn.execute(
                "SELECT * FROM mix_feedback_features ORDER BY created_at DESC LIMIT ?",
                (max(1, min(5000, limit)),),
            ).fetchall()
    except Exception:
        return []
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["features"] = json.loads(item.pop("feature_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            item["features"] = {}
        out.append(item)
    return out


REPORT_SUMMARY_CACHE_SQL = """
    CREATE TABLE IF NOT EXISTS mix_report_summaries (
        review_id TEXT PRIMARY KEY,
        report_name TEXT,
        title TEXT,
        created_at TEXT,
        version_label TEXT,
        score INTEGER,
        rating TEXT,
        peak_dbfs REAL,
        rms_dbfs_estimate REAL,
        crest_factor_db REAL,
        summary TEXT,
        flags_json TEXT,
        previous_version_json TEXT,
        version_comparison_json TEXT,
        version_advice_json TEXT,
        revision_impact_json TEXT,
        mix_critique_json TEXT,
        reference_json TEXT,
        comparison_json TEXT,
        comparison_advice_json TEXT,
        revision_agent_json TEXT,
        session_report_json TEXT,
        kenn_handoff_json TEXT,
        dominant_band TEXT,
        high_flag_count INTEGER DEFAULT 0,
        cached_at TEXT
    )
"""


def _init_report_summary_cache(connect_func: Callable) -> None:
    with connect_func() as conn:
        conn.execute(REPORT_SUMMARY_CACHE_SQL)
        conn.commit()


def _cache_report_summary(report: dict, connect_func: Callable) -> None:
    """Cache key fields from a report for fast dashboard queries."""
    metrics = report.get("metrics") or {}
    review_id = str(report.get("id") or "")
    if not review_id:
        return
    summary = report.get("summary", "")
    flags = report.get("flags", [])
    previous_version = report.get("previous_version")
    version_comparison = report.get("version_comparison")
    version_advice = report.get("version_advice", [])
    revision_impact = report.get("revision_impact")
    mix_critique = report.get("mix_critique")
    reference = report.get("reference")
    comparison = report.get("comparison")
    comparison_advice = report.get("comparison_advice", [])
    revision_agent = report.get("revision_agent")
    session_report = report.get("session_report")
    kenn_handoff_data = report.get("kenn_handoff") or kenn_handoff(report)

    dominant_band = ""
    ps = metrics.get("perceptual_summary") or {}
    if isinstance(ps, dict):
        dominant_band = ps.get("dominant_band", "")

    high_flag_count = sum(
        1 for flag in (flags or []) if str(flag.get("severity", "")).lower() == "high"
    )

    with connect_func() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO mix_report_summaries (
                review_id, report_name, title, created_at, version_label,
                score, rating, peak_dbfs, rms_dbfs_estimate, crest_factor_db,
                summary, flags_json, previous_version_json, version_comparison_json,
                version_advice_json, revision_impact_json, mix_critique_json,
                reference_json, comparison_json, comparison_advice_json,
                revision_agent_json, session_report_json, kenn_handoff_json,
                dominant_band, high_flag_count, cached_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                str(report.get("report_name", "")),
                str(report.get("title", "")),
                str(report.get("created_at", "")),
                str(report.get("version_label", "")),
                metric_float(metrics.get("technical_score")),
                str(metrics.get("technical_rating", "")),
                metric_float(metrics.get("peak_dbfs")),
                metric_float(metrics.get("rms_dbfs_estimate")),
                metric_float(metrics.get("crest_factor_db")),
                str(summary),
                json.dumps(flags) if flags else "[]",
                json.dumps(previous_version) if previous_version else None,
                json.dumps(version_comparison) if version_comparison else None,
                json.dumps(version_advice) if version_advice else "[]",
                json.dumps(revision_impact) if revision_impact else None,
                json.dumps(mix_critique) if mix_critique else None,
                json.dumps(reference) if reference else None,
                json.dumps(comparison) if comparison else None,
                json.dumps(comparison_advice) if comparison_advice else "[]",
                json.dumps(revision_agent) if revision_agent else None,
                json.dumps(session_report) if session_report else None,
                json.dumps(kenn_handoff_data) if kenn_handoff_data else None,
                dominant_band,
                high_flag_count,
                str(datetime.now(timezone.utc).isoformat()) if hasattr(datetime, 'now') else "",
            ),
        )
        conn.commit()


def _read_cached_summaries(
    limit: int,
    *,
    connect_func: Callable,
) -> list[dict]:
    """Read cached report summaries from SQLite, returning dicts ready to use."""
    with connect_func() as conn:
        rows = conn.execute(
            """
            SELECT * FROM mix_report_summaries
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(500, limit)),),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        _deserialize_json_fields(item, [
            "flags_json", "previous_version_json", "version_comparison_json",
            "version_advice_json", "revision_impact_json", "mix_critique_json",
            "reference_json", "comparison_json", "comparison_advice_json",
            "revision_agent_json", "session_report_json", "kenn_handoff_json",
        ])
        out.append(item)
    return out


def _deserialize_json_fields(item: dict, fields: list[str]) -> None:
    for field in fields:
        raw = item.get(field)
        if raw and isinstance(raw, str):
            try:
                item[field.replace("_json", "")] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                item[field.replace("_json", "")] = None
        else:
            item[field.replace("_json", "")] = raw


def _delete_cached_summary(review_id: str, connect_func: Callable) -> None:
    with connect_func() as conn:
        conn.execute("DELETE FROM mix_report_summaries WHERE review_id = ?", (review_id,))
        conn.commit()


def init_reviews_table(
    *,
    upload_root: Path,
    report_root: Path,
    reference_root: Path,
    create_sql: str,
    create_references_sql: str,
    connect_func: Callable = connect,
) -> None:
    upload_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    reference_root.mkdir(parents=True, exist_ok=True)
    with connect_func() as conn:
        conn.execute(create_sql)
        try:
            conn.execute("ALTER TABLE mix_reviews ADD COLUMN status TEXT DEFAULT 'completed'")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE mix_reviews ADD COLUMN error TEXT")
        except sqlite3.OperationalError:
            pass
        conn.execute(create_references_sql)
        conn.execute(REPORT_SUMMARY_CACHE_SQL)
        conn.execute(FEATURE_HISTORY_SQL)
        conn.execute(FEEDBACK_FEATURES_SQL)
        conn.commit()


def normalize_title(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def read_report(report_root: Path, report_name: str) -> dict:
    path = report_root / str(report_name or "")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def review_by_id(
    review_id: str,
    *,
    report_root: Path,
    init_func: Callable,
    connect_func: Callable = connect,
) -> dict | None:
    review_id = str(review_id or "").strip()
    if not review_id:
        return None
    init_func()
    with connect_func() as conn:
        row = conn.execute(
            "SELECT * FROM mix_reviews WHERE id = ? LIMIT 1",
            (review_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    report = read_report(report_root, str(item.get("report_name", "")))
    if not report:
        return None
    merged = {**item, **report}
    _cache_report_summary(merged, connect_func)
    cache_feature_vector(merged, connect_func=connect_func)
    return merged


def update_revision_agent_step(
    review_id: str,
    step_id: str,
    status: str,
    *,
    report_root: Path,
    init_func: Callable,
    connect_func: Callable = connect,
) -> dict:
    review_id = str(review_id or "").strip()
    step_id = str(step_id or "").strip()
    status = str(status or "").strip().lower()
    if status not in {"todo", "doing", "done"}:
        return {"ok": False, "error": "Step status must be todo, doing, or done."}
    if not review_id or not step_id:
        return {"ok": False, "error": "Review id and step id are required."}
    init_func()
    with connect_func() as conn:
        row = conn.execute(
            "SELECT * FROM mix_reviews WHERE id = ? LIMIT 1",
            (review_id,),
        ).fetchone()
    if not row:
        return {"ok": False, "error": "Mix review not found."}
    item = dict(row)
    report_name = str(item.get("report_name", ""))
    report_path = report_root / report_name
    report = read_report(report_root, report_name)
    if not report:
        return {"ok": False, "error": "Mix review report not found."}
    agent = report.get("revision_agent") if isinstance(report.get("revision_agent"), dict) else {}
    agent, changed = update_step_status(agent, step_id, status)
    if not changed:
        return {"ok": False, "error": "Revision agent step not found."}
    report["revision_agent"] = agent
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "review": {**item, **report}, "revision_agent": agent}


def record_review_feedback(
    review_id: str,
    decision: str,
    note: str = "",
    *,
    path: Path,
    review_lookup: Callable,
    report_reader: Callable,
    connect_func: Callable = connect,
) -> dict:
    item = review_lookup(review_id)
    if not item:
        return {"ok": False, "error": "Review not found."}
    report = report_reader(str(item.get("report_name", "")))
    if not report:
        return {"ok": False, "error": "Review report not found."}
    result = append_feedback_record(path, report, decision, note)
    feedback_id = result.get("record", {}).get("id", "")
    if feedback_id and MIX_FEATURES_AVAILABLE:
        cache_feedback_feature_vector(
            feedback_id,
            review_id,
            decision,
            note,
            report,
            connect_func=connect_func,
        )
    return {**result, "review_id": review_id}


def latest_review_for_title(
    title: str,
    *,
    report_root: Path,
    init_func: Callable,
    connect_func: Callable = connect,
) -> dict | None:
    normalized = normalize_title(title)
    if not normalized:
        return None
    init_func()
    with connect_func() as conn:
        result = conn.execute(
            """
            SELECT * FROM mix_reviews
            WHERE lower(trim(title)) = ? AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (normalized,),
        )
        if not hasattr(result, "fetchall"):
            return None
        rows = result.fetchall()
    if not rows:
        return None
    row = dict(rows[0])
    report = read_report(report_root, str(row.get("report_name", "")))
    if not report.get("metrics"):
        return None
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "created_at": row.get("created_at"),
        "version_label": report.get("version_label", ""),
        "metrics": report.get("metrics", {}),
        "flags": report.get("flags", []),
        "revision_agent": report.get("revision_agent"),
    }


def list_reviews(
    limit: int = 50,
    *,
    report_root: Path,
    init_func: Callable,
    connect_func: Callable = connect,
    use_cache: bool = True,
) -> list[dict]:
    """List reviews, optionally using the SQLite summary cache for performance."""
    init_func()
    if use_cache:
        cached = _read_cached_summaries(limit, connect_func=connect_func)
        if cached:
            return cached
    with connect_func() as conn:
        rows = conn.execute(
            "SELECT * FROM mix_reviews ORDER BY created_at DESC LIMIT ?",
            (max(1, min(200, limit)),),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        report = read_report(report_root, str(item.get("report_name", "")))
        if report:
            item["metrics"] = report.get("metrics", {})
            item["flags"] = report.get("flags", [])
            item["advice"] = report.get("advice", [])
            item["summary"] = report.get("summary", "")
            item["action_plan"] = report.get("action_plan", [])
            item["version_label"] = report.get("version_label", "")
            item["previous_version"] = report.get("previous_version")
            item["version_comparison"] = report.get("version_comparison")
            item["version_advice"] = report.get("version_advice", [])
            item["kenn_handoff"] = report.get("kenn_handoff") or kenn_handoff({**item, **report})
            item["revision_impact"] = report.get("revision_impact")
            item["mix_critique"] = report.get("mix_critique")
            item["reference"] = report.get("reference")
            item["comparison"] = report.get("comparison")
            item["comparison_advice"] = report.get("comparison_advice", [])
            item["revision_agent"] = report.get("revision_agent")
            item["session_report"] = report.get("session_report")
            _cache_report_summary({**item, **report}, connect_func)
            cache_feature_vector({**item, **report}, connect_func=connect_func)
        out.append(item)
    return out


def numeric_delta(new_value: object, old_value: object) -> float | None:
    try:
        return round(float(new_value) - float(old_value), 3)
    except (TypeError, ValueError):
        return None


def review_history(list_func: Callable, limit: int = 20, *, title: str = "") -> list[dict]:
    normalized = normalize_title(title)
    items = list_func(limit=max(limit, 50 if normalized else limit))
    if normalized:
        items = [item for item in items if normalize_title(str(item.get("title", ""))) == normalized]
    compact = []
    for item in items[: max(1, min(100, limit))]:
        metrics = item.get("metrics") or {}
        previous = item.get("previous_version") or {}
        version_comparison = item.get("version_comparison") or {}
        revision_agent = item.get("revision_agent") or {}
        compact.append(
            {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "version_label": item.get("version_label", ""),
                "created_at": item.get("created_at", ""),
                "score": metrics.get("technical_score"),
                "rating": metrics.get("technical_rating", ""),
                "peak_dbfs": metrics.get("peak_dbfs"),
                "rms_dbfs_estimate": metrics.get("rms_dbfs_estimate"),
                "crest_factor_db": metrics.get("crest_factor_db"),
                "dominant_band": (metrics.get("perceptual_summary") or {}).get("dominant_band", ""),
                "summary": item.get("summary", ""),
                "flags": [
                    str(flag.get("label", ""))
                    for flag in item.get("flags", [])[:5]
                    if flag.get("label")
                ],
                "previous_version": {
                    "id": previous.get("id"),
                    "version_label": previous.get("version_label", ""),
                    "created_at": previous.get("created_at", ""),
                }
                if previous
                else None,
                "version_delta": {
                    key: version_comparison.get(key)
                    for key in ("rms_delta_db", "crest_delta_db", "stereo_width_delta")
                    if version_comparison.get(key) not in {None, ""}
                },
                "version_advice": item.get("version_advice", [])[:3],
                "revision_impact": item.get("revision_impact"),
                "has_reference": bool(item.get("reference")),
                "revision_agent": {
                    "summary": revision_agent.get("summary", ""),
                    "steps": (revision_agent.get("steps") or [])[:4],
                }
                if revision_agent
                else None,
            }
        )
    return compact


def report_json_bytes(review_lookup: Callable, review_id: str) -> bytes | None:
    report = review_lookup(review_id)
    if not report:
        return None
    return (json.dumps(report, indent=2) + "\n").encode("utf-8")


def repair_chains_json_bytes(review_lookup: Callable, review_id: str) -> bytes | None:
    report = review_lookup(review_id)
    if not report:
        return None
    chains = report.get("ableton_repair_chains") or {}
    return (json.dumps(chains, indent=2) + "\n").encode("utf-8")


def review_audio_path(
    review_lookup: Callable,
    review_id: str,
    type: str,
    *,
    upload_root: Path,
) -> Path | None:
    review = review_lookup(review_id)
    if not review:
        return None
    if type == "mix":
        stored_name = review.get("stored_name")
        if stored_name:
            return upload_root / stored_name
    elif type == "reference":
        ref = review.get("reference")
        if isinstance(ref, dict):
            stored_name = ref.get("stored_name")
            if stored_name:
                return upload_root / stored_name
            filename = ref.get("filename")
            if filename:
                return upload_root / f"{review_id}_reference_{filename}"
    return None
