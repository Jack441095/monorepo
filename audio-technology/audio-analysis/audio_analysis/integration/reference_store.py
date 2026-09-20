from __future__ import annotations

from dataclasses import dataclass
import json
import wave
from pathlib import Path
from typing import Callable
from uuid import uuid4


@dataclass(frozen=True)
class ReferenceStoreContext:
    analyze_wav: Callable
    connect: Callable
    init_reviews_table: Callable
    now: Callable
    reference_root: Path
    validate_wav_upload: Callable


def save_reference(
    *,
    file_bytes: bytes,
    filename: str,
    name: str = "",
    style: str = "",
    context: ReferenceStoreContext,
) -> dict:
    validation = context.validate_wav_upload(file_bytes, filename, label="Reference")
    if not validation.get("ok"):
        return validation
    safe_name = str(validation["safe_name"])
    reference_name = name.strip()[:120] or Path(safe_name).stem.replace("-", " ").replace("_", " ").title()
    try:
        report = context.analyze_wav(file_bytes, safe_name)
    except (wave.Error, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    context.init_reviews_table()
    reference_id = str(uuid4())[:8]
    stored_name = f"{reference_id}_{safe_name}"
    (context.reference_root / stored_name).write_bytes(file_bytes)
    metrics = report["metrics"]
    profile = metrics.get("log_bands_40") or []
    try:
        from audio_analysis.analysis_core.genre_profiles import classify_reference_profile

        classification = classify_reference_profile(profile, metrics)
    except (ImportError, TypeError, ValueError):
        classification = {"genre_key": "", "genre_name": "Uncategorised", "confidence": 0.0}
    detected_style = str(classification.get("genre_name") or "").strip()
    row = {
        "id": reference_id,
        "name": reference_name,
        "style": style.strip()[:120] or detected_style[:120],
        "genre_key": str(classification.get("genre_key") or ""),
        "genre_confidence": float(classification.get("confidence") or 0.0),
        "original_name": safe_name,
        "stored_name": stored_name,
        "metrics": metrics,
        "profile": profile,
        "size_bytes": len(file_bytes),
        "created_at": context.now(),
    }
    with context.connect() as conn:
        conn.execute(
            """
            INSERT INTO mix_references (
                id, name, style, original_name, stored_name, metrics_json,
                genre_key, genre_confidence, profile_json, crest_factor_db,
                integrated_lufs, loudness_range_lu, stereo_correlation, stereo_width_ratio,
                size_bytes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["id"],
                row["name"],
                row["style"],
                row["original_name"],
                row["stored_name"],
                json.dumps(row["metrics"]),
                row["genre_key"],
                row["genre_confidence"],
                json.dumps(row["profile"]),
                metrics.get("crest_factor_db"),
                metrics.get("integrated_lufs"),
                metrics.get("loudness_range_lu"),
                metrics.get("stereo_correlation"),
                metrics.get("stereo_width_ratio"),
                row["size_bytes"],
                row["created_at"],
            ],
        )
        conn.commit()
    return {"ok": True, "reference": row}


def list_references(limit: int = 100, *, init_reviews_table: Callable, connect: Callable) -> list[dict]:
    init_reviews_table()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM mix_references ORDER BY created_at DESC LIMIT ?",
            (max(1, min(500, limit)),),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["metrics"] = json.loads(str(item.pop("metrics_json", "{}") or "{}"))
        except json.JSONDecodeError:
            item["metrics"] = {}
        try:
            item["profile"] = json.loads(str(item.pop("profile_json", "[]") or "[]"))
        except json.JSONDecodeError:
            item["profile"] = []
        out.append(item)
    return out


def reference_by_id(reference_id: str, *, init_reviews_table: Callable, connect: Callable) -> dict | None:
    reference_id = str(reference_id or "").strip()
    if not reference_id:
        return None
    init_reviews_table()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM mix_references WHERE id = ? LIMIT 1",
            (reference_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["metrics"] = json.loads(str(item.pop("metrics_json", "{}") or "{}"))
    except json.JSONDecodeError:
        item["metrics"] = {}
    try:
        item["profile"] = json.loads(str(item.pop("profile_json", "[]") or "[]"))
    except json.JSONDecodeError:
        item["profile"] = []
    return item


def reference_envelope_for_genre(
    genre_key: str,
    *,
    init_reviews_table: Callable,
    connect: Callable,
) -> dict | None:
    """Build a statistical envelope from every stored reference in a genre."""
    genre_key = str(genre_key or "").strip().lower()
    if not genre_key:
        return None
    init_reviews_table()
    with connect() as conn:
        cursor = conn.execute(
            "SELECT profile_json FROM mix_references WHERE genre_key = ? ORDER BY created_at",
            (genre_key,),
        )
        rows = cursor.fetchall() if cursor is not None else []
    profiles = []
    for row in rows:
        try:
            profile = json.loads(str(row["profile_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            continue
        if len(profile) == 40:
            profiles.append(profile)
    if not profiles:
        return None
    from audio_analysis.analysis_core.genre_profiles import build_reference_envelope

    return build_reference_envelope(profiles)


def handle_multipart_reference(content_type: str, body: bytes, *, parse_multipart_form: Callable, save_reference: Callable) -> dict:
    fields = parse_multipart_form(content_type, body)
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return {"ok": False, "error": "Missing file field."}
    return save_reference(
        file_bytes=bytes(file_bytes),
        filename=str(fields.get("file__filename", "reference.wav")),
        name=str(fields.get("name", "")),
        style=str(fields.get("style", "")),
    )
