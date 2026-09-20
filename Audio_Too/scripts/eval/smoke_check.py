#!/usr/bin/env python3
"""Quick smoke checks for the local Audio_Too stack."""

from __future__ import annotations

import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        example = ROOT / ".env.example"
        if example.exists():
            path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()
HOST = os.getenv("AUDIO_TOO_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("AUDIO_TOO_PORT", "8080"))
if os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "audio-too-admin") == "audio-too-admin":
    os.environ.setdefault("AUDIO_TOO_DEV", "1")
os.environ.setdefault("AUDIO_TOO_DEV", "1")
# Must match business/app/session_auth.py::dashboard_password()'s own
# default exactly -- this was hardcoded to "change-me" here, which never
# matched the server's real default ("audio-too-admin"), so login always
# failed with a live server started without AUDIO_TOO_DASHBOARD_PASSWORD set.
PASSWORD = os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "audio-too-admin")
BASE = f"http://{HOST}:{WEB_PORT}"

COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))
CSRF_TOKEN = ""


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"OK: {message}")


def port_open() -> bool:
    try:
        with socket.create_connection((HOST, WEB_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def ensure_server() -> subprocess.Popen[bytes] | None:
    if port_open():
        return None
    print(f"No server on port {WEB_PORT} — starting temporary instance for smoke check…")
    env = os.environ.copy()
    env.setdefault("AUDIO_TOO_DEV", "1")
    log_file = open(ROOT / "tmp_smoke_server.log", "w")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "business" / "app" / "server.py")],
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=log_file,
    )
    # Cold native audio-analysis imports can take well beyond ten seconds on
    # otherwise healthy machines. Match the packaged-release readiness budget.
    for _ in range(600):
        if port_open():
            return proc
        if proc.poll() is not None:
            fail("Website/server.py exited before listening (check .env or run ./start.sh)")
        time.sleep(0.2)
    proc.kill()
    fail(f"server did not become ready on port {WEB_PORT}")
    return None


def login() -> None:
    global CSRF_TOKEN
    data = json.dumps({"password": PASSWORD}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with OPENER.open(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"login -> HTTP {exc.code}: {body[:200]}")
    except urllib.error.URLError as exc:
        fail(f"login failed — is the server running? ({exc}). Try: ./start.sh --restart")
    if not payload.get("authenticated"):
        fail("login did not return authenticated session")
    CSRF_TOKEN = str(payload.get("csrf_token", ""))
    if not CSRF_TOKEN:
        fail("login did not return a CSRF token")


def request(
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    expect_status: int | None = None,
) -> dict:
    headers = {"Content-Type": "application/json"}
    if method.upper() not in {"GET", "HEAD", "OPTIONS"} and CSRF_TOKEN:
        headers["X-CSRF-Token"] = CSRF_TOKEN
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with OPENER.open(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        if expect_status and exc.code == expect_status:
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"error": payload}
        fail(f"{method} {path} -> HTTP {exc.code}: {payload[:200]}")
    except urllib.error.URLError as exc:
        fail(f"{method} {path} — server not reachable ({exc}). Run ./start.sh --restart")


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "business" / "app"))
    import server  # noqa: F401

    ok("server module imports")

    temp_server = ensure_server()
    try:
        return run_checks()
    finally:
        if temp_server and temp_server.poll() is None:
            temp_server.terminate()
            try:
                temp_server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                temp_server.kill()


def run_checks() -> int:
    login()
    ok("session login")

    session = request("/api/auth/session")
    if not session.get("authenticated"):
        fail("session not authenticated after login")
    ok("session cookie")

    hub = request("/api/hub/status")
    if not hub.get("modules"):
        fail("hub status missing modules")
    ok("hub status API")

    gaps = request("/api/ableton/gaps")
    if not isinstance(gaps.get("items"), list):
        fail("ableton gaps missing items list")
    if not isinstance(gaps.get("summary"), dict):
        fail("ableton gaps missing summary")
    ok("ableton gaps API")

    catalog = request("/api/public/business")
    if not catalog.get("offerings"):
        fail("public business catalog missing offerings")
    ok("public business catalog")

    tips_catalog = request("/api/public/tips")
    if not tips_catalog.get("suggested_questions"):
        fail("public tips catalog missing suggestions")
    ok("public studio tips catalog")

    tips_suggest = request("/api/public/tips/suggest?q=sidechain")
    if not isinstance(tips_suggest.get("suggestions"), list):
        fail("public tips suggest missing suggestions list")
    ok("public studio tips suggest")

    tips_ask = request(
        "/api/public/tips/ask",
        method="POST",
        body={
            "question": "How do I sidechain bass to the kick?",
            "session_id": "smoke-check-public-tips",
        },
    )
    if not tips_ask.get("answer"):
        fail("public tips ask missing answer")
    if not tips_ask.get("retrieval_only"):
        fail("public tips should be retrieval-only")
    ok("public studio tips ask")

    ask = request(
        "/api/public/ask",
        method="POST",
        body={"question": "How much does mixing cost?"},
    )
    if not ask.get("answer"):
        fail("public ask missing answer")
    if "£" not in ask.get("answer", ""):
        fail("public ask should include indicative pricing from knowledge file")
    ok("public business ask")

    hub = request("/api/admin/hub")
    if "summary" not in hub:
        fail("hub missing summary")
    ok(f"hub API ({hub['summary'].get('clients', 0)} clients)")

    dashboard = request("/api/admin/dashboard")
    if "drafts" not in dashboard:
        fail("dashboard missing drafts")
    projects = dashboard.get("records", {}).get("projects") or []
    if projects:
        stem_link = request(
            "/api/admin/projects/stem-link",
            method="POST",
            body={"project_id": projects[0]["id"], "ttl_days": 14},
        )
        if not stem_link.get("upload_url"):
            fail("stem upload link missing upload_url")
        ok("stem upload link API")
    if "enquiries" not in dashboard.get("records", {}):
        fail("dashboard missing enquiries table")
    ok("dashboard API")

    agent_result = request(
        "/api/admin/agent",
        method="POST",
        body={"task": "clients", "agent": "admin"},
    )
    if not agent_result.get("ok"):
        fail(f"agent task failed: {agent_result.get('output', '')[:120]}")
    ok(f"agent API routed to {agent_result.get('agent')}")

    blocked = request(
        "/api/admin/agent",
        method="POST",
        body={"task": "save invoice for client test", "agent": "admin"},
        expect_status=403,
    )
    if blocked.get("ok"):
        fail("expected save-invoice to be blocked from dashboard")
    ok("agent allowlist blocks save-invoice")

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "studio" / "kenn" / "kenn" / "main.py"),
            "ask",
            "--session-id",
            "smoke-check-cli",
            "how do I sidechain bass",
        ],
        cwd=ROOT / "studio" / "kenn" / "kenn",
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        fail(f"ableton ask failed: {completed.stderr[:200]}")
    if "source" not in completed.stdout.lower() and "bass" not in completed.stdout.lower():
        fail("ableton ask returned unexpected output")
    ok("ableton ask")

    repair_training = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "repair-training", "--summary-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if repair_training.returncode != 0:
        fail(f"repair-training summary failed: {repair_training.stderr[:200] or repair_training.stdout[:200]}")
    if "Raw records:" not in repair_training.stdout:
        fail("repair-training summary returned unexpected output")
    ok("repair-training summary")

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
