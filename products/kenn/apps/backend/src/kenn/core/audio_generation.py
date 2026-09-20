"""Provider-neutral, disabled-by-default audio-generation boundary."""

from __future__ import annotations

import base64
import hashlib
import io
import math
import wave
from dataclasses import dataclass
from typing import Any, Callable

REQUEST_SCHEMA = "kenn.audio_generation_request.v1"
RESULT_SCHEMA = "kenn.audio_generation_result.v1"
CAPTION_SCHEMA = "kenn.structured_music_caption.v1"
MAX_DURATION_SECONDS = 300.0
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024


class AudioGenerationError(ValueError):
    """Raised when an untrusted request or provider response is invalid."""


def _text(value: Any, *, limit: int) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned[:limit] or None


def build_structured_caption(brief: dict[str, Any]) -> dict[str, Any]:
    """Allowlist explicit creative constraints without inventing missing facts."""
    if not isinstance(brief, dict):
        raise AudioGenerationError("creative brief must be an object")
    caption: dict[str, Any] = {"schema": CAPTION_SCHEMA}
    for field in ("genre", "subgenre", "key", "scale", "emotion", "production_profile"):
        caption[field] = _text(brief.get(field), limit=128)
    bpm = brief.get("bpm")
    if bpm is None:
        caption["bpm"] = None
    else:
        try:
            parsed_bpm = float(bpm)
        except (TypeError, ValueError) as exc:
            raise AudioGenerationError("bpm must be numeric when supplied") from exc
        if not math.isfinite(parsed_bpm) or not 20 <= parsed_bpm <= 400:
            raise AudioGenerationError("bpm must be between 20 and 400")
        caption["bpm"] = parsed_bpm
    vocals = brief.get("vocals") if isinstance(brief.get("vocals"), dict) else {}
    caption["vocals"] = {
        key: _text(vocals.get(key), limit=128)
        for key in ("presence", "timbre", "register", "delivery", "harmony", "effects", "identity")
    }
    arrangement = brief.get("arrangement")
    if arrangement is not None and not isinstance(arrangement, list):
        raise AudioGenerationError("arrangement must be a list when supplied")
    caption["arrangement"] = [
        _text(item, limit=512) for item in (arrangement or [])[:32] if _text(item, limit=512)
    ]
    caption["unknown_fields_preserved"] = [
        field for field in ("bpm", "key", "scale", "genre", "vocal_identity")
        if (caption["vocals"]["identity"] if field == "vocal_identity" else caption.get(field)) is None
    ]
    return caption


def build_request(*, request_id: str, lyrics: str, brief: dict[str, Any], duration_seconds: float,
                  seed: int, output_format: str = "wav") -> dict[str, Any]:
    clean_id = _text(request_id, limit=128)
    clean_lyrics = _text(lyrics, limit=20_000)
    if not clean_id:
        raise AudioGenerationError("request_id is required")
    if not clean_lyrics:
        raise AudioGenerationError("lyrics are required")
    try:
        duration = float(duration_seconds)
        clean_seed = int(seed)
    except (TypeError, ValueError) as exc:
        raise AudioGenerationError("duration_seconds and seed must be numeric") from exc
    if not math.isfinite(duration) or not 1 <= duration <= MAX_DURATION_SECONDS:
        raise AudioGenerationError(f"duration_seconds must be between 1 and {MAX_DURATION_SECONDS:g}")
    if output_format != "wav":
        raise AudioGenerationError("only non-streaming WAV output is supported")
    return {"schema": REQUEST_SCHEMA, "request_id": clean_id, "lyrics": clean_lyrics,
            "caption": build_structured_caption(brief), "duration_seconds": duration,
            "seed": clean_seed, "output_format": "wav", "stream": False}


def _wav_metadata(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_ARTIFACT_BYTES:
        raise AudioGenerationError("provider WAV exceeds the artifact-size limit")
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            frames = handle.getnframes(); rate = handle.getframerate(); channels = handle.getnchannels()
    except (wave.Error, EOFError) as exc:
        raise AudioGenerationError("provider returned invalid WAV data") from exc
    if rate <= 0 or channels not in (1, 2) or frames <= 0:
        raise AudioGenerationError("provider WAV has unsupported audio metadata")
    return {"sample_rate_hz": rate, "channels": channels, "frame_count": frames,
            "duration_seconds": frames / rate}


def _validate_request(request: Any) -> None:
    if not isinstance(request, dict) or request.get("schema") != REQUEST_SCHEMA:
        raise AudioGenerationError("invalid audio-generation request contract")
    if request.get("stream") is not False or request.get("output_format") != "wav":
        raise AudioGenerationError("audio-generation request must use non-streaming WAV output")
    if not _text(request.get("request_id"), limit=128) or not _text(request.get("lyrics"), limit=20_000):
        raise AudioGenerationError("audio-generation request identity and lyrics are required")
    if not isinstance(request.get("caption"), dict) or request["caption"].get("schema") != CAPTION_SCHEMA:
        raise AudioGenerationError("audio-generation request has an invalid caption")
    try:
        duration = float(request["duration_seconds"])
        int(request["seed"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AudioGenerationError("audio-generation request has invalid bounds") from exc
    if not math.isfinite(duration) or not 1 <= duration <= MAX_DURATION_SECONDS:
        raise AudioGenerationError("audio-generation request has invalid bounds")


@dataclass(frozen=True)
class MiniMaxMusic3Backend:
    """Thin optional adapter; the caller supplies the HTTP transport."""

    http_client: Callable[[dict[str, Any], float], dict[str, Any]]
    model_revision: str
    enabled: bool = False
    timeout_seconds: float = 120.0

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise AudioGenerationError("MiniMax Music 3 backend is disabled")
        _validate_request(request)
        try:
            response = self.http_client(request, self.timeout_seconds)
        except TimeoutError as exc:
            raise AudioGenerationError("MiniMax Music 3 request timed out") from exc
        except OSError as exc:
            raise AudioGenerationError("MiniMax Music 3 provider is unavailable") from exc
        if not isinstance(response, dict) or not isinstance(response.get("audio_base64"), str):
            raise AudioGenerationError("provider response does not contain inline WAV data")
        try:
            audio = base64.b64decode(response["audio_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise AudioGenerationError("provider returned invalid base64 audio") from exc
        metadata = _wav_metadata(audio)
        if metadata["duration_seconds"] > float(request["duration_seconds"]) + 1.0:
            raise AudioGenerationError("provider WAV exceeds the requested duration")
        configured_revision = _text(self.model_revision, limit=256)
        reported_revision = _text(response.get("model_revision"), limit=256)
        if reported_revision and configured_revision and reported_revision != configured_revision:
            raise AudioGenerationError("provider model revision does not match the configured revision")
        revision = reported_revision or configured_revision
        if not revision:
            raise AudioGenerationError("model revision is required for provenance")
        return {"schema": RESULT_SCHEMA, "request_id": request["request_id"], "status": "complete",
                "artifact": {"kind": "wav", "media_type": "audio/wav", "byte_count": len(audio),
                             "sha256": "sha256:" + hashlib.sha256(audio).hexdigest(), **metadata},
                "provenance": {"generated": True, "provider": "minimax_music3",
                               "model_revision": revision, "user_source_audio": False},
                "audio_bytes": audio}


__all__ = ["AudioGenerationError", "MiniMaxMusic3Backend", "build_request", "build_structured_caption"]
