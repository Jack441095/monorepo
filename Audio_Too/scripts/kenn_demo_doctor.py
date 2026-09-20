#!/usr/bin/env python3
"""Readiness checks for the scoped KENN tester demo."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL = "http://127.0.0.1:8090"


def fetch(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


def check(condition: bool, label: str, detail: str = "") -> dict:
    return {"ok": bool(condition), "label": label, "detail": detail}


def local_checks(base_url: str) -> list[dict]:
    checks: list[dict] = []
    status, body = fetch(f"{base_url}/api/health")
    checks.append(check(status == 200 and '"ok": true' in body, "KENN health endpoint", f"HTTP {status}"))

    status, body = fetch(base_url)
    checks.append(check(status == 200 and "Kernel Engineering Neural Network" in body, "Tester page subtitle", f"HTTP {status}"))
    checks.append(check("No saved reference" not in body and "Save reference" not in body, "Saved-reference UI hidden"))

    status, _ = fetch(f"{base_url}/api/mix-references")
    checks.append(check(status == 404, "Saved-reference API hidden", f"HTTP {status}"))

    status, body = fetch(f"{base_url}/app.js")
    checks.append(check(status == 200 and "renderMixDecisionCard" in body, "Mix Review decision panel JS", f"HTTP {status}"))
    checks.append(check("sessionStorage" in body and "kenn_latest_mix_review_context" in body, "Mix Review context memory JS"))

    status, body = fetch(f"{base_url}/styles.css")
    checks.append(check(status == 200 and "mix-decision-card" in body and "context-pill" in body, "Tester CSS upgrades", f"HTTP {status}"))
    return checks


def file_checks() -> list[dict]:
    paths = [
        "scripts/run_kenn_tester_demo.sh",
        "scripts/kenn_tester_tunnel.sh",
        "scripts/kenn_feedback_report.py",
        "scripts/kenn_feedback_repair.py",
        "docs/KENN_PERMANENT_DEMO.md",
        "docs/cloudflared-kenn-demo.example.yml",
        "docs/launchd/com.audio-too.kenn-demo.plist.example",
        "docs/launchd/com.audio-too.kenn-tunnel.plist.example",
    ]
    checks = [check((ROOT / path).exists(), f"Required file: {path}") for path in paths]
    for script in ("scripts/run_kenn_tester_demo.sh", "scripts/kenn_tester_tunnel.sh", "scripts/kenn_feedback_repair.py"):
        path = ROOT / script
        checks.append(check(path.exists() and path.stat().st_mode & 0o111, f"Executable: {script}"))
    return checks


def tool_checks() -> list[dict]:
    checks = [
        check(shutil.which("cloudflared") is not None, "cloudflared installed"),
    ]
    config = Path.home() / ".cloudflared" / "kenn-demo.yml"
    checks.append(check(config.exists(), "Named tunnel config exists", str(config)))
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    checks.append(check((launch_agents / "com.audio-too.kenn-demo.plist").exists(), "KENN LaunchAgent installed"))
    checks.append(check((launch_agents / "com.audio-too.kenn-tunnel.plist").exists(), "Tunnel LaunchAgent installed"))
    return checks


def command_checks() -> list[dict]:
    checks: list[dict] = []
    commands = [
        ("bash syntax", ["bash", "-n", "scripts/run_kenn_tester_demo.sh", "scripts/kenn_tester_tunnel.sh"]),
        ("Python compile", [sys.executable, "-m", "py_compile", "scripts/kenn_feedback_repair.py", "scripts/kenn_feedback_report.py", "KENN/server.py"]),
    ]
    for label, cmd in commands:
        completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        checks.append(check(completed.returncode == 0, label, completed.stderr.strip() or completed.stdout.strip()))
    return checks


def print_report(checks: list[dict], *, as_json: bool = False) -> int:
    if as_json:
        print(json.dumps({"ok": all(item["ok"] for item in checks), "checks": checks}, indent=2, ensure_ascii=True))
    else:
        print("KENN demo doctor")
        print("")
        for item in checks:
            marker = "OK" if item["ok"] else "WARN"
            detail = f" ({item['detail']})" if item.get("detail") else ""
            print(f"[{marker}] {item['label']}{detail}")
        failed = [item for item in checks if not item["ok"]]
        if failed:
            print("")
            print("Next actions:")
            for item in failed:
                if item["label"] == "Named tunnel config exists":
                    print("- For a stable URL, follow docs/KENN_PERMANENT_DEMO.md and create ~/.cloudflared/kenn-demo.yml.")
                elif "LaunchAgent" in item["label"]:
                    print("- Optional: install LaunchAgents from docs/KENN_PERMANENT_DEMO.md after the named tunnel works manually.")
                elif item["label"] == "KENN health endpoint":
                    print("- Start KENN with ./scripts/run_kenn_tester_demo.sh.")
                else:
                    print(f"- Check: {item['label']}")
    return 0 if all(item["ok"] for item in checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Check KENN tester demo readiness.")
    parser.add_argument("--url", default=DEFAULT_LOCAL, help="Local or public KENN base URL to check.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks = [*file_checks(), *command_checks(), *tool_checks(), *local_checks(args.url.rstrip("/"))]
    return print_report(checks, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
