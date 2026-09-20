"""DiskSweep CLI: table Path|Size|LastUsed|Category|Safety|Why + DryRun/Trash/Undo.

Usage:
  python -m sidecar.cli --scan build/scan.jsonl [--no-llm] [--json out.json]
  python -m sidecar.cli --scan build/scan.jsonl --trash [--include-review]
  python -m sidecar.cli --undo --log ~/.Trash/Disksweep/<stamp>/undo.json
  python -m sidecar.cli doctor
Default is dry-run: never deletes unless --trash is passed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sidecar.classifier import (  # noqa: E402
    classify,
    get_enrichment_status,
    leaf_totals,
)
from sidecar.ollama_client import OLLAMA_URL, ollama_available  # noqa: E402


def load_scan(path: str) -> list[dict]:
    items = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def fmt_gb(n: int) -> str:
    return f"{n / 1e9:.2f}G"


def print_table(verdicts: list[dict], items_by_path: dict) -> None:
    print(
        f"{'Path':60.60s} | {'Size':>7s} | {'Used':10.10s} | {'Cat':9.9s} | {'Safety':7s} | Why"
    )
    print("-" * 140)
    for v in sorted(verdicts, key=lambda x: -x["size_bytes"]):
        it = items_by_path.get(v["path"], {})
        print(
            f"{v['path'][:60]:60s} | {fmt_gb(v['size_bytes']):>7s} | "
            f"{str(it.get('mtime', ''))[:10]:10s} | {str(it.get('category', ''))[:9]:9s} | "
            f"{v['safety']:7s} | {v['reason'][:60]}"
        )


def rotate_trash_logs(keep: int = 10) -> None:
    """Keep only the newest `keep` Trash/Disksweep runs (undo logs + payloads)."""
    base = os.path.expanduser("~/.Trash/Disksweep")
    if not os.path.isdir(base):
        return
    runs = sorted(
        (
            os.path.join(base, d)
            for d in os.listdir(base)
            if os.path.isdir(os.path.join(base, d))
        )
    )
    for old in runs[:-keep] if len(runs) > keep else []:
        shutil.rmtree(old, ignore_errors=True)


def cmd_trash(verdicts: list[dict], include_review: bool) -> str:
    """Trash-first delete with undo log. Returns log path."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    trash_dir = os.path.expanduser(f"~/.Trash/Disksweep/{stamp}")
    os.makedirs(trash_dir, exist_ok=True)
    log = []
    for v in verdicts:
        if v["safety"] == "BLOCKED":
            continue
        if v["safety"] == "REVIEW" and not include_review:
            continue
        src = v["path"]
        if not os.path.exists(src):
            continue
        dst = os.path.join(trash_dir, os.path.basename(src).replace("/", "_"))
        try:
            shutil.move(src, dst)
            log.append({"src": src, "dst": dst})
        except Exception as e:
            print(f"SKIP {src}: {e}", file=sys.stderr)
    log_path = os.path.join(trash_dir, "undo.json")
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)
    rotate_trash_logs()
    try:  # keep Time-Machine-visible frees honest
        subprocess.run(
            ["tmutil", "thinlocalsnapshots", "/", "2000000000", "4"],
            capture_output=True,
            timeout=120,
        )
    except Exception:
        pass
    return log_path


def cmd_undo(log_path: str) -> None:
    try:
        with open(os.path.expanduser(log_path)) as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Cannot undo: unreadable log {log_path}: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(entries, list):
        print(
            f"Cannot undo: corrupt log (expected a list): {log_path}", file=sys.stderr
        )
        sys.exit(2)
    base = os.path.dirname(os.path.expanduser(log_path))
    if os.path.basename(log_path) != "undo.json":
        entries = [{"src": e["dst"], "dst": e["src"]} for e in entries]
        for e in entries:
            if os.path.exists(e["src"]):
                os.makedirs(os.path.dirname(e["dst"]), exist_ok=True)
                shutil.move(e["src"], e["dst"])
        return
    restored = 0
    for e in entries:
        if not isinstance(e, dict) or "src" not in e or "dst" not in e:
            print(f"SKIP corrupt entry: {e!r:.80s}", file=sys.stderr)
            continue
        if os.path.exists(e["dst"]):
            os.makedirs(os.path.dirname(e["src"]), exist_ok=True)
            shutil.move(e["dst"], e["src"])
            restored += 1
    print(f"Restored {restored}/{len(entries)} items from {base}")


def cmd_doctor() -> None:
    print("DiskSweep doctor")
    print(
        f"Ollama: {'reachable' if ollama_available() else 'UNREACHABLE (rules-only mode)'} [{OLLAMA_URL}]"
    )
    try:
        out = subprocess.run(
            ["df", "-h", "/System/Volumes/Data"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        print(out.stdout.strip() or "(df unavailable)")
    except Exception as e:
        print(f"(df failed: {e})")
    tcc = os.path.expanduser("~/Library/Application Support/com.apple.TCC/TCC.db")
    print(
        f"Full Disk Access: {'likely ON (TCC.db readable)' if os.access(tcc, os.R_OK) else 'UNKNOWN/OFF (grant in Settings > Privacy > Full Disk Access)'}"
    )
    print(
        "Blocklist: /System /bin /sbin /usr(except /usr/local caches) /private/var/vm *.kext Backups.backupdb"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default="build/scan.jsonl")
    ap.add_argument("--trash", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--log", default="")
    ap.add_argument("--include-review", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument(
        "--json", default="", help="write verdicts JSON (verdict.schema.json) to PATH"
    )
    a = ap.parse_args()
    if a.undo:
        if not a.log:
            ap.error("--undo requires --log")
        cmd_undo(a.log)
        return
    items = load_scan(a.scan)
    verdicts = classify(items, use_llm=not a.no_llm)
    items_by_path = {i["path"]: i for i in items}
    print_table(verdicts, items_by_path)
    totals = leaf_totals(verdicts, items_by_path)
    print(
        f"\nSAFE reclaimable (deduped): {fmt_gb(totals['SAFE'])} | REVIEW (needs checkbox): {fmt_gb(totals['REVIEW'])}"
    )
    if get_enrichment_status()["rules_only"] and not a.no_llm:
        print(
            "NOTE: rules-only mode — Ollama unreachable or budget exhausted, reasons lack llm: notes."
        )
    if a.json:
        with open(a.json, "w") as f:
            json.dump(verdicts, f, indent=2)
        print(f"Wrote {len(verdicts)} verdicts to {a.json}")
    if a.trash:
        log = cmd_trash(verdicts, include_review=a.include_review)
        print(
            f"Moved to Trash. Undo log: {log}\nUndo with: python -m sidecar.cli --undo --log {log}"
        )
    else:
        print("\nDry run only — nothing deleted. Re-run with --trash to move to Trash.")


def doctor_main() -> None:
    cmd_doctor()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        cmd_doctor()
    else:
        main()
