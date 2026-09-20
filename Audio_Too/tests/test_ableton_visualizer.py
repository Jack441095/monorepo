"""Unit tests for the retired Ableton visualizer page's redirect stub.

The live-session chat + OSC control panel this page used to host now lives
in the KENN app itself (studio/kenn/kenn/static/, "Live" nav button) — see
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md. This page is kept only as a
redirect so old bookmarks/links to /visualizer still land somewhere useful.
"""

from __future__ import annotations

from pathlib import Path

from server.app.routes.static_routes import static_target


def test_ableton_visualizer_static_route():
    res = static_target("/visualizer")
    assert res is not None
    target_path, content_type = res
    assert target_path.name == "ableton_visualizer.html"
    assert "html" in content_type
    assert target_path.exists()


def test_ableton_visualizer_redirects_to_kenn():
    html_file = Path(__file__).resolve().parent.parent / "server" / "app" / "static" / "ableton_visualizer.html"
    content = html_file.read_text(encoding="utf-8")

    # Points at the raw KENN port, not the /kenn proxy — see the file's own
    # comment for why (kenn_proxy_routes.py doesn't cover the bare /api/...
    # paths studio/kenn/kenn/static/app.js actually calls).
    assert 'url=http://127.0.0.1:8090' in content
    assert 'ableton_visualizer.js' not in content
