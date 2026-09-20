"""Proxy routes for KENN — forwards /kenn/* to the KENN engine on port 8090.

Static files (/kenn, /kenn/app.js, /kenn/styles.css) are served directly
from the KENN static directory. All /kenn/api/* calls are proxied to the
KENN inference server so the browser only ever talks to port 8080.
"""
from __future__ import annotations

import http.client
import json
from pathlib import Path
from urllib.parse import urlparse

KENN_HOST = "127.0.0.1"
KENN_PORT = 8090

KENN_STATIC = (
    Path(__file__).resolve().parents[3] / "studio" / "kenn" / "kenn" / "static"
)

_MIME = {
    ".html": "text/html;charset=utf-8",
    ".js":   "application/javascript;charset=utf-8",
    ".css":  "text/css;charset=utf-8",
    ".json": "application/json",
    ".wav":  "audio/wav",
    ".mp3":  "audio/mpeg",
}

# Static files served directly from KENN static dir
_STATIC_MAP = {
    "/kenn":           "index.html",
    "/kenn/":          "index.html",
    "/kenn/index.html":"index.html",
    "/kenn/app.js":    "app.js",
    "/kenn/styles.css":"styles.css",
}


def handle_kenn_get(handler, path: str) -> bool:
    """Serve KENN static files or proxy API GETs. Returns True if handled."""
    # Static file?
    if path in _STATIC_MAP:
        _serve_static(handler, _STATIC_MAP[path])
        return True

    # Proxy /kenn/api/* → 8090/api/*
    if path.startswith("/kenn/api/") or path.startswith("/kenn/portfolio/"):
        upstream = path[len("/kenn"):]  # strip /kenn prefix
        _proxy_get(handler, upstream)
        return True

    return False


def handle_kenn_post(handler, path: str) -> bool:
    """Proxy KENN API POSTs or run autonomous agent."""
    if path in {"/api/kenn/autonomous-execute", "/kenn/api/autonomous-execute"}:
        # Deliberate, documented exception to this module's proxy pattern
        # (docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md Phase 1): every
        # other /kenn/api/* path below forwards over HTTP to the KENN
        # engine on :8090; this one instead imports and runs
        # KennAutonomousAgent in-process, inside the business app. Left
        # as-is rather than forced into the HTTP-proxy shape -- the
        # autonomous coding-agent loop this runs is a long-lived,
        # potentially slow operation better kept in-process than added to
        # the generic proxy's request/response round trip.
        try:
            from kenn.autonomous_agent import KennAutonomousAgent
            length = int(handler.headers.get("Content-Length", 0))
            raw_body = handler.rfile.read(length).decode("utf-8")
            data = json.loads(raw_body)
        except Exception as exc:
            handler.send_json(400, {"error": f"Invalid JSON body: {exc}"})
            return True

        prompt = data.get("prompt", "Analyze audio DSP code and match spectrum")
        code_context = data.get("code_context")
        project_id = data.get("project_id")

        agent = KennAutonomousAgent()
        result = agent.run_agent_loop(prompt, code_context=code_context, project_id=project_id)
        handler.send_json(200, result)
        return True

    if not path.startswith("/kenn/api/"):
        return False
    upstream = path[len("/kenn"):]
    _proxy_post(handler, upstream)
    return True


# ── helpers ───────────────────────────────────────────────────────

def _serve_static(handler, filename: str) -> None:
    target = KENN_STATIC / filename
    if not target.exists():
        handler.send_error(404)
        return
    data = target.read_bytes()
    suffix = target.suffix
    content_type = _MIME.get(suffix, "application/octet-stream")
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _proxy_get(handler, upstream_path: str) -> None:
    # Forward query string
    parsed = urlparse(handler.path)
    if parsed.query:
        upstream_path = f"{upstream_path}?{parsed.query}"
    try:
        conn = http.client.HTTPConnection(KENN_HOST, KENN_PORT, timeout=60)
        headers = {
            "Accept": handler.headers.get("Accept", "*/*"),
            "Accept-Language": handler.headers.get("Accept-Language", ""),
        }
        conn.request("GET", upstream_path, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        handler.send_response(resp.status)
        ct = resp.getheader("Content-Type", "application/octet-stream")
        handler.send_header("Content-Type", ct)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
    except (ConnectionRefusedError, OSError):
        _kenn_unavailable(handler)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _proxy_post(handler, upstream_path: str) -> None:
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length) if length else b""
    content_type = handler.headers.get("Content-Type", "application/json")
    try:
        conn = http.client.HTTPConnection(KENN_HOST, KENN_PORT, timeout=120)
        conn.request(
            "POST",
            upstream_path,
            body=body,
            headers={"Content-Type": content_type, "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        data = resp.read()
        handler.send_response(resp.status)
        ct = resp.getheader("Content-Type", "application/json")
        handler.send_header("Content-Type", ct)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(data)
    except (ConnectionRefusedError, OSError):
        _kenn_unavailable(handler)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _kenn_unavailable(handler) -> None:
    body = json.dumps({"error": "KENN engine unavailable. Start it with: python3 scripts/serve.py"}).encode()
    handler.send_response(503)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
