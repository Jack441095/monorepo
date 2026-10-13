#!/usr/bin/env python3
"""Record the operator's web UI/Live walkthrough without sending DAW commands."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess


MAX_SECONDS = 300  # The complete investor showcase must fit in five minutes.


def check_output_directory(directory: Path) -> None:
    """Refuse existing takes and any destination inside a Git checkout."""
    if directory.exists():
        raise ValueError("Use a new output directory so earlier attempts remain intact")
    parent = directory.parent
    while not parent.exists():
        parent = parent.parent
    # Check the destination, not this script's checkout: captures can contain
    # private sessions and must stay outside every repository, including worktrees.
    result = subprocess.run(
        ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        raise ValueError("Record outside Git; raw video and audio are local evidence")


def media_info(path: Path, ffprobe: str) -> dict:
    """Read only the duration and stream properties needed for media checks."""
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name,width,height,channels",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout)
    duration = float(info.get("format", {}).get("duration", "nan"))
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise ValueError("Recording duration must be measurable and at most 300 s")
    streams = info.get("streams", [])
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video) != 1 or not video[0].get("width") or not video[0].get("height"):
        raise ValueError("Recording must contain one readable video stream")
    if not audio:
        # A silent screen movie cannot demonstrate an audible Apply/Undo A/B.
        raise ValueError("Recording has no audio stream; check capture audio first")
    return {"seconds": duration, "video": video[0], "audio": audio}


def convert_take(raw: Path, output: Path, ffmpeg: str, ffprobe: str) -> dict:
    """Encode a full take with aligned playback audio; leave raw tracks intact."""
    before = media_info(raw, ffprobe)
    audio_count = len(before["audio"])
    audio_args = ["-map", "0:a:0"]
    if audio_count > 1:
        # Players usually select one audio track, so separate music and mic
        # tracks must share a normalized mix. Keep the longest source's tail;
        # normalization prevents overlapping full-scale sources from clipping.
        # amix starts consuming every input together. Pad each source to its
        # timestamps first so a mic starting late stays aligned with the video.
        timing_filters = ";".join(
            f"[0:a:{index}]aresample=async=1:first_pts=0[aligned{index}]"
            for index in range(audio_count)
        )
        inputs = "".join(f"[aligned{index}]" for index in range(audio_count))
        audio_args = [
            "-filter_complex",
            f"{timing_filters};{inputs}amix=inputs={audio_count}:duration=longest:normalize=1[playback]",
            "-map", "[playback]",
        ]
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-n", "-i", str(raw),
         "-map", "0:v:0", *audio_args, "-c:v", "libx264",
         "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
         # H.264 requires even dimensions; lose at most one edge pixel rather
         # than resize the UI text or crop out a failed action.
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)],
        capture_output=True, text=True, check=True,
    )
    after = media_info(output, ffprobe)
    # MOV/MP4 timestamps and AAC padding can differ by less than 250 ms.
    # Reject anything larger instead of quietly shipping a shortened take.
    if abs(before["seconds"] - after["seconds"]) > 0.25:
        raise ValueError("Encoded video duration differs from the original take")
    if len(after["audio"]) != 1:
        # A player must hear every captured source without choosing tracks.
        raise ValueError("Encoded video must contain one playback audio track")
    return {
        "raw": before,
        "mp4": after,
        "audio_playback": "normalized_mix_all_sources" if audio_count > 1 else "single_source",
        "audio_timing": "pad_each_source_to_video_clock" if audio_count > 1 else "retain_source_start",
    }


def capture_command(raw: Path, seconds: int, microphone: bool) -> list[str]:
    """Request main-display video and system audio; optionally request the mic."""
    command = ["screencapture", "-v", "-V", str(seconds), "-m", "-C", "-k", "-A"]
    if microphone:
        # These flags request both sources; the supervised ten-second sound
        # check must prove Live playback and narration on this Mac's routing.
        command.append("-g")
    return [*command, str(raw)]


def _sha256(path: Path) -> str:
    """Hash a closed capture without leaving file handles open during playback."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record_take(directory: Path, seconds: int, microphone: bool) -> Path:
    """Keep a raw take and media receipt; playback and Live qualification stay manual."""
    if not 1 <= seconds <= MAX_SECONDS:
        raise ValueError("Capture length must be between 1 and 300 s")
    check_output_directory(directory)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe or not shutil.which("screencapture"):
        raise RuntimeError("screencapture, ffmpeg and ffprobe must already be installed")
    directory.mkdir(parents=True)
    raw, output = directory / "raw.mov", directory / "showcase.mp4"
    receipt_path = directory / "capture.json"
    receipt = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "requested_seconds": seconds,
        "system_audio_requested": True,
        "microphone_requested": microphone,
        "status": "capturing",
        "human_checks_pending": [
            "complete browser sequence", "readable cards and Live values",
            "audible Live before/after", "intelligible narration", "exact reset restoration",
        ],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Recording for {seconds} s. Perform all commands and confirmations in the web UI.", flush=True)
    try:
        subprocess.run(capture_command(raw, seconds, microphone), check=True)
        receipt["media"] = convert_take(raw, output, ffmpeg, ffprobe)
        receipt["sha256"] = {path.name: _sha256(path) for path in (raw, output)}
        # Valid media proves neither successful Live control nor audible sound;
        # only supervised playback and the rehearsal log can qualify this take.
        receipt["status"] = "media_valid_unreviewed"
    except (OSError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt):
        # Preserve the failed take and make its state explicit for bug finding.
        receipt["status"] = "capture_failed"
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True, help="new directory outside Git")
    parser.add_argument("--seconds", type=int, default=285, help="capture length in seconds (1–300)")
    parser.add_argument("--microphone", action="store_true", help="also request default microphone input")
    args = parser.parse_args(argv)
    try:
        output = record_take(args.out_dir.expanduser().resolve(), args.seconds, args.microphone)
    except KeyboardInterrupt:
        # An interrupted dry run remains evidence, never a successful demo.
        print("Capture interrupted; inspect the preserved raw take and capture.json.")
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        # Report failure without promoting a partial or silent movie to success.
        print(f"Capture failed: {exc}. Preserve this attempt and check capture.json.")
        return 1
    print(f"Saved {output}. Playback and supervised Live checks are still pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
