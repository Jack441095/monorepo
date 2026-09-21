#!/usr/bin/env python3
"""Record a demonstration video of KENN UI & Ableton Live 12 integration."""

import json
import os
import subprocess
import time
import urllib.request

from pathlib import Path

REPO_ROOT = str(Path(__file__).resolve().parents[2])
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
RAW_MOV = "/tmp/kenn_demo_raw.mov"
OUTPUT_MP4 = os.path.join(DOCS_DIR, "demo_kenn_live.mp4")
OUTPUT_GIF = os.path.join(DOCS_DIR, "demo_kenn_live.gif")

os.makedirs(DOCS_DIR, exist_ok=True)

def arrange_windows():
    applescript = '''
    tell application "System Events"
        tell process "Live"
            set frontmost to true
            set position of window 1 to {855, 25}
            set size of window 1 to {855, 1075}
        end tell
        tell process "Safari"
            set frontmost to true
            set position of window 1 to {0, 25}
            set size of window 1 to {855, 1075}
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", applescript], check=True)
    time.sleep(1)

def live_command(cmd_text: str):
    print(f"[DEMO] Executing live DAW command: '{cmd_text}'...")
    req = urllib.request.Request(
        "http://127.0.0.1:8090/api/ableton/command",
        data=json.dumps({"command": cmd_text, "session_id": "demo-video"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))


    prop = res.get("proposal")
    if not prop:
        print(f"[DEMO] No proposal for '{cmd_text}': {res}")
        return res


    token = prop.get("confirmation_token")
    confirm_req = urllib.request.Request(
        "http://127.0.0.1:8090/api/ableton/command",
        data=json.dumps({
            "command": cmd_text,
            "session_id": "demo-video",
            "proposal": prop,
            "confirm_token": token
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(confirm_req) as resp:
        confirm_res = json.loads(resp.read().decode("utf-8"))
    print(f"[DEMO] Result for '{cmd_text}': {confirm_res.get('status')} - {confirm_res.get('answer')}")
    return confirm_res

def main():
    print("[DEMO] Arranging Safari (KENN UI) and Ableton Live 12...")
    arrange_windows()

    duration = 16
    print(f"[DEMO] Starting screen capture for {duration} seconds to {RAW_MOV}...")
    if os.path.exists(RAW_MOV):
        os.remove(RAW_MOV)

    cap_proc = subprocess.Popen([
        "screencapture",
        "-v",
        f"-V{duration}",
        RAW_MOV
    ])

    try:
        # Give 2 seconds of clean initial state
        time.sleep(2.5)

        # 1. Mute track 1 in Live
        live_command("mute track 1")
        time.sleep(3.0)

        # 2. Unmute track 1 in Live
        live_command("unmute track 1")
        time.sleep(2.5)

        # 3. Solo track 1 in Live
        live_command("solo track 1")
        time.sleep(2.5)

        # 4. Unsolo track 1 in Live
        live_command("unsolo track 1")

        print("[DEMO] Waiting for screen capture to finalize...")
        cap_proc.wait(timeout=10)
    except Exception as e:
        print(f"[DEMO] Exception during recording: {e}")
        cap_proc.kill()
        raise

    print(f"[DEMO] Raw capture saved. Size: {os.path.getsize(RAW_MOV)} bytes.")

    # Convert to MP4
    print(f"[DEMO] Transcoding to web-optimized MP4 at {OUTPUT_MP4}...")
    ffmpeg_cmd = [
        "/usr/local/bin/ffmpeg",
        "-y",
        "-i", RAW_MOV,
        "-vf", "scale=1920:-2:flags=lanczos",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        OUTPUT_MP4
    ]
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"[DEMO] MP4 successfully generated: {OUTPUT_MP4} ({os.path.getsize(OUTPUT_MP4)} bytes)")

    # Convert to GIF
    print(f"[DEMO] Generating preview GIF at {OUTPUT_GIF}...")
    gif_cmd = [
        "/usr/local/bin/ffmpeg",
        "-y",
        "-i", OUTPUT_MP4,
        "-vf", "fps=10,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        OUTPUT_GIF
    ]
    subprocess.run(gif_cmd, check=True)
    print(f"[DEMO] GIF successfully generated: {OUTPUT_GIF} ({os.path.getsize(OUTPUT_GIF)} bytes)")
    print("[DEMO] Demo capture complete!")

if __name__ == "__main__":
    main()
