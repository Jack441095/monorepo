#!/usr/bin/env python3
"""Master Autonomous Goal Runner: 5,000-Note Knowledge Harvester & Distiller.

Coordinates:
1. Background monitoring of GPU 1 distillation batches.
2. Auto-triggering indexing (build_index.py) at milestones.
3. Ingesting new web & transcript batches when current queues empty.
4. Continuous hands-free looping until milestone reached.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTES_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Notes"
INDEX_SCRIPT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "retrieval" / "build_index.py"
DISTILL_SCRIPT = REPO_ROOT / "tooling" / "scripts" / "batch_distill_5k_gpu1.py"
PROGRESS_FILE = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Sources" / ".batch_distillation_progress.json"


def get_current_note_count() -> int:
    return len(list(NOTES_DIR.glob("*.md")))


def run_indexing() -> None:
    print("\n" + "=" * 70)
    print("   REBUILDING VECTOR & BM25 INDEX...")
    print("=" * 70)
    cmd = [sys.executable, str(INDEX_SCRIPT)]
    try:
        subprocess.run(cmd, cwd=str(REPO_ROOT / "apps" / "backend" / "src"), check=True)
        print("[+] Index rebuilt successfully.")
    except Exception as e:
        print(f"[!] Index rebuild error: {e}")


def run_distillation_batch(batch_size: int = 100) -> int:
    print(f"\n[*] Launching GPU 1 Distillation Batch (max {batch_size} notes)...")
    cmd = [sys.executable, str(DISTILL_SCRIPT), "--max", str(batch_size)]
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return proc.returncode
    except Exception as e:
        print(f"[!] Distillation batch error: {e}")
        return 1


def main():
    target = 5000
    print("=" * 75)
    print("   AUTONOMOUS 5,000-NOTE GOAL RUNNER ACTIVE")
    print(f"   Target: {target} notes | Current: {get_current_note_count()} notes")
    print("=" * 75)

    last_indexed_count = get_current_note_count()

    while True:
        current_count = get_current_note_count()
        print(f"\n[Status Check] Current Notes: {current_count}/{target}")


        if current_count >= target:
            print("[+] GOAL ACHIEVED! 5,000 Notes Milestone Reached.")
            run_indexing()
            break

        # If we added 25+ notes since last index, update index
        if current_count - last_indexed_count >= 25:
            run_indexing()
            last_indexed_count = current_count

        # Run next distillation batch on GPU 1
        ret = run_distillation_batch(batch_size=50)


        # Brief breather
        time.sleep(5)


if __name__ == "__main__":
    main()
