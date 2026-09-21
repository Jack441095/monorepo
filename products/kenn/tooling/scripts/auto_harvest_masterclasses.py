#!/usr/bin/env python3
"""Autonomous Background Masterclass Transcript Harvester.

Runs continuously in the background:
- Monitors pending YouTube masterclass videos.
- Attempts fetches with randomized delays and respectful pacing.
- Handles YouTube 429 IP cooldowns with backoff (sleeps 5m on block).
- On each downloaded transcript, automatically rsyncs to the remote GPU queue:
  ubuntu@www.haoee.com:/mnt/data/kenn-notes-gpu1/transcripts/
"""

from __future__ import annotations

import random
import subprocess
import time
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Transcripts"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = REPO_ROOT / "auto_harvest.log"

import sys
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tooling"))

from scripts.fetch_all_masterclasses import CATALOGUE, fetch_via_ytdlp
try:
    from scripts.fetch_all_masterclasses import CATALOGUE, fetch_via_ytdlp
except ImportError:
    from tooling.scripts.fetch_all_masterclasses import CATALOGUE, fetch_via_ytdlp


def log(msg: str) -> None:
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{timestamp} {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def rsync_to_gpu() -> None:
    try:
        askpass_script = Path("/tmp/kenn_askpass.sh")
        if not askpass_script.exists():
            askpass_script.write_text("#!/bin/sh\necho 'srd123456.'\n", encoding="utf-8")
            askpass_script.chmod(0o755)

        import os
        env = os.environ.copy()
        env["SSH_ASKPASS"] = str(askpass_script)
        env["SSH_ASKPASS_REQUIRE"] = "force"

        cmd = [
            "rsync", "-avz", "-e", "ssh -p 2022 -o StrictHostKeyChecking=no",
            str(OUT_DIR) + "/",
            "ubuntu@www.haoee.com:/mnt/data/kenn-notes-gpu1/transcripts/"
        ]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            log("Synced newly harvested transcripts to GPU 1.")
        else:
            log(f"Rsync warning: {res.stderr.strip()[:200]}")
    except Exception as exc:
        log(f"Rsync error: {exc}")


def run_daemon() -> None:
    log("=" * 70)
    log("KENN Autonomous Masterclass Harvester Daemon Started")
    log(f"Target Directory: {OUT_DIR}")
    log(f"Total Masterclasses in Catalogue: {len(CATALOGUE)}")
    log("=" * 70)

    api = YouTubeTranscriptApi()

    while True:
        # Determine pending
        pending = []
        for artist, prefix, vid, title in CATALOGUE:
            matching = list(OUT_DIR.glob(f"*{vid}*"))
            if not matching or matching[0].stat().st_size < 500:
                pending.append((artist, prefix, vid, title))

        if not pending:
            log("All catalogue masterclasses are harvested! Daemon will sleep 1 hour.")
            time.sleep(3600)
            continue

        log(f"Pending videos to harvest: {len(pending)}")
        cooldown_needed = False

        for artist, prefix, vid, title in pending:
            out_file = OUT_DIR / f"{prefix}-{vid}.txt"
            log(f"Attempting: [{artist}] {title} ({vid})...")


            transcript_text = None
            try:
                ts = api.fetch(vid)
                transcript_text = " ".join([s.text for s in ts]).replace("\n", " ")
                transcript_text = " ".join([s.text if hasattr(s, "text") else s.get("text", "") for s in ts]).replace("\n", " ")
            except Exception as err:
                err_str = str(err)
                if "blocking requests" in err_str or "429" in err_str:
                    log("  -> Direct API IP cooldown active. Trying yt-dlp...")
                    transcript_text = fetch_via_ytdlp(vid)
                    if not transcript_text:
                        log("  -> Both engines blocked by YouTube cooldown.")
                        cooldown_needed = True
                        break
                else:
                    log(f"  -> No captions or error: {err}")

            if transcript_text and len(transcript_text) > 300:
                header = (
                    f"Artist: {artist}\n"
                    f"Title: {title}\n"
                    f"Video ID: {vid}\n"
                    f"Source: YouTube Verbatim Masterclass\n"
                    f"{'=' * 60}\n\n"
                )
                out_file.write_text(header + transcript_text, encoding="utf-8")
                log(f"  -> SUCCESS: {len(transcript_text)} chars saved to {out_file.name}")
                rsync_to_gpu()

            delay = random.uniform(4.0, 8.0)
            time.sleep(delay)

        if cooldown_needed:
            sleep_duration = 300  # 5 minutes
            log(f"YouTube rate-limit cooldown active. Sleeping {sleep_duration // 60} minutes before retrying...")
            time.sleep(sleep_duration)
        else:
            time.sleep(30)


if __name__ == "__main__":
    run_daemon()
