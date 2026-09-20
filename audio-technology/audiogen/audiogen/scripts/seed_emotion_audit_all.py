#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def _load_emotions(repo_root: Path) -> List[str]:
    root_s = str(repo_root.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    from data.music_data import EMOTIONS

    names = []
    for e in list(EMOTIONS or []):
        nm = str(getattr(e, "name", "") or "").strip().lower()
        if nm:
            names.append(nm)
    return names


def _run_one_emotion(
    *,
    repo_root: Path,
    emotion: str,
    runs: int,
    root_midi: int,
    out_dir: Path,
    extra_args: List[str],
) -> Dict[str, object]:
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "seed_emotion_audit.py"),
        "--emotion",
        str(emotion),
        "--runs",
        str(int(runs)),
        "--root",
        str(int(root_midi)),
        "--out-dir",
        str(out_dir),
    ]
    for a in list(extra_args or []):
        cmd.extend(["--extra-arg", str(a)])

    proc = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)
    summary_path = ""
    if proc.stdout:
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        if lines:
            summary_path = lines[-1]

    row: Dict[str, object] = {
        "emotion": str(emotion),
        "returncode": int(proc.returncode),
        "summary_path": str(summary_path),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
    }

    if summary_path:
        p = Path(summary_path)
        if p.is_file():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                row["summary"] = payload
                row["session_dir"] = str(payload.get("session_dir", ""))
            except Exception:
                pass
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Run seed emotion audit across all emotions.")
    ap.add_argument("--runs", type=int, default=3, help="Runs per emotion (default: 3).")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI note (default: 60).")
    ap.add_argument("--out-dir", default="artifacts/seed_audit_all", help="Output directory.")
    ap.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra CLI arg forwarded to main.py via seed_emotion_audit.py (repeatable).",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = Path(str(args.out_dir)).expanduser()
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_dir / f"all_emotions_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    emotions = _load_emotions(repo_root)
    results: List[Dict[str, object]] = []

    for emo in emotions:
        results.append(
            _run_one_emotion(
                repo_root=repo_root,
                emotion=str(emo),
                runs=max(1, int(args.runs)),
                root_midi=int(args.root),
                out_dir=run_dir,
                extra_args=list(args.extra_arg or []),
            )
        )

    rc_counts = Counter(int(r.get("returncode", 999)) for r in results)
    failed = [str(r.get("emotion")) for r in results if int(r.get("returncode", 999)) != 0]

    gaps: Dict[str, List[int]] = {}
    for r in results:
        emo = str(r.get("emotion", ""))
        vals: List[int] = []
        s = r.get("summary")
        if isinstance(s, dict):
            ch = s.get("chorus_lead_minus_arp_median")
            if isinstance(ch, dict):
                vv = ch.get("values")
                if isinstance(vv, list):
                    vals = [int(x) for x in vv if isinstance(x, int)]
        gaps[emo] = vals

    combined_events_jsonl = run_dir / "all_note_events.jsonl"
    with combined_events_jsonl.open("w", encoding="utf-8") as out_f:
        for r in results:
            s = r.get("summary")
            if not isinstance(s, dict):
                continue
            p = Path(str(s.get("all_note_events_jsonl", "") or ""))
            if not p.is_file():
                continue
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if ln.strip():
                    out_f.write(ln.strip() + "\n")

    master = {
        "runs_per_emotion": int(max(1, int(args.runs))),
        "root_midi": int(args.root),
        "emotions_total": int(len(emotions)),
        "returncodes": {str(k): int(v) for k, v in sorted(rc_counts.items())},
        "failed_emotions": failed,
        "all_note_events_jsonl": str(combined_events_jsonl),
        "chorus_lead_minus_arp_median_by_emotion": gaps,
        "results": results,
    }

    master_json = run_dir / "all_emotions_audit_summary.json"
    master_json.write_text(json.dumps(master, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"run_dir={run_dir}",
        f"emotions_total={len(emotions)}",
        f"runs_per_emotion={max(1, int(args.runs))}",
        f"returncodes={dict(sorted(rc_counts.items()))}",
        f"failed_emotions={failed}",
        f"master_json={master_json}",
    ]
    (run_dir / "all_emotions_audit_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(str(master_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
