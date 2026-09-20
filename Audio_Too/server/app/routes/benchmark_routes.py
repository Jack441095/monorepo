"""Listening Benchmark API routes — /api/benchmark/session, /api/benchmark/audio,
and /api/benchmark/rate.

Serves real blind A/B packages from a completed listening-benchmark study
(artifacts/listening_benchmark_study_2026_07_20/packages/<id>/{A,B}.wav),
each with a public listener_manifest.json (safe to read) and a
private_lineage.json holding the real A/B->baseline/candidate mapping --
that file is never read here. Ratings from the internal-evaluation panel
are stored via the shared db module, not an ad-hoc connection.
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from urllib.parse import urlparse

import db
import path_safety

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_PACKAGES_ROOT = (
    REPO_ROOT / "artifacts" / "listening_benchmark_study_2026_07_20" / "packages"
)
_SLOT_TO_FILENAME = {"1": "A.wav", "2": "B.wav"}


def _list_package_ids() -> list[str]:
    if not BENCHMARK_PACKAGES_ROOT.is_dir():
        return []
    return sorted(
        p.name for p in BENCHMARK_PACKAGES_ROOT.iterdir()
        if p.is_dir() and (p / "listener_manifest.json").exists()
    )


def handle_benchmark_get(handler, parsed_path: str) -> bool:
    """Handle GET /api/benchmark/* routes."""
    parsed = urlparse("https://host" + parsed_path)
    path_only = parsed.path

    if path_only == "/api/benchmark/session":
        package_ids = _list_package_ids()
        if not package_ids:
            handler.send_json(404, {"ok": False, "error": "No listening-benchmark packages are available."})
            return True
        package_id = random.choice(package_ids)
        manifest_path = BENCHMARK_PACKAGES_ROOT / package_id / "listener_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            handler.send_json(500, {"ok": False, "error": "Package manifest could not be read."})
            return True
        handler.send_json(200, {
            "ok": True,
            "session_id": f"session_{uuid.uuid4().hex[:8]}",
            "project_id": package_id,
            "project_title": f"Blind comparison {package_id}",
            "genre": "",
            "duration_seconds": manifest.get("duration_seconds"),
            "mix1_url": f"/api/benchmark/audio/{package_id}/1",
            "mix2_url": f"/api/benchmark/audio/{package_id}/2",
        })
        return True

    audio_prefix = "/api/benchmark/audio/"
    if path_only.startswith(audio_prefix):
        remainder = path_only.removeprefix(audio_prefix)
        parts = remainder.split("/")
        if len(parts) != 2:
            handler.send_json(404, {"error": "Benchmark audio not found."})
            return True
        package_id, slot = parts
        filename = _SLOT_TO_FILENAME.get(slot)
        if filename is None:
            handler.send_json(404, {"error": "Unknown benchmark audio slot."})
            return True
        try:
            package_id = path_safety.validate_identifier(package_id, label="package ID")
            wav_path = path_safety.safe_child(BENCHMARK_PACKAGES_ROOT, package_id, filename)
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        if not wav_path.exists():
            handler.send_json(404, {"error": "Benchmark audio not found."})
            return True
        handler.send_file(wav_path, "audio/wav", filename=f"{package_id}_{filename}")
        return True

    return False


def handle_benchmark_post(handler, parsed_path: str) -> bool:
    """Handle POST /api/benchmark/* routes."""
    parsed = urlparse("https://host" + parsed_path)
    path_only = parsed.path

    if path_only == "/api/benchmark/rate":
        if not handler.require_private_post():
            return True
        try:
            data = handler.read_json_body()
        except Exception as exc:
            handler.send_json(400, {"error": f"Invalid JSON payload: {exc}"})
            return True

        session_id = str(data.get("session_id", ""))
        project_id = str(data.get("project_id", ""))
        if not session_id or not project_id:
            handler.send_json(400, {"error": "session_id and project_id are required."})
            return True

        try:
            active_mix_evaluated = int(data.get("active_mix_evaluated", 1))
        except (TypeError, ValueError):
            active_mix_evaluated = 1
        preference = str(data.get("preference", "equal") or "equal")
        producer_name = str(data.get("producer_name", "") or "Anonymous Producer")
        feedback_text = str(data.get("feedback_text", ""))

        def _score(key: str) -> int | None:
            try:
                return int(data.get(key))
            except (TypeError, ValueError):
                return None

        rating_id = uuid.uuid4().hex
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO listening_benchmark_ratings (
                    id, session_id, package_id, active_mix_evaluated, preference,
                    producer_name, score_clarity, score_bass, score_width, score_punch,
                    feedback_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rating_id, session_id, project_id, active_mix_evaluated, preference,
                    producer_name, _score("clarity"), _score("bass"), _score("width"), _score("punch"),
                    feedback_text, db.now(),
                ),
            )
            conn.commit()

        handler.send_json(200, {
            "ok": True,
            "message": "Producer benchmark rating recorded successfully.",
            "session_id": session_id,
            "rating_id": rating_id,
        })
        return True

    return False
