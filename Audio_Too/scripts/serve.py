#!/usr/bin/env python3
"""Start Audio_Too (website :8080 + Ableton chat :8090) and optionally open the browser."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(REPO_ROOT / "business") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "business"))

from repo_python import python_executable  # noqa: E402

HOST = "127.0.0.1"
WEB_PORT = 8080
ABLETON_PORT = 8090
DEFAULT_OPEN_PATH = "/hub"
LOG_DIR = REPO_ROOT / "data" / "logs"

_children: list[subprocess.Popen] = []


def website_python_command(fallback: str) -> list[str]:
    """Prefer the native arm64 runtime for ONNX TTS on Apple Silicon."""
    configured = os.getenv("AUDIO_TOO_WEBSITE_PYTHON", "").strip()
    candidate = Path(configured).expanduser() if configured else None
    if candidate and candidate.exists():
        return [str(candidate)]
    native_envs = sorted(REPO_ROOT.glob(".venv-py313-*/bin/python"), reverse=True)
    if sys.platform == "darwin" and native_envs:
        return ["arch", "-arm64", str(native_envs[0])]
    return [fallback]


def load_env() -> None:
    env_path = REPO_ROOT / ".env"
    example = REPO_ROOT / ".env.example"
    if not env_path.exists() and example.exists():
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created .env from .env.example.")
        print("Edit AUDIO_TOO_DASHBOARD_PASSWORD when ready; AUDIO_TOO_DEV=1 allows local start until then.")
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
    if os.environ.get("AUDIO_TOO_DEV", "").strip() not in {"1", "true", "yes", "on"}:
        if os.environ.get("AUDIO_TOO_DASHBOARD_PASSWORD", "") == "change-me":
            os.environ["AUDIO_TOO_DEV"] = "1"
            print("Note: using AUDIO_TOO_DEV=1 while password is still 'change-me' in .env.")


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def pids_on_port(port: int) -> list[int]:
    try:
        completed = subprocess.run(
            ["lsof", "-tiTCP:%s" % port, "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    out: list[int] = []
    for part in completed.stdout.split():
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def stop_port(port: int, label: str) -> None:
    pids = pids_on_port(port)
    if not pids:
        return
    print(f"Stopping {label} on port {port} (PID {' '.join(map(str, pids))})…")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(0.5)


def wait_for_port(host: str, port: int, *, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_open(host, port):
            return True
        time.sleep(0.2)
    return False


def start_ableton_web(python: str) -> None:
    if port_open(HOST, ABLETON_PORT):
        print(f"Ableton chat already running: http://{HOST}:{ABLETON_PORT}")
        return
    print(f"Starting Ableton chat at http://{HOST}:{ABLETON_PORT}")
    proc = subprocess.Popen(
        [python, str(REPO_ROOT / "studio" / "kenn" / "kenn" / "main.py"), "web"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _children.append(proc)
    time.sleep(0.8)


def start_detached_process(cmd: list[str], label: str, log_name: str) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / log_name
    stream = log_path.open("ab")
    print(f"Starting {label}; log: {log_path.relative_to(REPO_ROOT)}")
    return subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def open_browser(path: str) -> None:
    url = f"http://{HOST}:{WEB_PORT}{path if path.startswith('/') else '/' + path}"
    print(f"Opening {url}")
    webbrowser.open(url)


def cleanup_children() -> None:
    for proc in _children:
        if proc.poll() is None:
            proc.terminate()
    for proc in _children:
        if proc.poll() is None:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start Audio_Too website and Ableton chat, optionally open the browser.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Stop anything on :8080 and :8090 before starting.",
    )
    parser.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open the umbrella hub in your default browser once the site is ready (default: on).",
    )
    parser.add_argument(
        "--path",
        default=DEFAULT_OPEN_PATH,
        help=f"Browser path after start (default: {DEFAULT_OPEN_PATH}).",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Start both local services in the background and return after readiness checks.",
    )
    args = parser.parse_args(argv)

    load_env()
    python = python_executable()

    if args.restart:
        stop_port(WEB_PORT, "website")
        stop_port(ABLETON_PORT, "Ableton chat")
    elif port_open(HOST, WEB_PORT):
        print(f"Port {WEB_PORT} is already in use — site may already be running.")
        print(f"  Hub:       http://{HOST}:{WEB_PORT}/hub")
        print(f"  Dashboard: http://{HOST}:{WEB_PORT}/dashboard")
        print("To restart everything: ./audio-too start --restart")
        if args.open:
            open_browser(args.path)
        return 0

    if args.detach:
        # Since business/app/server.py now runs KENN and the Automix worker
        # internally in background threads, we only need to start the single website process.
        start_detached_process([*website_python_command(python), str(REPO_ROOT / "business" / "app" / "server.py")], "Audio_Too website", "website.log")
        if not wait_for_port(HOST, WEB_PORT):
            print(f"Website did not become ready on :{WEB_PORT}. Check {LOG_DIR / 'website.log'}", file=sys.stderr)
            return 1
        print(f"Website ready: http://{HOST}:{WEB_PORT}")
        print(f"Hub:           http://{HOST}:{WEB_PORT}/hub")
        if args.open:
            open_browser(args.path)
        return 0

    def handle_signal(_signum: int, _frame: object) -> None:
        cleanup_children()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"Starting Audio_Too website (with unified KENN and Automix worker) at http://{HOST}:{WEB_PORT}")
    print(f"Umbrella hub:        http://{HOST}:{WEB_PORT}/hub")
    print(f"Unified dashboard:   http://{HOST}:{WEB_PORT}/dashboard")
    print("Press Ctrl+C to stop.")
 
    website_proc = subprocess.Popen(
        [*website_python_command(python), str(REPO_ROOT / "business" / "app" / "server.py")],
        cwd=REPO_ROOT,
    )
    _children.append(website_proc)
 
    if not wait_for_port(HOST, WEB_PORT):
        print("Website did not become ready in time. Check .env and terminal output.", file=sys.stderr)
        cleanup_children()
        return 1

    if args.open:
        open_browser(args.path)

    try:
        return website_proc.wait()
    except KeyboardInterrupt:
        print("\nStopped.")
        cleanup_children()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
