#!/usr/bin/env python3
"""Demo-only server for external Audio Tips LLM testers.

This intentionally exposes only the tester demo page and /api/demo/* routes.
Do not use the full website server for public tester access unless you also
intend to expose the public site, hub, and protected dashboard routes.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import demo_feedback
import demo_routes
import tips_gaps
import tips_queries
from db import init_db

ROOT = Path(__file__).resolve().parent
BUSINESS_ROOT = ROOT.parent
STATIC_ROOT = ROOT / "static"
AGENTS_ROOT = BUSINESS_ROOT / "agents"
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))
from Shared.activity_log import log_event  # noqa: E402

HOST = os.getenv("AUDIO_TOO_DEMO_HOST", "127.0.0.1")
PORT = int(os.getenv("AUDIO_TOO_DEMO_PORT", "8091"))
MAX_JSON_BODY_BYTES = 1024 * 1024


def load_env() -> None:
    env_path = BUSINESS_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: int, payload: dict, *, cookie: str | None = None) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_body_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length)

    def read_json_body(self) -> dict:
        return json.loads(self.read_body_bytes().decode("utf-8"))

    def content_length(self) -> int | None:
        try:
            return int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if demo_routes.handle_get(self, self.path):
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = self.content_length()
        if length is None:
            self.send_json(400, {"error": "Invalid Content-Length."})
            return
        if length > MAX_JSON_BODY_BYTES:
            self.send_json(413, {"error": "Request body exceeds 1 MB limit."})
            return
        if demo_routes.handle_post(
            self,
            parsed.path,
            log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor),
        ):
            return
        self.send_json(404, {"error": "Not found"})

    def serve_static(self, path: str) -> None:
        allowed = {
            "/": "demo.html",
            "/demo": "demo.html",
            "/demo.html": "demo.html",
            "/demo.js": "demo.js",
            "/styles.css": "styles.css",
        }
        filename = allowed.get(path)
        if not filename:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        target = (STATIC_ROOT / filename).resolve()
        try:
            target.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        if not target.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    global HOST, PORT
    load_env()
    HOST = os.getenv("AUDIO_TOO_DEMO_HOST", HOST)
    PORT = int(os.getenv("AUDIO_TOO_DEMO_PORT", str(PORT)))
    init_db()
    tips_gaps.init_gaps_table()
    tips_queries.init_queries_table()
    demo_feedback.init_feedback_table()
    server = HTTPServer((HOST, PORT), DemoHandler)
    print(f"Audio Tips LLM demo-only server running at http://{HOST}:{PORT}/demo")
    print("Expose this port for testers; it does not serve dashboard or hub routes.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
