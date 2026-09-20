"""Creative Lab: portfolio functions.

Split out of creative_lab.py (was 1,261 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

from pathlib import Path

from audio_analysis.mix_review import mix_review

from .constants import (
    PORTFOLIO_AUDIO,
)

from .metrics import (
    record_session_event,
)


def _portfolio_audio_path(src: str) -> Path | None:
    clean = str(src or "").strip()
    prefix = "/portfolio/audio/"
    if not clean.startswith(prefix):
        return None
    filename = Path(clean.removeprefix(prefix)).name
    target = (PORTFOLIO_AUDIO / filename).resolve()
    try:
        target.relative_to(PORTFOLIO_AUDIO.resolve())
    except ValueError:
        return None
    return target if target.exists() else None


def review_generated_audio(payload: dict) -> dict:
    src = str(payload.get("src") or "").strip()
    target = _portfolio_audio_path(src)
    if not target:
        return {"ok": False, "error": "Generated WAV was not found in Portfolio/audio."}
    result = mix_review.save_review(
        file_bytes=target.read_bytes(),
        filename=target.name,
        title=str(payload.get("title") or target.stem).strip(),
        version_label=str(payload.get("version") or "Creative Lab").strip(),
        mix_goal=str(payload.get("mix_goal") or "club").strip(),
    )
    if not result.get("ok"):
        return result
    review = result.get("review") or {}
    record_session_event(
        {
            "session_id": str(payload.get("session_id") or "").strip(),
            "type": "mix_review",
            "title": str(payload.get("session_title") or "Creative Lab session"),
            "src": src,
            "review_id": review.get("id", ""),
            "technical_score": (review.get("metrics") or {}).get("technical_score"),
            "summary": review.get("summary", ""),
        }
    )
    return {"ok": True, "review": review}
