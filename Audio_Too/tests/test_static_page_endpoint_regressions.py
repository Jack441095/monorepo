"""Regression guards for stale/CSRF-less endpoint bugs found in a live
bug-finding sweep (2026-07-08).

Both business/app/static/audio-analysis.html and audiogen.html were calling
endpoints that don't exist in the current dispatch (renamed during an
earlier refactor: /api/ableton/mix-review -> /api/admin/mix-review;
/api/audiogen/render -> /api/admin/audiogen/generate +
/api/admin/audiogen/render-song), reading response fields that don't exist
(file_url/prompt instead of src/emotion), and — like studio/kenn/kenn's
app.js — never sending the X-CSRF-Token header the business app's
require_private_post() requires for authenticated POST routes. Verified live
against a running server: without these fixes every one of these features
was completely broken (403 or silently no-op).
"""

from __future__ import annotations

from pathlib import Path

STATIC_ROOT = Path(__file__).resolve().parent.parent / "server" / "app" / "static"


def _source(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_audio_analysis_uploads_to_the_real_mix_review_endpoint() -> None:
    source = _source("audio-analysis.html")
    assert "/api/ableton/mix-review" not in source
    assert "/api/admin/mix-review'" in source or '/api/admin/mix-review"' in source


def test_audio_analysis_sends_csrf_token_on_upload() -> None:
    source = _source("audio-analysis.html")
    assert "ensureCsrf" in source
    assert "X-CSRF-Token" in source


def test_audiogen_uses_the_real_generate_and_render_song_endpoints() -> None:
    source = _source("audiogen.html")
    assert "/api/audiogen/render'" not in source and '/api/audiogen/render"' not in source
    assert "/api/admin/audiogen/generate" in source
    assert "/api/admin/audiogen/render-song" in source
    assert "/api/admin/audiogen/render-job" in source
    assert "/api/admin/audiogen/history" in source


def test_audiogen_sends_csrf_token_on_mutations() -> None:
    source = _source("audiogen.html")
    assert "ensureCsrf" in source
    assert "X-CSRF-Token" in source


def test_audiogen_reads_the_real_response_field_names() -> None:
    """audiogen_bridge.generate_for_kenn/render worker return `src`, not
    `file_url`; render_job's completed result is under job.result.src."""
    source = _source("audiogen.html")
    assert "d.file_url" not in source
    assert "d.src" in source
    assert "job.result&&job.result.src" in source or "job.result && job.result.src" in source
