#!/usr/bin/env python3
"""Local Audio_Too website and agent data bridge."""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from db import init_db, now
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# nite_core, audio_analysis, kenn, thursday are pip-installed editable;
# only non-package dirs still need sys.path.
for _p in (REPO_ROOT, REPO_ROOT / "scripts", REPO_ROOT / "server"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import demo_feedback
import demo_routes
# studio: plain studio/ is needed too (not just audio_analysis/kenn) --
# mix_review.py's revision-agent integration does `from agents.MixReview...`
# (docs/CODEBASE_AUDIT_2026-07-06.md); studio/audiogen(/audiogen) is needed
# because thursday.autonomous_producer imports AudioGen's composition package.
for _p in (
    REPO_ROOT / "studio" / "audio_analysis", REPO_ROOT / "studio" / "kenn",
    REPO_ROOT / "studio" / "audiogen" / "audiogen", REPO_ROOT / "studio" / "audiogen",
    REPO_ROOT / "studio", Path(__file__).resolve().parent,
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from audio_analysis.mix_review import mix_review
if os.getenv("AUDIO_TOO_MIX_REVIEW_LLM", "").strip().lower() in {"1", "true", "yes", "on"}:
    try:
        from kenn.llm import llm_rewrite as _mix_critique_provider

        mix_review.set_mix_critique_provider(_mix_critique_provider)
    except ImportError:
        pass
import tips_gaps
import tips_queries
from app.routes.public_api_routes import handle_public_get
from app.routes.automix_routes import handle_automix_get, handle_automix_post
from app.routes.benchmark_routes import handle_benchmark_get, handle_benchmark_post
from app.routes.thursday_routes import handle_thursday_get, handle_thursday_post
from app.routes.auth_routes import handle_auth_get, handle_auth_post
from app.routes.admin_routes import handle_admin_get, handle_admin_post
from app.routes.creative_lab_routes import handle_creative_lab_get, handle_creative_lab_post
from app.routes.mix_review_routes import handle_mix_report_public_get, handle_mix_review_get, handle_mix_review_post, handle_podcast_report_public_get
from app.routes.ableton_routes import handle_ableton_post
from app.routes.ableton_read_routes import handle_ableton_get
from app.routes.live_analysis_routes import handle_live_analyze_post
import public_routes
import request_validation
import session_auth
import stem_uploads
from app import api_contract
from app import request_security
from app.routes.api_contract_routes import handle_api_contract_get
from app.api_errors import safe_error_payload
from app.route_policy import (
    AUTHENTICATED_GET_PREFIXES,
    AUTHENTICATED_GET_ROUTES,
    PUBLIC_GET_ROUTES,
    PUBLIC_POST_ROUTES,
    route_access,
)
from app.routes.invoice_routes import handle_invoice_get
from app.routes.kenn_proxy_routes import handle_kenn_get, handle_kenn_post
from app.routes.static_routes import STATIC_ROUTE_MAP, handle_static_get
from app.server_config import HOST, PORT, validate_startup_secrets
from app.background_services import start_background_services

__all__ = [
    "AUTHENTICATED_GET_PREFIXES",
    "AUTHENTICATED_GET_ROUTES",
    "PUBLIC_GET_ROUTES",
    "PUBLIC_POST_ROUTES",
    "STATIC_ROUTE_MAP",
    "Handler",
    "route_access",
    "safe_error_payload",
]


ROOT = Path(__file__).resolve().parent
BUSINESS_ROOT = ROOT.parent
AGENTS_ROOT = BUSINESS_ROOT / "agents"
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))
from Shared.activity_log import log_event  # noqa: E402
MAX_JSON_BODY_BYTES = 1024 * 1024





class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        status = str(args[1]) if len(args) > 1 and str(args[1]).isdigit() else ""
        self.structured_log("http_request", status=status)

    def request_id(self) -> str:
        request_id = getattr(self, "_request_id", "")
        if not request_id:
            request_id = secrets.token_hex(6)
            self._request_id = request_id
        return request_id

    def structured_log(self, event: str, **fields: object) -> None:
        record = {
            "timestamp": now(),
            "event": event,
            "request_id": self.request_id(),
            "method": getattr(self, "command", ""),
            "path": urlparse(getattr(self, "path", "")).path,
            "client": getattr(self, "client_address", ("unknown", 0))[0],
            **fields,
        }
        print(json.dumps(record, ensure_ascii=True), file=sys.stderr, flush=True)

    def authorized(self) -> bool:
        return session_auth.verify_session_token(self.session_token())

    def session_token(self) -> str:
        return session_auth.cookie_value(self.headers.get("Cookie"))

    def require_auth(self) -> bool:
        if self.authorized():
            return True
        self.send_json(401, {"error": "Dashboard password required."})
        return False

    def request_is_same_origin(self) -> bool:
        origin = self.headers.get("Origin", "").rstrip("/")
        fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if fetch_site == "cross-site":
            return False
        if not origin:
            return True
        host = self.headers.get("Host", "").strip()
        allowed = {f"http://{host}", f"https://{host}"} if host else set()
        configured = os.getenv("AUDIO_TOO_ALLOWED_ORIGINS", "")
        allowed.update(item.strip().rstrip("/") for item in configured.split(",") if item.strip())
        return origin in allowed

    def require_private_post(self) -> bool:
        if not self.require_auth():
            return False
        if not self.request_is_same_origin():
            self.send_json(403, {"error": "Cross-origin request rejected."})
            return False
        token = self.session_token()
        csrf_token = self.headers.get("X-CSRF-Token", "")
        if not session_auth.verify_csrf_token(token, csrf_token):
            self.send_json(403, {"error": "Invalid CSRF token."})
            return False
        return True

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        # The private hub deliberately exposes speech input.  Blocking microphone
        # here overrides the user's browser permission and makes the mic button a
        # no-op even on localhost.
        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; "
            "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' "
            "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
            "frame-src 'self'",
        )
        successor = api_contract.legacy_successor(
            getattr(self, "command", ""), urlparse(getattr(self, "path", "")).path
        )
        if successor:
            self.send_header("Deprecation", "true")
            self.send_header("Sunset", api_contract.LEGACY_API_SUNSET)
            self.send_header("Link", f'<{successor}>; rel="successor-version"')
        super().end_headers()

    def send_json(self, status: int, payload: dict, *, cookie: str | None = None) -> None:
        error_id = self.request_id()
        if status >= 500:
            self.structured_log("server_error", status=status)
        payload = safe_error_payload(status, payload, error_id)
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", error_id)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def send_bytes(self, status: int, body: bytes, content_type: str, *, filename: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def send_file(
        self,
        path: Path,
        content_type: str,
        *,
        filename: str = "",
        cache_control: str = "no-store",
    ) -> None:
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", cache_control)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{Path(filename).name}"')
        self.end_headers()
        if not getattr(self, "_head_only", False):
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    self.wfile.write(chunk)

    def query_limit(self, parsed, default: int = 100) -> int:
        try:
            return max(1, min(500, int(parse_qs(parsed.query).get("limit", [str(default)])[0])))
        except ValueError:
            return default

    def do_HEAD(self) -> None:
        """Serve GET metadata without a body for browser/app capability probes."""
        self._head_only = True
        self.do_GET()

    def do_GET(self) -> None:
        requested = urlparse(self.path)
        if route_access("GET", requested.path) == "authenticated-read" and not self.require_auth():
            return
        if handle_api_contract_get(self, self.path):
            return
        dispatch_path = api_contract.dispatch_path("GET", self.path)
        parsed = urlparse(dispatch_path)
        if parsed.path.startswith(("/api/automix/", "/api/v1/automix/")):
            if not self.require_auth():
                return
            if handle_automix_get(self, dispatch_path, BUSINESS_ROOT):
                return

        if handle_benchmark_get(self, self.path):
            return
        if handle_thursday_get(self, self.path):
            return
        if handle_auth_get(self, self.path):
            return
        if handle_public_get(self, self.path):
            return
        if handle_creative_lab_get(self, self.path):
            return
        if handle_mix_review_get(self, self.path, BUSINESS_ROOT):
            return
        if demo_routes.handle_get(self, self.path):
            return
        if handle_ableton_get(self, self.path):
            return
        if handle_admin_get(self, dispatch_path):
            return

        if handle_invoice_get(self, self.path):
            return
        if handle_mix_report_public_get(self, self.path) or handle_podcast_report_public_get(self, self.path):
            return
        if handle_kenn_get(self, parsed.path):
            return
        handle_static_get(self, parsed.path)

    def read_body_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length)

    def read_json_body(self) -> dict:
        payload = json.loads(self.read_body_bytes().decode("utf-8"))
        try:
            return request_validation.validate_json_payload(payload)
        except ValueError as exc:
            raise json.JSONDecodeError(str(exc), "", 0) from exc

    def content_length(self) -> int | None:
        try:
            return int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        dispatch_path = api_contract.dispatch_path("POST", self.path)
        access = route_access("POST", parsed.path)
        length = self.content_length()
        if length is None:
            self.send_json(400, {"error": "Invalid Content-Length."})
            return
        if parsed.path in {"/api/admin/mix-review", "/api/admin/mix-stems", "/api/admin/music-analysis"}:
            max_body = mix_review.MAX_UPLOAD_BYTES * 4
        elif parsed.path in {
            "/api/automix/upload",
            "/api/automix/reference/upload",
            "/api/v1/automix/uploads",
        }:
            max_body = stem_uploads.MAX_UPLOAD_BYTES + 1024 * 1024
        elif parsed.path == "/api/thursday/transcribe":
            max_body = 3 * 1024 * 1024
        else:
            max_body = stem_uploads.MAX_UPLOAD_BYTES if parsed.path == "/api/public/stem-upload" else MAX_JSON_BODY_BYTES
        if length > max_body:
            self.send_json(413, {"error": f"Request body exceeds {max_body // (1024 * 1024)} MB limit."})
            return
        if not request_security.enforce_write_boundary(self, access):
            return
        if demo_routes.handle_post(self, parsed.path, log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor)):
            return
        if public_routes.handle_post(self, parsed.path, log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor)):
            return
        if handle_benchmark_post(self, self.path):
            return
        if handle_auth_post(self, self.path, log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor)):
            return
        if not self.require_private_post():
            return

        if handle_thursday_post(self, self.path):
            return
        if handle_automix_post(self, dispatch_path, BUSINESS_ROOT):
            return
        if handle_creative_lab_post(self, self.path, log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor)):
            return
        if handle_mix_review_post(self, self.path, log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor)):
            return
        if handle_live_analyze_post(self, self.path):
            return
        if handle_ableton_post(self, self.path, BUSINESS_ROOT, log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor)):
            return
        if handle_admin_post(self, dispatch_path, log_event=lambda kind, detail, actor: log_event(kind, detail, actor=actor)):
            return
        if handle_kenn_post(self, parsed.path):
            return

        self.send_json(404, {"error": "Not found"})


def main() -> int:
    validate_startup_secrets()
    init_db()
    start_background_services()
    tips_gaps.init_gaps_table()
    tips_queries.init_queries_table()
    stem_uploads.init_uploads_table()
    mix_review.init_reviews_table()
    # Model/session initialisation costs several seconds on first use.  Do it in
    # the background so the site starts immediately and the first spoken reply
    # does not pay that cold-start penalty.
    try:
        from thursday.voice_output import warm_tts

        threading.Thread(target=warm_tts, name="TTSWarmup", daemon=True).start()
    except ImportError:
        pass
    demo_feedback.init_feedback_table()
    # KENN and local TTS are CPU-heavy.  A single-threaded HTTPServer stalls the
    # whole hub (including status and auth requests) while either one is running.
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"Audio_Too website running at http://{HOST}:{PORT}")
    print(f"Public site:         http://{HOST}:{PORT}/")
    print(f"Thursday chat:       http://{HOST}:{PORT}/thursday")
    print(f"Umbrella hub:        http://{HOST}:{PORT}/hub")
    print(f"Unified dashboard:   http://{HOST}:{PORT}/dashboard")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
