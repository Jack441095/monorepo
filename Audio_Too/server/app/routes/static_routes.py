"""Canonical browser route mapping and safe static/portfolio delivery."""

from __future__ import annotations

import mimetypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUSINESS_ROOT = ROOT.parent
STATIC_ROOT = ROOT / "static"
PORTFOLIO_ROOT = BUSINESS_ROOT / "Portfolio"

STATIC_ROUTE_MAP = {
    "/": "/index.html",
    "/admin.html": "/dashboard.html",
    "/audio-analysis": "/audio-analysis.html",
    "/audiogen": "/audiogen.html",
    "/automix": "/automix.html",
    "/automix.html": "/automix.html",
    "/chat": "/thursday.html",
    "/creative-lab": "/creative-lab.html",
    "/dashboard": "/dashboard.html",
    "/demo": "/demo.html",
    "/home": "/hub.html",
    "/hub": "/hub.html",
    "/portfolio": "/portfolio.html",
    "/thursday": "/thursday.html",
    "/thursday.html": "/thursday.html",
    "/tips": "/tips.html",
    "/upload": "/stem-upload.html",
    "/visualizer": "/ableton_visualizer.html",
    "/ableton_visualizer.html": "/ableton_visualizer.html",
}


def static_target(path: str) -> tuple[Path, str] | None:
    """Resolve one browser path to an allowed file and content type."""
    path = STATIC_ROUTE_MAP.get(path, path)
    if path.startswith("/portfolio/audio/"):
        allowed_root = (PORTFOLIO_ROOT / "audio").resolve()
        target = (allowed_root / path.removeprefix("/portfolio/audio/")).resolve()
    elif path.startswith("/portfolio/images/"):
        allowed_root = (PORTFOLIO_ROOT / "images").resolve()
        target = (allowed_root / path.removeprefix("/portfolio/images/")).resolve()
    else:
        allowed_root = STATIC_ROOT.resolve()
        target = (allowed_root / path.lstrip("/")).resolve()
    try:
        target.relative_to(allowed_root)
    except ValueError:
        return None
    if not target.is_file():
        return None
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return target, content_type


def handle_static_get(handler, path: str) -> bool:
    resolved = static_target(path)
    if not resolved:
        handler.send_bytes(404, b"Not found", "text/plain; charset=utf-8")
        return True
    target, content_type = resolved
    handler.send_file(target, content_type, cache_control="public, max-age=300")
    return True
