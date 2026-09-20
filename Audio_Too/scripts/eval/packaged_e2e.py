#!/usr/bin/env python3
"""Build, clean-install, and exercise a packaged Audio_Too release candidate."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nite_core.release_package import build_package, extract_and_verify  # noqa: E402

def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _available_port(excluded: set[int]) -> int:
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port not in excluded:
            return port


def _wait_port(port: int, process: subprocess.Popen, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(port):
            return
        if process.poll() is not None:
            raise RuntimeError(f"Service on :{port} exited with {process.returncode}")
        time.sleep(0.2)
    raise RuntimeError(f"Service on :{port} did not become ready")


def _run(command: list[str], root: Path, env: dict[str, str], timeout: int = 180) -> dict:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        output = ((completed.stdout or "") + (completed.stderr or ""))[-4000:]
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}\n{output}")
    return {
        "command": command,
        "seconds": round(time.perf_counter() - started, 3),
        "output": (completed.stdout or "")[-1000:].strip(),
    }


class HttpClient:
    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.csrf = ""

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, str]:
        request_headers = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        if method not in {"GET", "HEAD", "OPTIONS"} and self.csrf:
            request_headers.setdefault("X-CSRF-Token", self.csrf)
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"{method} {url} returned {exc.code}: "
                f"{exc.read().decode('utf-8', errors='replace')[:1000]}"
            ) from exc

    def json(self, url: str, **kwargs) -> dict:
        status, body, _ = self.request(url, **kwargs)
        if not 200 <= status < 300:
            raise RuntimeError(f"Unexpected HTTP status {status} for {url}")
        payload = json.loads(body)
        if payload.get("csrf_token"):
            self.csrf = str(payload["csrf_token"])
        return payload


def _start(
    command: list[str], root: Path, env: dict[str, str], log_path: Path
) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = log_path.open("wb")
    process = subprocess.Popen(
        command,
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    stream.close()
    return process


def _stop(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def run(output_dir: Path, *, reuse_runtime: bool = False, keep_install: bool = False) -> dict:
    ports: set[int] = set()
    web_port = _available_port(ports)
    ports.add(web_port)
    kenn_port = _available_port(ports)
    ports.add(kenn_port)
    thursday_port = _available_port(ports)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = output_dir / f"audio_too_release_{stamp}.tar.gz"
    started = time.perf_counter()
    steps: dict[str, object] = {}

    checkpoint = time.perf_counter()
    package_manifest = build_package(ROOT, archive)
    steps["package_seconds"] = round(time.perf_counter() - checkpoint, 3)

    temporary = tempfile.mkdtemp(prefix="audio-too-package-e2e-")
    install_parent = Path(temporary)
    package_root, verified = extract_and_verify(archive, install_parent)
    processes: list[subprocess.Popen] = []
    log_dir = package_root / "data/logs/package-e2e"
    try:
        env = os.environ.copy()
        env.update(
            {
                "AUDIO_TOO_DEV": "1",
                "AUDIO_TOO_DASHBOARD_PASSWORD": "package-e2e-password",
                "AUDIO_TOO_SESSION_SECRET": "package-e2e-session-secret-at-least-32-characters",
                "AUDIO_TOO_NOTIFY": "0",
                "AUDIO_TOO_EMAIL_ENABLED": "0",
                "AUDIO_TOO_LLM_ENABLED": "0",
                "AUDIO_TOO_ALLOW_EXTERNAL_EMAIL": "0",
                "AUDIO_TOO_ALLOW_DESKTOP_AUTOMATION": "0",
                "AUDIO_TOO_ALLOW_DAW_CONTROL": "0",
                "AUDIO_TOO_ALLOW_AUDIO_CAPTURE": "0",
                "THURSDAY_SERVER_TOKEN": "package-e2e-thursday-token",
                "THURSDAY_SERVER_PORT": str(thursday_port),
                "AUDIO_TOO_HOST": "127.0.0.1",
                "AUDIO_TOO_PORT": str(web_port),
                "AUDIO_TOO_ALLOWED_ORIGINS": f"http://127.0.0.1:{web_port}",
                "KENN_HOST": "127.0.0.1",
                "KENN_PORT": str(kenn_port),
                "KENN_LM_ENABLED": "0",
                "PYTHONUNBUFFERED": "1",
            }
        )
        if reuse_runtime:
            python = ROOT / ".venv/bin/python"
            if not python.exists():
                raise RuntimeError("--reuse-runtime requires the repository .venv")
            env["AUDIO_TOO_PYTHON"] = str(python)
            steps["install"] = {"mode": "reused", "python": str(python)}
        else:
            bootstrap = ROOT / ".venv/bin/python"
            if not bootstrap.exists():
                raise RuntimeError("Python 3.12 bootstrap runtime is unavailable")
            env["AUDIO_TOO_PYTHON"] = str(bootstrap)
            steps["install"] = _run(
                [str(package_root / "audio-too"), "setup"],
                package_root,
                env,
                timeout=1200,
            )
            python = package_root / ".venv/bin/python"
            if not python.exists():
                raise RuntimeError("Clean setup did not create .venv/bin/python")

        steps["launcher"] = _run(
            [str(package_root / "audio-too"), "help"], package_root, env
        )
        kenn = _start(
            [str(python), "studio/kenn/kenn/main.py", "web"],
            package_root,
            env,
            log_dir / "kenn.log",
        )
        processes.append(kenn)
        _wait_port(kenn_port, kenn, timeout=180.0)
        website = _start(
            [str(python), "server/app/server.py"],
            package_root,
            env,
            log_dir / "website.log",
        )
        processes.append(website)
        _wait_port(web_port, website, timeout=120.0)
        thursday = _start(
            [
                str(python),
                "thursday/main.py",
                "--server",
                "--port",
                str(thursday_port),
            ],
            package_root,
            env,
            log_dir / "thursday.log",
        )
        processes.append(thursday)
        _wait_port(thursday_port, thursday)

        client = HttpClient()
        web_base = f"http://127.0.0.1:{web_port}"
        thursday_base = f"http://127.0.0.1:{thursday_port}"
        status, hub_html, content_type = client.request(f"{web_base}/hub")
        if status != 200 or content_type != "text/html" or b"Audio_Too" not in hub_html:
            raise RuntimeError("Packaged hub HTML did not load")
        login = client.json(
            f"{web_base}/api/auth/login",
            method="POST",
            body={"password": "package-e2e-password"},
            headers={"Origin": web_base},
        )
        if not login.get("authenticated"):
            raise RuntimeError("Packaged dashboard login failed")
        hub_status = client.json(f"{web_base}/api/hub/status")
        if not hub_status.get("modules"):
            raise RuntimeError("Packaged hub status has no modules")
        hub_answer = client.json(
            f"{web_base}/api/thursday/ask",
            method="POST",
            body={
                "question": "How do I sidechain the bass to the kick?",
                "session_id": "packaged-hub",
            },
            headers={"Origin": web_base},
        )
        if not hub_answer.get("answer") or hub_answer.get("service") != "kenn":
            raise RuntimeError(f"Packaged hub routing failed: {hub_answer}")
        voice_status, voice_wav, voice_type = client.request(
            f"{web_base}/api/thursday/speak",
            method="POST",
            body={"text": "Package voice check.", "voice": "thursday"},
            headers={"Origin": web_base},
        )
        if (
            voice_status != 200
            or voice_type != "audio/wav"
            or not voice_wav.startswith(b"RIFF")
        ):
            raise RuntimeError("Packaged voice synthesis did not return a WAV file")

        thursday_client = HttpClient()
        health = thursday_client.json(f"{thursday_base}/health")
        direct_answer = thursday_client.json(
            f"{thursday_base}/ask",
            method="POST",
            body={
                "question": "How do I sidechain the bass to the kick?",
                "session_id": "direct",
            },
            headers={"X-Thursday-Token": "package-e2e-thursday-token"},
        )
        if not health.get("ok") or not direct_answer.get("answer"):
            raise RuntimeError("Packaged Thursday HTTP workflow failed")
        steps["http"] = {
            "hub": "passed",
            "hub_service": hub_answer.get("service"),
            "hub_sources": len(hub_answer.get("sources") or []),
            "thursday": "passed",
            "voice_wav_bytes": len(voice_wav),
        }

        steps["kenn_cli"] = _run(
            [
                str(package_root / "ableton"),
                "ask",
                "--session-id",
                "packaged-cli",
                "How do I sidechain the bass to the kick?",
            ],
            package_root,
            env,
        )
        steps["thursday_cli"] = _run(
            [
                str(package_root / "audio-too"),
                "thursday",
                "--new-session",
                "How do I sidechain the bass to the kick?",
            ],
            package_root,
            env,
        )
        voice_code = """
from thursday.orchestrator import handle
from thursday.session_manager import new_session
from thursday.voice import execute_voice_command_result
result = execute_voice_command_result(
    'How do I sidechain the bass to the kick?', new_session(), handle
)
assert result.error is None, result.error
assert result.result.get('answer')
assert result.result.get('service') == 'kenn', result.result
print(result.result['service'], len(result.result.get('sources') or []))
"""
        steps["voice_boundary"] = _run(
            [str(python), "-c", voice_code], package_root, env
        )
        steps["runtime_seconds"] = round(time.perf_counter() - started, 3)
    finally:
        _stop(processes)
        if sys.exc_info()[0] is not None and log_dir.exists():
            failure_logs = output_dir / f"packaged_e2e_failure_logs_{stamp}"
            shutil.copytree(log_dir, failure_logs, dirs_exist_ok=True)
        if not keep_install:
            shutil.rmtree(install_parent, ignore_errors=True)

    report = {
        "schema": "audio_too.packaged_e2e.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "clean_dependency_install": not reuse_runtime,
        "archive": str(archive.relative_to(ROOT)),
        "archive_bytes": archive.stat().st_size,
        "package_files": package_manifest["file_count"],
        "package_uncompressed_bytes": package_manifest["total_bytes"],
        "verified_files": verified["file_count"],
        "index_version": package_manifest["index_version"],
        "private_runtime_data_in_package": False,
        "ports": {
            "website": web_port,
            "kenn": kenn_port,
            "thursday": thursday_port,
        },
        "steps": steps,
        "total_seconds": round(time.perf_counter() - started, 3),
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path = output_dir / f"packaged_e2e_{stamp}.json"
    report_path.write_text(encoded, encoding="utf-8")
    (output_dir / "packaged_e2e_latest.json").write_text(encoded, encoding="utf-8")
    (output_dir / "packaged_e2e_latest.md").write_text(
        "# Audio_Too packaged end-to-end rehearsal\n\n"
        f"- Status: **{report['status']}**\n"
        f"- Clean dependency install: {report['clean_dependency_install']}\n"
        f"- Package files: {report['package_files']}\n"
        f"- Package bytes: {report['archive_bytes']}\n"
        f"- KENN index: `{report['index_version']}`\n"
        "- Hub HTTP workflow: passed\n"
        "- KENN CLI workflow: passed\n"
        "- Thursday CLI and HTTP workflows: passed\n"
        "- Hardware-independent voice command boundary: passed\n"
        f"- Total: {report['total_seconds']} seconds\n"
        f"- Evidence: `{report_path.relative_to(ROOT)}`\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/release")
    parser.add_argument("--reuse-runtime", action="store_true")
    parser.add_argument("--keep-install", action="store_true")
    args = parser.parse_args()
    report = run(
        args.output.resolve(),
        reuse_runtime=args.reuse_runtime,
        keep_install=args.keep_install,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
