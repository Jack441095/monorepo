#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Tuple

LINE_RE = re.compile(r"\b(\w+)=([^\s]+)")


def _parse_kv_line(line: str) -> Dict[str, str]:
    return {k: v for k, v in LINE_RE.findall(str(line or ""))}


def _parse_scalar(raw: str):
    s = str(raw or "").strip()
    if s == "":
        return ""
    low = s.lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        return s


def _extract_full_note_events(
    note_log_path: Path,
    *,
    emotion: str,
    run_index: int,
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    if not note_log_path.is_file():
        return [], {"events_total": 0}
    out: List[Dict[str, object]] = []
    lines = note_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_no, line in enumerate(lines, start=1):
        if not line.startswith("CREATED "):
            continue
        kv = _parse_kv_line(line)
        if str(kv.get("emotion", "")).strip().lower() != str(emotion).strip().lower():
            continue
        row: Dict[str, object] = {
            "run_index": int(run_index),
            "line_no": int(line_no),
            "raw": line,
        }
        for k, v in kv.items():
            row[str(k)] = _parse_scalar(v)
        out.append(row)
    return out, {"events_total": int(len(out))}


def _extract_seed(lines: List[str]) -> Optional[int]:
    for line in lines:
        if "Generation seed (this run):" not in line:
            continue
        m = re.search(r"Generation seed \(this run\):\s*(\d+)", line)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
    return None


def _summarize_note_log(note_log_path: Path, emotion: str) -> Dict[str, object]:
    if not note_log_path.is_file():
        return {"note_log_path": str(note_log_path), "events": 0, "channels": {}, "chorus": {}}

    lines = note_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    events = 0
    channel_counts: Counter[int] = Counter()
    section_role_counts: Counter[str] = Counter()
    seed_counts: Counter[int] = Counter()
    chorus_lead: List[int] = []
    chorus_arp: List[int] = []

    for line in lines:
        if not line.startswith("CREATED "):
            continue
        kv = _parse_kv_line(line)
        if str(kv.get("emotion", "")).strip().lower() != str(emotion).strip().lower():
            continue
        try:
            ch = int(kv.get("channel", "-1"))
            seed = int(kv.get("seed", "-1"))
            midi = int(kv.get("midi", "-1"))
        except Exception:
            continue
        role = str(kv.get("section_role", "") or "").strip().lower()
        events += 1
        channel_counts[ch] += 1
        section_role_counts[role] += 1
        if seed >= 0:
            seed_counts[seed] += 1
        if role in {"b", "chorus", "hook", "tag"}:
            if ch == 2 and midi >= 0:
                chorus_lead.append(midi)
            elif ch == 3 and midi >= 0:
                chorus_arp.append(midi)

    lead_med = int(median(chorus_lead)) if chorus_lead else None
    arp_med = int(median(chorus_arp)) if chorus_arp else None
    gap = (lead_med - arp_med) if (lead_med is not None and arp_med is not None) else None

    return {
        "note_log_path": str(note_log_path),
        "events": int(events),
        "channels": {str(k): int(v) for k, v in sorted(channel_counts.items())},
        "section_roles": {str(k): int(v) for k, v in sorted(section_role_counts.items()) if k},
        "seeds_seen": {str(k): int(v) for k, v in sorted(seed_counts.items())},
        "chorus": {
            "lead_note_count": int(len(chorus_lead)),
            "arp_note_count": int(len(chorus_arp)),
            "lead_median_midi": lead_med,
            "arp_median_midi": arp_med,
            "lead_minus_arp_median": gap,
        },
    }


def _run_once(
    *,
    repo_root: Path,
    emotion: str,
    root_midi: int,
    out_dir: Path,
    run_index: int,
    extra_args: List[str],
) -> Dict[str, object]:
    run_dir = out_dir / f"run_{run_index:02d}"
    export_dir = run_dir / "exports"
    note_log_path = run_dir / "notes.log"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    run_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(repo_root / "main.py"),
        "--mode",
        "offline",
        "--offline-count",
        "1",
        "--offline-emotion",
        str(emotion),
        "--root",
        str(int(root_midi)),
        "--offline-export-dir",
        str(export_dir),
        "--offline-export-prefix",
        f"seed_audit_{emotion}",
        "--offline-outputs",
        "wav,midi,report,meta",
        "--note-log",
        "--note-log-path",
        str(note_log_path),
        "--quiet",
    ]
    cmd.extend(list(extra_args or []))

    with stdout_path.open("w", encoding="utf-8") as out_f, stderr_path.open("w", encoding="utf-8") as err_f:
        proc = subprocess.run(cmd, cwd=str(repo_root), stdout=out_f, stderr=err_f)

    out_lines = stdout_path.read_text(encoding="utf-8", errors="replace").splitlines() if stdout_path.exists() else []
    err_lines = stderr_path.read_text(encoding="utf-8", errors="replace").splitlines() if stderr_path.exists() else []
    launch_seed = _extract_seed(out_lines + err_lines)

    summary = _summarize_note_log(note_log_path, emotion)
    full_events, full_meta = _extract_full_note_events(
        note_log_path,
        emotion=str(emotion),
        run_index=int(run_index),
    )
    full_events_jsonl = run_dir / "note_events.jsonl"
    with full_events_jsonl.open("w", encoding="utf-8") as f:
        for ev in list(full_events or []):
            f.write(json.dumps(ev, sort_keys=True) + "\n")
    summary.update(
        {
            "run_index": int(run_index),
            "returncode": int(proc.returncode),
            "launch_seed": launch_seed,
            "cmd": cmd,
            "run_dir": str(run_dir),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "full_note_events_jsonl": str(full_events_jsonl),
            "full_note_events_count": int(full_meta.get("events_total", 0)),
        }
    )
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Run 3x randomized offline renders for one emotion and write audit files.")
    ap.add_argument("--emotion", required=True, help="Emotion name to audit (e.g. excitement, sadness).")
    ap.add_argument("--runs", type=int, default=3, help="How many runs to generate (default: 3).")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI note (default: 60).")
    ap.add_argument("--out-dir", default="artifacts/seed_audit", help="Output directory for audit artifacts.")
    ap.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra CLI args passed through to main.py (repeatable). Example: --extra-arg=--offline-arrangement-form --extra-arg=swing",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand_tag = f"r{random.randint(1000, 9999)}"
    out_dir = Path(str(args.out_dir)).expanduser()
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    session_dir = out_dir / f"{args.emotion}_{ts}_{rand_tag}"
    session_dir.mkdir(parents=True, exist_ok=True)

    runs = max(1, int(args.runs))
    results: List[Dict[str, object]] = []
    for i in range(1, runs + 1):
        results.append(
            _run_once(
                repo_root=repo_root,
                emotion=str(args.emotion),
                root_midi=int(args.root),
                out_dir=session_dir,
                run_index=int(i),
                extra_args=list(args.extra_arg or []),
            )
        )

    lead_arp_gaps = [
        int(x["chorus"]["lead_minus_arp_median"])
        for x in results
        if isinstance(x.get("chorus"), dict)
        and isinstance(x["chorus"].get("lead_minus_arp_median"), int)
    ]
    rc_counts = Counter(int(x.get("returncode", 999)) for x in results)

    by_seed: Dict[str, int] = defaultdict(int)
    for row in results:
        s = row.get("launch_seed")
        if s is not None:
            by_seed[str(s)] += 1

    all_events_jsonl = session_dir / "all_note_events.jsonl"
    with all_events_jsonl.open("w", encoding="utf-8") as out_f:
        for row in results:
            p = Path(str(row.get("full_note_events_jsonl", "") or ""))
            if not p.is_file():
                continue
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if ln.strip():
                    out_f.write(ln.strip() + "\n")

    summary = {
        "emotion": str(args.emotion),
        "runs": int(runs),
        "root_midi": int(args.root),
        "session_dir": str(session_dir),
        "returncodes": {str(k): int(v) for k, v in sorted(rc_counts.items())},
        "launch_seed_counts": dict(sorted(by_seed.items())),
        "all_note_events_jsonl": str(all_events_jsonl),
        "chorus_lead_minus_arp_median": {
            "values": list(lead_arp_gaps),
            "min": min(lead_arp_gaps) if lead_arp_gaps else None,
            "max": max(lead_arp_gaps) if lead_arp_gaps else None,
        },
        "results": results,
    }

    summary_path = session_dir / "audit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    text_lines = [
        f"emotion={args.emotion}",
        f"runs={runs}",
        f"session_dir={session_dir}",
        f"returncodes={dict(sorted(rc_counts.items()))}",
        f"launch_seed_counts={dict(sorted(by_seed.items()))}",
        f"chorus_lead_minus_arp_median={lead_arp_gaps}",
        f"audit_summary_json={summary_path}",
    ]
    (session_dir / "audit_summary.txt").write_text("\n".join(text_lines) + "\n", encoding="utf-8")

    print(str(summary_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
