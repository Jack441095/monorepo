#!/usr/bin/env python3
"""KENN Companion Runner & macOS Menu Bar Status Utility.

Provides lightweight status monitoring, background daemon management,
and quick actions (Launch Server, Open Web Dashboard, Install Bridge,
Run Session Doctor) for KENN Mix Assistant.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "server.py"
PID_FILE = REPO_ROOT / ".kenn_server.pid"
PORT = int(os.environ.get("KENN_PORT", 8090))
HOST = os.environ.get("KENN_HOST", "127.0.0.1")
BASE_URL = f"http://{HOST}:{PORT}"


def check_server_health(timeout: float = 1.0) -> dict | None:
    """Query KENN server health endpoint. Return JSON dict or None."""
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/health", headers={"User-Agent": "KENN-Companion/0.1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = resp.read().decode("utf-8")
                return json.loads(data)
    except Exception:
        pass
    return None


def is_server_online() -> bool:
    return check_server_health() is not None


def start_server_process() -> subprocess.Popen | None:
    """Start KENN server in background if not already running."""
    if is_server_online():
        print(f"[*] KENN server is already running at {BASE_URL}")
        return None

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT / 'source'}:{REPO_ROOT / 'scripts'}:{REPO_ROOT / 'studio'}:{env.get('PYTHONPATH', '')}"


    log_file = REPO_ROOT / "kenn_server.log"
    out_fh = open(log_file, "a")


    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=out_fh,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"[+] Started KENN server (PID: {proc.pid}). Logging to {log_file}")


    # Wait up to 5 seconds for health check
    for _ in range(25):
        time.sleep(0.2)
        if is_server_online():
            print(f"[✓] KENN server online at {BASE_URL}")
            return proc
    print("[!] Server process started but health check timed out. Check kenn_server.log")
    return proc


def stop_server_process() -> bool:
    """Stop KENN server process using PID file or port lookup."""
    stopped = False
    if PID_FILE.is_file():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            stopped = True
        except (ProcessLookupError, ValueError):
            pass
        except Exception as err:
            print(f"[!] Error stopping PID: {err}")
        finally:
            PID_FILE.unlink(missing_ok=True)
    if stopped:
        print("[✓] Stopped KENN server process.")
        return True
    print("[*] No running KENN PID file found.")
    return False


def install_remote_scripts() -> bool:
    """Run remote script installer."""
    inst_script = REPO_ROOT / "tooling" / "scripts" / "install_remote_script.py"
    if inst_script.is_file():
        res = subprocess.run([sys.executable, str(inst_script)], capture_output=True, text=True)
        print(res.stdout)
        return res.returncode == 0
    return False


def open_demo_als() -> bool:
    """Open Live 12 Demo set in Ableton Live."""
    als = REPO_ROOT / "assets" / "demo" / "KENN_Live12_Demo.als"
    if als.is_file():
        subprocess.run(["open", str(als)])
        return True
    return False


def sync_remote_gpu_notes() -> bool:
    """Run sync_gpu_notes.sh to download newly distilled notes and rebuild index."""
    sync_script = REPO_ROOT / "sync_gpu_notes.sh"
    if not sync_script.is_file():
        sync_script = REPO_ROOT / "tooling" / "scripts" / "sync_gpu1_notes.sh"
    if sync_script.is_file():
        print("[*] Running GPU note sync...")
        res = subprocess.run([str(sync_script)], cwd=str(REPO_ROOT), capture_output=True, text=True)
        print(res.stdout)
        if res.returncode == 0:
            notes_dir = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Notes"
            count = len(list(notes_dir.glob("*.md")))
            msg = f"Synced & rebuilt index: {count} notes active in KENN brain."
            print(f"[✓] {msg}")
            try:
                subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "KENN Knowledge Sync"'])
            except Exception:
                pass
            return True
        else:
            print(f"[!] Sync failed: {res.stderr}")
    return False


def run_mac_menu_app():
    """Launch macOS menu bar tray app using rumps."""
    try:
        import rumps
    except ImportError:
        print("Note: 'rumps' is not installed. Running in CLI companion mode.")
        run_cli_companion()
        return

    import threading

    class KENNCompanionApp(rumps.App):
        def __init__(self):
            super().__init__("🎛️ KENN", quit_button="Quit KENN Companion")
            self.status_item = rumps.MenuItem("Status: Checking...")
            self.menu = [
                self.status_item,
                None,  # Separator
                "Open KENN Web Hub",
                "Start KENN Server",
                "Stop KENN Server",
                None,
                "Sync Remote GPU Notes",
                None,
                "Open Live 12 Demo Project",
                "Install Live Remote Scripts",
            ]
            self.timer = rumps.Timer(self.refresh_status, 3)
            self.timer.start()
            self.refresh_status(None)

        def refresh_status(self, _):
            online = is_server_online()
            if online:
                self.title = "🎛️ KENN [Online]"
                self.status_item.title = f"🟢 Connected ({BASE_URL})"
            else:
                self.title = "🎛️ KENN [Offline]"
                self.status_item.title = "🔴 Server Offline"

        @rumps.clicked("Open KENN Web Hub")
        def open_hub(self, _):
            webbrowser.open(BASE_URL)

        @rumps.clicked("Start KENN Server")
        def start_server(self, _):
            start_server_process()
            self.refresh_status(None)

        @rumps.clicked("Stop KENN Server")
        def stop_server(self, _):
            stop_server_process()
            self.refresh_status(None)

        @rumps.clicked("Sync Remote GPU Notes")
        def sync_notes(self, _):
            threading.Thread(target=sync_remote_gpu_notes, daemon=True).start()

        @rumps.clicked("Open Live 12 Demo Project")
        def open_demo(self, _):
            open_demo_als()

        @rumps.clicked("Install Live Remote Scripts")
        def install_scripts(self, _):
            ok = install_remote_scripts()
            rumps.notification("KENN Live Bridge", "Installation", "Bridge scripts installed successfully" if ok else "Installation failed")

    app = KENNCompanionApp()
    app.run()


def run_cli_companion():
    """Run interactive CLI companion status loop."""
    print("=" * 60)
    print(" KENN Companion Manager (CLI Mode)")
    print(f" Base URL: {BASE_URL}")
    print("=" * 60)
    health = check_server_health()
    if health:
        print(f"[✓] Status: ONLINE | {health.get('service', 'KENN')}")
    else:
        print("[!] Status: OFFLINE")
    print("\nCommands:")
    print("  1) Start Server")
    print("  2) Stop Server")
    print("  3) Open Web Dashboard")
    print("  4) Open Live 12 Demo Project")
    print("  5) Install Remote Scripts")
    print("  6) Sync Remote GPU Notes")
    print("  q) Quit")


def main():
    parser = argparse.ArgumentParser(description="KENN Companion & Menu Bar Manager")
    parser.add_argument("--start", action="store_true", help="Start background server")
    parser.add_argument("--stop", action="store_true", help="Stop background server")
    parser.add_argument("--status", action="store_true", help="Check server status")
    parser.add_argument("--open", action="store_true", help="Open web dashboard in browser")
    parser.add_argument("--gui", action="store_true", help="Launch macOS menu bar app")
    parser.add_argument("--sync-notes", action="store_true", help="Sync GPU notes and rebuild index")
    args = parser.parse_args()

    if args.sync_notes:
        ok = sync_remote_gpu_notes()
        sys.exit(0 if ok else 1)
    elif args.status:
        health = check_server_health()
        if health:
            print(f"KENN Server: ONLINE ({BASE_URL})")
            print(json.dumps(health, indent=2))
            sys.exit(0)
        else:
            print(f"KENN Server: OFFLINE ({BASE_URL})")
            sys.exit(1)
    elif args.start:
        start_server_process()
    elif args.stop:
        stop_server_process()
    elif args.open:
        webbrowser.open(BASE_URL)
    elif args.gui or len(sys.argv) == 1:
        run_mac_menu_app()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
