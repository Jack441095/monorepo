"""Thursday HTTP server — exposes the orchestrator over a local REST API.

Endpoints:
    GET  /health          — liveness check, no auth required
    POST /ask             — route a question through Thursday
    GET  /session/<id>    — fetch session metadata
    DELETE /session/<id>  — delete a session

Auth: Bearer token in Authorization header, or X-Thursday-Token header.
      Token is read from THURSDAY_SERVER_TOKEN (or AUDIO_TOO_DASHBOARD_PASSWORD).
      Fails closed — outside AUDIO_TOO_DEV, an unset/placeholder token denies every
      request and the server refuses to start. There is no publicly-known default.

Usage:
    python -m thursday.server              # start on default port 8092
    python main.py thursday --server       # same, via main CLI
    python main.py thursday --server --port 9000
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
# nite_core, audio_analysis, kenn, thursday are pip-installed editable.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server" / "agents"))

# Load .env
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

DEFAULT_PORT = int(os.environ.get("THURSDAY_SERVER_PORT", "8092"))
_lock = threading.Lock()
_rate_lock = threading.Lock()
_rate_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
MAX_REQUEST_BODY_BYTES = 256 * 1024
REQUEST_RATE_LIMITS = {"/ask": (60, 60), "/command": (30, 60)}


def _rate_allowed(client: str, path: str) -> tuple[bool, int]:
    limit, window = REQUEST_RATE_LIMITS.get(path, (60, 60))
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[(client, path)]
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
    return True, 0


# ── auth ──────────────────────────────────────────────────────────────────────

def _dev_mode() -> bool:
    return os.environ.get("AUDIO_TOO_DEV", "").strip().lower() in {"1", "true", "yes", "on"}


def _server_token() -> str:
    """The token required for Thursday API access.

    Configured via THURSDAY_SERVER_TOKEN (preferred) or AUDIO_TOO_DASHBOARD_PASSWORD.
    Fails closed: outside dev mode, an unset/placeholder token returns "" and
    _is_authorised denies every request — there is no publicly-known default.
    In dev mode a local default is allowed for frictionless localhost use.
    """
    token = (
        os.environ.get("THURSDAY_SERVER_TOKEN", "").strip()
        or os.environ.get("AUDIO_TOO_DASHBOARD_PASSWORD", "").strip()
    )
    if token and token != "change-me":
        return token
    return "thursday-dev" if _dev_mode() else ""


def _is_authorised(handler: BaseHTTPRequestHandler) -> bool:
    token = _server_token()
    if not token:
        return False  # unconfigured outside dev → deny all (fail closed)
    auth = handler.headers.get("Authorization", "")
    custom = handler.headers.get("X-Thursday-Token", "")
    if custom and secrets.compare_digest(custom, token):
        return True
    if auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], token):
        return True
    return False


def _cors_origin() -> str:
    """Scope browser access to the business origin (not '*'). Override with the
    first entry of AUDIO_TOO_ALLOWED_ORIGINS. Non-browser clients (Ableton/curl)
    ignore CORS entirely, so this only constrains cross-origin browser callers."""
    configured = os.environ.get("AUDIO_TOO_ALLOWED_ORIGINS", "").split(",")[0].strip()
    return configured or "http://127.0.0.1:8080"


# ── request handler ───────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    """HTTP handler for Thursday API requests."""

    def log_message(self, format: str, *args) -> None:
        print(f"[thursday-server] {self.address_string()} — {format % args}")

    def _send_json(
        self, status: int, data: dict, *, headers: dict[str, str] | None = None
    ) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", _cors_origin())
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str, code: str = "") -> None:
        if not code:
            code = {
                400: "invalid_request",
                401: "permission_denied",
                403: "permission_denied",
                404: "not_found",
                409: "conflict",
                429: "rate_limited",
            }.get(status, "internal_error")
        self._send_json(
            status,
            {"ok": False, "error": message, "error_code": code, "retryable": False},
        )

    def _read_json(self) -> dict | None:
        self._body_error_sent = False
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_error(400, "Invalid Content-Length")
            self._body_error_sent = True
            return None
        if length < 0 or length > MAX_REQUEST_BODY_BYTES:
            self._send_error(413, "Request body exceeds the 256 KiB limit")
            self._body_error_sent = True
            return None
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _enforce_rate_limit(self, path: str) -> bool:
        allowed, retry_after = _rate_allowed(self.client_address[0], path)
        if allowed:
            return True
        self._send_json(
            429,
            {
                "ok": False,
                "error": "Too many requests.",
                "error_code": "rate_limited",
                "retryable": True,
            },
            headers={"Retry-After": str(retry_after)},
        )
        return False

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", _cors_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Thursday-Token")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")

        if path == "/health":
            self._handle_health()
        elif path in ("", "/chat"):
            # Minimal mobile-friendly chat page, served same-origin so its
            # fetch() calls to /ask need no CORS handling and (unlike an
            # externally-hosted page) never hit browser mixed-content
            # blocking against this plain-HTTP Tailscale-only server. The
            # token itself is entered client-side and kept in
            # localStorage -- never embedded in this HTML, never sent to
            # anywhere but this same server.
            static_path = Path(__file__).resolve().parent / "static" / "chat.html"
            try:
                self._send_html(200, static_path.read_bytes())
            except OSError:
                self._send_error(404, "Chat page not found")
        elif path in ("/api/thursday/daw-sessions", "/daw-sessions"):
            if not _is_authorised(self):
                self._send_error(401, "Unauthorised")
                return
            from thursday.daw_watcher import DAWProjectWatcher
            watcher = DAWProjectWatcher()
            sessions = [s.__dict__ for s in watcher.scan_once()]
            self._send_json(200, {"ok": True, "daw_sessions": sessions})
        elif path.startswith("/session/"):
            if not _is_authorised(self):
                self._send_error(401, "Unauthorised")
                return
            session_id = path[len("/session/"):]
            self._handle_get_session(session_id)
        else:
            self._send_error(404, f"Unknown endpoint: {path}")

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")

        if path in ("/api/thursday/hud-action", "/hud-action"):
            if not _is_authorised(self):
                self._send_error(401, "Unauthorised")
                return
            if not self._enforce_rate_limit(path):
                return
            body = self._read_json() or {}
            from thursday.mac_app.thursday_hud_controller import ThursdayHUDController
            ctrl = ThursdayHUDController()
            result = ctrl.process_hud_action(str(body.get("action", "toggle")), body)
            self._send_json(200, result)
            return

        if path == "/ask":
            if not _is_authorised(self):
                self._send_error(401, "Unauthorised")
                return
            if not self._enforce_rate_limit(path):
                return
            body = self._read_json()
            if body is None:
                if not getattr(self, "_body_error_sent", False):
                    self._send_error(400, "Invalid JSON")
                return
            self._handle_ask(body)
        elif path == "/command":
            if not _is_authorised(self):
                self._send_error(401, "Unauthorised")
                return
            if not self._enforce_rate_limit(path):
                return
            body = self._read_json()
            if body is None:
                if not getattr(self, "_body_error_sent", False):
                    self._send_error(400, "Invalid JSON")
                return
            self._handle_command(body)
        else:
            self._send_error(404, f"Unknown endpoint: {path}")

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path.rstrip("/")

        if path.startswith("/session/"):
            if not _is_authorised(self):
                self._send_error(401, "Unauthorised")
                return
            if not self._enforce_rate_limit(path):
                return
            session_id = path[len("/session/"):]
            self._handle_delete_session(session_id)
        else:
            self._send_error(404, f"Unknown endpoint: {path}")

    # ── endpoint implementations ──────────────────────────────────────────────

    def _handle_health(self) -> None:
        from thursday.orchestrator import handle as _handle  # noqa: F401 — test importability
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        ollama_ok = False
        try:
            import urllib.request as _ur
            _ur.urlopen("http://127.0.0.1:11434", timeout=1)
            ollama_ok = True
        except Exception:
            pass

        self._send_json(200, {
            "ok": True,
            "service": "thursday",
            "timestamp": now,
            "ollama": ollama_ok,
            "port": DEFAULT_PORT,
        })

    def _handle_ask(self, body: dict) -> None:
        question = str(body.get("question", "")).strip()
        session_id = str(body.get("session_id", "")).strip() or None

        if not question:
            self._send_error(400, "Missing 'question' field")
            return

        from thursday.bridge import ask

        with _lock:
            result = ask(question, session_id=session_id or "")

        self._send_json(200, {"ok": result.get("status") == "succeeded", **result})

    def _handle_command(self, body: dict) -> None:
        """Typed command/result entry point: CommandEnvelope in, ResultEnvelope out."""
        from nite_core import CommandEnvelope
        from nite_core.contracts import ContractValidationError
        from thursday.command_gateway import execute_command
        from thursday.session_manager import get_or_create_session

        try:
            envelope = CommandEnvelope.from_dict(body)
        except ContractValidationError:
            self._send_error(400, "The command envelope is invalid.", "invalid_command")
            return

        with _lock:
            session = get_or_create_session(None)
            result = execute_command(envelope, session=session)

        # A ResultEnvelope is always well-formed; a failed command is still HTTP 200
        # with status="failed" so callers read the typed error rather than a raw 5xx.
        self._send_json(200, result.to_dict())

    def _handle_get_session(self, session_id: str) -> None:
        from thursday.session_manager import load_session

        session = load_session(session_id)
        if session is None:
            self._send_error(404, f"Session '{session_id}' not found")
            return

        self._send_json(200, {
            "ok": True,
            "session_id": session_id,
            "turns": len(session.get("turns", [])),
            "context": session.get("context", {}),
            "updated_at": session.get("updated_at", ""),
        })

    def _handle_delete_session(self, session_id: str) -> None:
        from thursday.session_manager import delete_session

        try:
            deleted = delete_session(session_id)
        except ValueError:
            self._send_error(400, "Invalid session ID")
            return

        if not deleted:
            self._send_error(404, f"Session '{session_id}' not found")
            return

        self._send_json(200, {"ok": True, "deleted": session_id})


# ── server lifecycle ──────────────────────────────────────────────────────────

def _require_token_or_exit() -> None:
    """Refuse to start outside dev mode without an explicit token (fail closed)."""
    if not _server_token():
        print(
            "[thursday-server] Refusing to start: no token configured. "
            "Set THURSDAY_SERVER_TOKEN (or AUDIO_TOO_DASHBOARD_PASSWORD), "
            "or set AUDIO_TOO_DEV=1 for local development.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _startup_health_checks() -> None:
    """Best-effort dependency checks, logged and printed at startup.

    Unlike KENN's warm_index() (studio/kenn/kenn/server.py), which fails
    closed with SystemExit because KENN is useless without its index, none
    of these block startup: Thursday's core routing/orchestration works
    without any of them -- only specific optional paths (the LLM brain,
    anything that writes session/plan/reminder data) degrade if they're
    unavailable. Previously there was no signal at all: the server would
    report "listening" successfully and only fail on the first real request
    that needed the missing dependency.
    """
    import logging

    logger = logging.getLogger("thursday.server")

    try:
        import httpx

        base_url = os.environ.get("AUDIO_TOO_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        native_base = base_url[:-3] if base_url.endswith("/v1") else base_url
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{native_base}/api/tags")
            if res.status_code != 200:
                raise RuntimeError(f"unexpected status {res.status_code}")
        print("[thursday-server] Ollama reachable.")
    except Exception as e:
        logger.warning("Ollama unreachable at startup (LLM-backed features will be degraded): %s", e)
        print(f"[thursday-server] WARNING: Ollama unreachable ({e}) -- LLM-backed features degraded.")

    from thursday.runtime_paths import DATA_DIR

    data_dir = DATA_DIR
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".startup_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        print(f"[thursday-server] Data directory writable: {data_dir}")
    except OSError as e:
        logger.warning("Thursday data directory is not writable at startup: %s", e)
        print(f"[thursday-server] WARNING: data directory {data_dir} is not writable ({e}).")


def start(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    """Start the Thursday HTTP server (blocking)."""
    from log_setup import setup_server_logging
    from thursday.monitor import start_background_monitor
    from thursday.runtime_paths import LOG_DIR, ensure_runtime_state

    ensure_runtime_state()
    setup_server_logging("thursday", LOG_DIR)
    _require_token_or_exit()
    _startup_health_checks()
    start_background_monitor()
    print("[thursday-server] Background monitor started (proactive checks run on their own schedule).")
    server = HTTPServer((host, port), Handler)
    print(f"[thursday-server] Listening on http://{host}:{port}")
    print(f"[thursday-server] Health: http://{host}:{port}/health")
    print(f"[thursday-server] Ask:    POST http://{host}:{port}/ask")
    print("[thursday-server] Auth:   X-Thursday-Token or Bearer <THURSDAY_SERVER_TOKEN>")
    print("[thursday-server] Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[thursday-server] Shutting down.")
        server.shutdown()


def start_background(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> HTTPServer:
    """Start the Thursday HTTP server in a background thread. Returns the server."""
    server = HTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Thursday HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    start(host=args.host, port=args.port)
