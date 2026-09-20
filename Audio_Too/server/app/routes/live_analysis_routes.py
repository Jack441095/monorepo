"""Live audio stream analysis route for A8.1 POST-based polling."""

from __future__ import annotations

import base64


def handle_live_analyze_post(handler, path: str) -> bool:
    """Handle POST /api/live/analyze — returns True if the path matches.

    Expects JSON body: {pcm_base64: str, sample_rate: int, channels: int}
    Returns:          {ok, lufs_momentary, bands, correlation, balance, sample_count}
    """
    if path != "/api/live/analyze":
        return False

    try:
        payload = handler.read_json_body()
    except Exception:
        handler.send_json(400, {"ok": False, "error": "Invalid JSON body"})
        return True

    pcm_b64 = payload.get("pcm_base64", "")
    sample_rate = int(payload.get("sample_rate") or 44100)
    channels = int(payload.get("channels") or 2)

    if not pcm_b64:
        handler.send_json(400, {"ok": False, "error": "pcm_base64 is required"})
        return True

    try:
        pcm_bytes = base64.b64decode(pcm_b64)
    except Exception:
        handler.send_json(400, {"ok": False, "error": "Invalid base64 data"})
        return True

    try:
        from audio_analysis.analysis_core.stream_analysis import analyze_pcm_chunk
        result = analyze_pcm_chunk(pcm_bytes, sample_rate=sample_rate, channels=channels)
        handler.send_json(200, {"ok": True, **result})
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": str(exc)})
    return True
