#!/usr/bin/env python3
"""Execute an automated live walkthrough of KENN and record a qualified investor demo take."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

try:
    import Quartz
except ImportError:
    Quartz = None


# The investor showcase must fit strictly within 210 seconds (3.5 minutes).
TARGET_SECONDS = 195
MAX_SECONDS = 210

# Live 12 transport button coordinates in points (measured from session window).
LIVE_PLAY_BUTTON = (645.0, 73.0)
LIVE_STOP_BUTTON = (670.0, 73.0)

# Safari chat input field coordinates in points.
CHAT_INPUT_CENTER = (1515.0, 1084.0)

# Target output location at repository root requested by user.
REPO_ROOT_MP4 = Path("/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/kenn_investor_demo.mp4")


def _check_preconditions(directory: Path) -> None:
    """Refuse git-tracked destinations and existing directories before recording."""
    if directory.exists():
        raise ValueError(f"Destination {directory} already exists. Choose a clean take path.")
    parent = directory.parent
    while not parent.exists():
        parent = parent.parent
    result = subprocess.run(
        ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        raise ValueError("Record outside Git; raw media contains personal session evidence.")
    if Quartz is None:
        raise RuntimeError("Quartz framework required for automated cursor moves and clicks.")


def smooth_move(from_pos: tuple[float, float], to_pos: tuple[float, float], steps: int = 16, duration: float = 0.28) -> None:
    """Interpolate mouse movements smoothly so cursors in the video look natural and human."""
    x0, y0 = from_pos
    x1, y1 = to_pos
    for i in range(1, steps + 1):
        t = i / steps
        # Smoothstep curve gives realistic acceleration and gentle deceleration.
        s = t * t * (3.0 - 2.0 * t)
        curr_x = x0 + (x1 - x0) * s
        curr_y = y0 + (y1 - y0) * s
        pt = Quartz.CGPointMake(curr_x, curr_y)
        move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
        time.sleep(duration / steps)


def click_at(pos: tuple[float, float]) -> None:
    """Post left-mouse down and up events at the given screen coordinates in points."""
    pt = Quartz.CGPointMake(pos[0], pos[1])
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.08)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    time.sleep(0.12)


def move_and_click(from_pos: tuple[float, float], to_pos: tuple[float, float]) -> tuple[float, float]:
    """Move the cursor smoothly to a target and trigger a click, returning the new position."""
    smooth_move(from_pos, to_pos)
    click_at(to_pos)
    return to_pos


def start_live_playback(current_pos: tuple[float, float]) -> tuple[float, float]:
    """Move to Live's play button, click, and trigger OSC playback."""
    new_pos = move_and_click(current_pos, LIVE_PLAY_BUTTON)
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"/live/song/continue_playing\x00,\x00\x00\x00", ("127.0.0.1", 11000))
    except Exception:
        pass
    return new_pos


def stop_live_playback(current_pos: tuple[float, float]) -> tuple[float, float]:
    """Move to Live's stop button, click, and trigger OSC stop."""
    new_pos = move_and_click(current_pos, LIVE_STOP_BUTTON)
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"/live/song/stop_playing\x00\x00,\x00\x00\x00", ("127.0.0.1", 11000))
    except Exception:
        pass
    return new_pos


def focus_chat_input(current_pos: tuple[float, float]) -> tuple[float, float]:
    """Focus Safari and click the KENN chat input field."""
    subprocess.run(["osascript", "-e", 'tell application "Safari" to activate'], check=True)
    time.sleep(0.15)
    return move_and_click(current_pos, CHAT_INPUT_CENTER)


def type_chat_message(message: str, current_pos: tuple[float, float]) -> tuple[float, float]:
    """Focus the chat box, type the query, and submit via the Return key."""
    current_pos = focus_chat_input(current_pos)
    # Keystroke typing through AppleScript System Events simulates user typing.
    escaped = message.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run([
        "osascript", "-e",
        f'tell application "System Events" to keystroke "{escaped}"'
    ], check=True)
    time.sleep(0.25)
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to key code 36'
    ], check=True)
    return current_pos


def find_latest_chat_button(name: str) -> tuple[float, float, float, float] | None:
    """Locate the center and dimensions of an action button in Safari's chat history."""
    script = f'''
tell application "Safari" to activate
delay 0.1
tell application "System Events"
    tell process "Safari"
        tell window 1
            set ch to group "AI Chat History" of group "KENN Chat Area" of group "KENN Sidebar" of group 1 of UI element 1 of scroll area 1 of group 1 of group 1 of tab group 1 of splitter group 1
            set allGroups to every UI element of ch
            repeat with g in reverse of allGroups
                try
                    set bList to every button of g
                    repeat with b in bList
                        if (name of b as string) contains "{name}" or (description of b as string) contains "{name}" then
                            set bp to position of b
                            set bs to size of b
                            return (item 1 of bp as string) & "," & (item 2 of bp as string) & "," & (item 1 of bs as string) & "," & (item 2 of bs as string)
                        end if
                    end repeat
                end try
                try
                    set subGroups to every group of g
                    repeat with sg in subGroups
                        try
                            set subButtons to every button of sg
                            repeat with sb in subButtons
                                if (name of sb as string) contains "{name}" or (description of sb as string) contains "{name}" then
                                    set bp to position of sb
                                    set bs to size of sb
                                    return (item 1 of bp as string) & "," & (item 2 of bp as string) & "," & (item 1 of bs as string) & "," & (item 2 of bs as string)
                                end if
                            end repeat
                        end try
                    end repeat
                end try
            end repeat
        end tell
    end tell
end tell
return ""
'''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    out = res.stdout.strip()
    if out and "," in out:
        parts = [float(p.strip()) for p in out.split(",")]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    return None


def click_chat_card_button(button_name: str, current_pos: tuple[float, float], timeout_seconds: float = 12.0) -> tuple[float, float]:
    """Wait for a proposal or undo button to appear, smoothly move to it, and click."""
    t0 = time.time()
    while time.time() - t0 < timeout_seconds:
        found = find_latest_chat_button(button_name)
        if found:
            bx, by, bw, bh = found
            target = (bx + bw / 2.0, by + bh / 2.0)
            subprocess.run(["osascript", "-e", 'tell application "Safari" to activate'], check=True)
            time.sleep(0.1)
            return move_and_click(current_pos, target)
        time.sleep(0.4)
    raise TimeoutError(f"Button '{button_name}' did not appear in Safari chat within {timeout_seconds} s")


def click_quick_chip(chip_name: str, current_pos: tuple[float, float]) -> tuple[float, float]:
    """Click a quick-action chip located in the KENN sidebar below the chat history."""
    script = f'''
tell application "Safari" to activate
delay 0.1
tell application "System Events"
    tell process "Safari"
        tell window 1
            set btn to button "{chip_name}" of group "KENN Sidebar" of group 1 of UI element 1 of scroll area 1 of group 1 of group 1 of tab group 1 of splitter group 1
            set btnPos to position of btn
            set btnSize to size of btn
            return (item 1 of btnPos as string) & "," & (item 2 of btnPos as string) & "," & (item 1 of btnSize as string) & "," & (item 2 of btnSize as string)
        end tell
    end tell
end tell
'''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    out = res.stdout.strip()
    if out and "," in out:
        parts = [float(p.strip()) for p in out.split(",")]
        target = (parts[0] + parts[2] / 2.0, parts[1] + parts[3] / 2.0)
        subprocess.run(["osascript", "-e", 'tell application "Safari" to activate'], check=True)
        time.sleep(0.1)
        return move_and_click(current_pos, target)
    raise RuntimeError(f"Quick chip '{chip_name}' was not found in KENN sidebar")


def run_showcase(output_dir: Path, total_seconds: int = TARGET_SECONDS, use_mic: bool = True) -> int:
    """Orchestrate the 195-second live walkthrough while recording screen and audio."""
    if total_seconds > MAX_SECONDS:
        raise ValueError(f"Total recording time {total_seconds} s exceeds limit of {MAX_SECONDS} s (3.5 minutes)")

    _check_preconditions(output_dir)

    recorder_script = Path(__file__).parent / "record_demo_live.py"
    if not recorder_script.exists():
        raise FileNotFoundError(f"Missing recorder script at {recorder_script}")

    # Launch record_demo_live.py in the background to capture high-res Retina video and audio.
    record_cmd = [sys.executable, str(recorder_script), "--out-dir", str(output_dir), "--seconds", str(total_seconds)]
    if use_mic:
        record_cmd.append("--microphone")

    # Ensure Live and Safari are the active front windows covering the display.
    subprocess.run([
        "osascript", "-e",
        'tell application "Live" to activate\ndelay 0.3\ntell application "Safari" to activate'
    ], check=True)
    time.sleep(0.5)

    print(f"Launching recorder: {' '.join(record_cmd)}", flush=True)
    recorder_proc = subprocess.Popen(record_cmd)

    # Allow screencapture 4 seconds to initialize hardware devices, audio taps, and window hooks.
    time.sleep(4.0)

    pos = (1200.0, 600.0)

    try:
        # Act 1: Simple Question 1 - Track Count
        print("[00:04] Act 1: Track Count Introspection", flush=True)
        pos = type_chat_message("How many tracks are in this session?", pos)
        time.sleep(8.0)

        # Act 2: Simple Question 2 - Session Tempo and Key
        print("[00:14] Act 2: Tempo and Key Check", flush=True)
        pos = type_chat_message("What is the project tempo and key?", pos)
        time.sleep(8.0)

        # Act 3: Live Track Control - Track 12 Renaming with Confirmation & Readback
        print("[00:24] Act 3: Live Track Renaming & Proposal Execution", flush=True)
        pos = type_chat_message("rename track 12 to Ambient Pads", pos)
        time.sleep(6.0)
        pos = click_chat_card_button("Apply to Live 12", pos)
        time.sleep(6.0)
        pos = click_chat_card_button("Undo", pos)
        time.sleep(6.0)

        # Act 4: Advanced Live Control - Auditory Playback & Volume A/B
        print("[00:42] Act 4: Start Live Playback & Propose Fader Adjustment", flush=True)
        pos = start_live_playback(pos)
        time.sleep(6.0)  # Hear unadjusted track playback and observe bouncing meters.

        pos = type_chat_message("Set BASS volume to -3 dB.", pos)
        time.sleep(5.0)  # Observe safety proposal card with before/after levels.

        print("[00:53] Act 4b: Apply Proposal to Live 12", flush=True)
        pos = click_chat_card_button("Apply to Live 12", pos)
        time.sleep(10.0)  # Hear boosted bass level (+7 dB) and observe Live 12 Synced confirmation.

        print("[01:03] Act 4c: Exact Non-Destructive Undo Restoration", flush=True)
        pos = click_chat_card_button("Undo", pos)
        time.sleep(8.0)  # Hear volume return to original -10 dB balance and observe restored card state.

        # Stop playback to transition cleanly to engineering queries.
        pos = stop_live_playback(pos)
        time.sleep(3.0)

        # Act 5: Advanced Engineering Query 1 - Low End Masking & Sidechaining
        print("[01:14] Act 5: Low-End Separation around 80 Hz", flush=True)
        pos = type_chat_message("How should I carve space between the Kick and Bass around 80 Hz?", pos)
        time.sleep(20.0)

        # Act 6: Advanced Engineering Query 2 - Linear-Phase vs Minimum-Phase EQ
        print("[01:34] Act 6: Linear-Phase vs Minimum-Phase EQ & Pre-Ringing", flush=True)
        pos = type_chat_message("When should I use a linear-phase EQ instead of a minimum-phase one?", pos)
        time.sleep(18.0)

        # Act 7: Advanced Engineering Query 3 - Saturation Aliasing & Oversampling
        print("[01:52] Act 7: Saturation Aliasing & Nyquist Oversampling", flush=True)
        pos = type_chat_message("Why do saturators alias, and how does oversampling help?", pos)
        time.sleep(18.0)

        # Act 8: Safety Boundary - Destructive Deletion Refusal
        print("[02:10] Act 8: Destructive Safety Guardrails Check", flush=True)
        pos = type_chat_message("Delete track 1.", pos)
        time.sleep(14.0)  # Proves KENN safely refuses destructive deletion requests.

        # Act 9: Quick Action Chip & Musical Outro
        print("[02:38] Act 9: Quick Chip Inspection & Musical Outro", flush=True)
        pos = click_quick_chip("◉ Session count", pos)
        time.sleep(6.0)

        # Final music playback outro to conclude the presentation with audio groove.
        pos = start_live_playback(pos)
        time.sleep(16.0)  # Outro music playback pass.
        pos = stop_live_playback(pos)

        print("[03:02] Walkthrough actions complete. Awaiting recording wrap-up and video transcoding...", flush=True)

    except Exception as err:
        print(f"Error during showcase execution: {err}", file=sys.stderr)
        try:
            stop_live_playback(LIVE_STOP_BUTTON)
        except Exception:
            pass
        raise

    # Wait for record_demo_live.py to reach completion (screencapture exit + ffmpeg transcode).
    returncode = recorder_proc.wait()
    if returncode != 0:
        raise RuntimeError(f"Recorder exited with error code {returncode}")

    showcase_mp4 = output_dir / "showcase.mp4"
    if not showcase_mp4.exists():
        raise FileNotFoundError(f"Expected encoded video not found at {showcase_mp4}")

    # Copy the finished mp4 to repo root as requested by user.
    print(f"Copying {showcase_mp4} to repository root at {REPO_ROOT_MP4}...", flush=True)
    shutil.copy2(showcase_mp4, REPO_ROOT_MP4)

    # Inspect media properties with ffprobe to verify video and audio streams.
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        probe_res = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,channels",
             "-of", "json", str(REPO_ROOT_MP4)],
            capture_output=True, text=True, check=True,
        )
        info = json.loads(probe_res.stdout)
        duration = float(info.get("format", {}).get("duration", 0.0))
        streams = info.get("streams", [])
        print(f"Verified {REPO_ROOT_MP4.name}: duration={duration:.2f} s ({duration/60:.2f} min), streams={len(streams)}", flush=True)

    print(f"Investor demo take successfully saved to {REPO_ROOT_MP4}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True, help="new destination directory outside Git")
    parser.add_argument("--seconds", type=int, default=TARGET_SECONDS, help="recording duration in seconds (1-210)")
    parser.add_argument("--microphone", action="store_true", default=True, help="include microphone narration")
    args = parser.parse_args(argv)

    try:
        return run_showcase(args.out_dir.expanduser().resolve(), args.seconds, args.microphone)
    except KeyboardInterrupt:
        print("\nDemo execution interrupted by user.")
        return 130
    except Exception as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
