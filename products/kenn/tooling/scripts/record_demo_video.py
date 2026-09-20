#!/usr/bin/env python3
"""Record a screen video demonstration of KENN Mix Assistant in Ableton Live 12.

Saves video to: artifacts/kenn_vst3_live12_demo.mp4
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VIDEO_OUTPUT = REPO_ROOT / "docs" / "kenn_vst3_live12_demo.mp4"
DESKTOP_COPY = Path.home() / "Desktop" / "kenn_vst3_live12_demo.mp4"

def is_screen_locked():
    try:
        import Quartz
        return bool(Quartz.CGSessionCopyCurrentDictionary().get("CGSSessionScreenIsLocked", False))
    except Exception:
        return False

def record_demo():
    print("Checking screen lock status...")
    if is_screen_locked():
        print("Screen is currently locked! Please unlock your Mac screen to capture live desktop pixels.")
        return False

    print("Activating Ableton Live 12...")
    subprocess.run(["osascript", "-e", 'tell application "Ableton Live 12 Suite" to activate'], stderr=subprocess.DEVNULL)
    subprocess.run(["osascript", "-e", 'tell application "System Events" to set frontmost of process "Live" to true'], stderr=subprocess.DEVNULL)
    time.sleep(1)

    # Launch screencapture in background for 14 seconds
    raw_mov = "/tmp/kenn_vst3_live12_raw.mov"
    if os.path.exists(raw_mov):
        try:
            os.remove(raw_mov)
        except OSError:
            pass

    print(f"Starting screen video recording -> {raw_mov} ...")
    cap_proc = subprocess.Popen(["screencapture", "-v", "-V", "22", "-C", "-k", "-m", raw_mov])

    time.sleep(2)

    # Run the live demo sequence
    print("Executing Live 12 + KENN VST3 plugin mutation sequence...")
    subprocess.run([sys.executable, str(REPO_ROOT / "tooling" / "scripts" / "demo_plugin_live.py")])

    cap_proc.wait()

    if os.path.exists(raw_mov) and os.path.getsize(raw_mov) > 0:
        print(f"Transcoding to web-compatible MP4 -> {VIDEO_OUTPUT} ...")
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
        subprocess.run([
            ffmpeg_bin, "-y",
            "-i", raw_mov,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            str(VIDEO_OUTPUT)
        ], check=True)
        print(f"✓ Video recording complete: {VIDEO_OUTPUT} ({VIDEO_OUTPUT.stat().st_size} bytes)")
        # Also copy to Desktop for easy access
        import shutil
        shutil.copy2(str(VIDEO_OUTPUT), str(DESKTOP_COPY))
        print(f"✓ Also copied to Desktop: {DESKTOP_COPY}")
        return True
    else:
        print("✗ No recording data was captured.")
        return False

if __name__ == "__main__":
    record_demo()
