from __future__ import annotations

import json
from pathlib import Path

from app.routes.ableton_routes import TRANSCRIPTION_SUFFIXES
from app.routes.static_routes import static_target


ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / "server" / "app" / "static" / "hub.html"


def test_browser_voice_uses_portable_media_recorder_contract() -> None:
    html = HUB.read_text(encoding="utf-8")

    # Primary voice input is the portable MediaRecorder + server-side
    # transcription path (works on Firefox/Safari, unlike the native
    # SpeechRecognition API). "Siri Mode" additionally offers an opt-in
    # hands-free loop that does use native SpeechRecognition where
    # available -- that's fine as long as it's feature-detected rather
    # than assumed, so this checks for the guard, not a blanket absence.
    assert "navigator.mediaDevices?.getUserMedia" in html
    assert "window.MediaRecorder" in html
    assert "'webkitSpeechRecognition' in window || 'SpeechRecognition' in window" in html
    assert "/api/thursday/transcribe" in html
    assert "audio/webm;codecs=opus" in html
    assert "audio/mp4;codecs=mp4a.40.2" in html
    assert "audio/ogg;codecs=opus" in html
    assert "browserSpeechFallback" in html


def test_server_accepts_firefox_safari_and_chromium_audio() -> None:
    assert TRANSCRIPTION_SUFFIXES == {
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
    }


def test_hub_exposes_standalone_web_app_manifest() -> None:
    resolved = static_target("/manifest.webmanifest")
    assert resolved is not None
    path, content_type = resolved
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert content_type == "application/manifest+json"
    assert manifest["start_url"] == "/hub"
    assert manifest["display"] == "standalone"
    assert '<link rel="manifest" href="/manifest.webmanifest">' in HUB.read_text(
        encoding="utf-8"
    )
