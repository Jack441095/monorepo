#!/usr/bin/env python3
"""
End-to-end offline training pipeline with versioned artifacts.

What it does:
- Generates a melody-training JSONL offline (all emotions by default)
- Runs the JSONL eval gate and writes a JSON report
- Trains Markov bundle and optional logit residual into a versioned run folder
- Promotes/copies "active" artifacts into an active models folder
- Writes a single run manifest that links everything together

This is a convenience wrapper around existing scripts + `main.py --offline-train`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _safe_version(v: str) -> str:
    raw = "".join(c for c in str(v or "").strip() if c.isalnum() or c in {"_", "-", "."}).strip("._-")
    if raw:
        return raw
    return time.strftime("v%Y%m%d_%H%M%S")


def _run(cmd: List[str], *, cwd: Path) -> Dict[str, object]:
    started = time.time()
    p = subprocess.run(cmd, cwd=str(cwd), text=True)
    return {
        "cmd": [str(x) for x in cmd],
        "returncode": int(p.returncode),
        "elapsed_seconds": float(time.time() - started),
    }


def _count_raw_emotions(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            emotion = str(row.get("emotion", "") or "").strip().lower()
            if emotion:
                counts[emotion] += 1
    return counts


def _default_emotion_names(root: Path) -> List[str]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from data.music_data import EMOTIONS

    return [str(getattr(e, "name", "") or "").strip().lower() for e in EMOTIONS if str(getattr(e, "name", "") or "").strip()]


def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _git_snapshot(root: Path) -> Dict[str, Optional[str]]:
    def _run_git(args: List[str]) -> Optional[str]:
        try:
            p = subprocess.run(
                ["git", "-C", str(root)] + list(args),
                text=True,
                capture_output=True,
                check=False,
            )
        except Exception:
            return None
        if int(p.returncode) != 0:
            return None
        out = str(p.stdout or "").strip()
        return out or None

    dirty = None
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=False,
        )
        if int(p.returncode) == 0:
            dirty = bool(str(p.stdout or "").strip())
    except Exception:
        dirty = None
    return {
        "commit": _run_git(["rev-parse", "HEAD"]),
        "commit_short": _run_git(["rev-parse", "--short", "HEAD"]),
        "branch": _run_git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty_worktree": None if dirty is None else str(bool(dirty)).lower(),
    }


def _python_runtime_snapshot() -> Dict[str, object]:
    packages = {}
    for name in ("numpy", "scipy"):
        try:
            packages[name] = str(importlib_metadata.version(name))
        except Exception:
            packages[name] = None
    return {
        "python_executable": str(sys.executable),
        "python_version": str(sys.version).splitlines()[0],
        "platform": str(platform.platform()),
        "cwd": str(Path.cwd()),
        "pid": int(os.getpid()),
        "package_versions": packages,
    }


def _full_python_env_snapshot() -> Dict[str, object]:
    """
    Best-effort environment snapshot for run reproducibility.

    Kept JSON-serializable; written to a sidecar file (not embedded directly into
    the manifest) to avoid huge manifests.
    """
    installed: Dict[str, Optional[str]] = {}
    try:
        for d in importlib_metadata.distributions():
            try:
                name = str(getattr(d, "metadata", {}).get("Name") or getattr(d, "name", "") or "").strip()
                if not name:
                    continue
                version = str(getattr(d, "version", "") or "").strip() or None
                installed[name] = version
            except Exception:
                continue
    except Exception:
        installed = {}

    pip_freeze: Optional[List[str]] = None
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if int(p.returncode) == 0:
            lines = [ln.strip() for ln in str(p.stdout or "").splitlines() if ln.strip()]
            pip_freeze = lines
    except Exception:
        pip_freeze = None

    return {
        "runtime": _python_runtime_snapshot(),
        "installed_packages": installed,
        "pip_freeze": pip_freeze,
    }


def _write_env_snapshot(out_path: Path) -> int:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _full_python_env_snapshot()
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except Exception:
        return 1


def _write_run_meta(root: Path, out_path: Path, *, version: str, args: argparse.Namespace) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        handle.write("=== offline training pipeline run_meta ===\n")
        handle.write(f"version={version}\n")
        handle.write(time.strftime("created_at_utc=%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
        handle.write(f"root={root}\n")
        handle.write("\n=== argparse ===\n")
        for k in sorted(vars(args).keys()):
            handle.write(f"{k}={getattr(args, k)!r}\n")
        handle.write("\n=== composition config snapshot ===\n")
    p = subprocess.run(
        [sys.executable, str(root / "scripts" / "snapshot_composition_run_meta.py")],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    with out_path.open("a", encoding="utf-8") as handle:
        if p.stdout:
            handle.write(str(p.stdout))
        if int(p.returncode) != 0:
            handle.write(f"\n# snapshot_composition_run_meta.py failed rc={int(p.returncode)}\n")
    return int(p.returncode)


def _read_eval_gate_ok(report_path: Path) -> Tuple[Optional[bool], Optional[List[str]]]:
    if not report_path.exists() or not report_path.is_file():
        return None, None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    ok = payload.get("ok")
    reasons = payload.get("reasons")
    ok_v: Optional[bool] = bool(ok) if isinstance(ok, bool) else None
    reasons_v: Optional[List[str]] = None
    if isinstance(reasons, list):
        reasons_v = [str(x) for x in reasons]
    return ok_v, reasons_v


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="", help="Version tag for artifacts (default: timestamp).")
    ap.add_argument("--artifacts-dir", default="artifacts", help="Base artifacts directory (default: artifacts).")
    ap.add_argument("--active-dir", default="training_data/active_models", help="Where to promote active models.")

    ap.add_argument("--per-emotion", type=int, default=64)
    ap.add_argument("--dataset-jobs", type=int, default=1, help="Parallel jobs across emotions for dataset generation.")
    ap.add_argument(
        "--min-strongbeat-fit",
        type=float,
        default=0.0,
        help="Optional per-row strong-beat chord-tone fit floor during dataset splitting.",
    )
    ap.add_argument(
        "--tender-min-strongbeat-fit",
        type=float,
        default=0.36,
        help="Stricter per-row strong-beat fit floor for tender/low-energy emotions during dataset splitting.",
    )
    ap.add_argument("--bars", type=int, default=16)
    ap.add_argument("--role-cycle-length", type=int, default=6)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--target-notes-per-bar", type=float, default=6.0)
    ap.add_argument("--root", type=int, default=60)
    ap.add_argument(
        "--style",
        default="",
        help="Optional style profile name for dataset generation (e.g. cinematic_minimal).",
    )
    ap.add_argument(
        "--use-retrained-markov",
        action="store_true",
        help="Use retrained melody Markov during dataset generation (default: disabled).",
    )
    ap.add_argument(
        "--emotions",
        nargs="*",
        default=None,
        help="Optional emotion names to generate/train this run (default: all).",
    )
    ap.add_argument(
        "--append-dataset",
        action="store_true",
        help="Append generated rows to an existing raw dataset for this version instead of overwriting.",
    )
    ap.add_argument(
        "--recover-raw-dataset",
        action="store_true",
        help="Recover an interrupted dataset by splitting the existing .raw.jsonl, then continue training.",
    )
    ap.add_argument(
        "--resume-dataset",
        action="store_true",
        help="Resume an interrupted dataset by appending only emotions with fewer than --per-emotion raw rows, then continue training.",
    )
    ap.add_argument(
        "--skip-dataset",
        action="store_true",
        help="Skip dataset generation and train from the existing live_melody_training.jsonl for this version.",
    )
    ap.add_argument(
        "--generate-only-dataset",
        action="store_true",
        help="Only generate/append raw dataset rows for this version; do not split, evaluate, train, or promote.",
    )
    ap.add_argument(
        "--quality-mode",
        action="store_true",
        help="Enable offline-quality generation knobs for dataset build (slower, cleaner).",
    )
    ap.add_argument(
        "--quality-k-samples",
        type=int,
        default=6,
        help="Best-of-K section samples used during --quality-mode dataset generation (default: 6; lower is faster).",
    )
    ap.add_argument(
        "--disable-voice-leading-dataset",
        action="store_true",
        help="Bypass global voice-leading while generating melody training JSONL (faster; recommended for baseline melody runs).",
    )

    ap.add_argument("--train", choices=("markov", "logit", "all"), default="all")
    ap.add_argument("--dedup", action="store_true", help="Deduplicate rows before Markov training.")
    ap.add_argument("--grouped", choices=("none", "emotion", "family", "both"), default="both")
    ap.add_argument("--min-group-melodies", type=int, default=8)
    ap.add_argument(
        "--reference-data",
        nargs="*",
        default=None,
        help="Curated emotion reference JSONL file(s) or directories to merge before eval/training.",
    )
    ap.add_argument(
        "--reference-weight",
        type=int,
        default=3,
        help="Repeat curated reference rows this many times in the merged dataset.",
    )

    ap.add_argument("--require-metadata", action="store_true", help="Require metadata in eval gate.")
    ap.add_argument("--min-emotions", type=int, default=4)
    ap.add_argument("--min-section-roles", type=int, default=3)
    ap.add_argument("--max-emotion-share", type=float, default=0.45)
    ap.add_argument("--max-dup-rate", type=float, default=0.10)
    ap.add_argument("--max-rest-rate-by-emotion", type=float, default=None)
    ap.add_argument("--min-lines-per-emotion", type=int, default=None)
    ap.add_argument(
        "--min-mean-lyrical",
        type=float,
        default=None,
        help="Optional: fail eval gate if mean lyrical melody score is below this.",
    )

    ap.add_argument("--skip-promote", action="store_true", help="Do not promote outputs to --active-dir.")
    ap.add_argument(
        "--promote-stage",
        choices=("candidate", "canary", "active"),
        default="active",
        help="Stage to promote trained artifacts into (default: active).",
    )
    ap.add_argument(
        "--skip-train",
        action="store_true",
        help="Skip training/promotion and run dataset + diagnostics + eval only.",
    )
    ap.add_argument(
        "--allow-promote-without-metadata",
        action="store_true",
        help="Allow promotion even when --require-metadata is not enabled.",
    )
    ap.add_argument(
        "--run-diagnostics",
        action="store_true",
        help="Run melody + joint diagnostics after dataset build and before training.",
    )
    ap.add_argument(
        "--diagnostics-top",
        type=int,
        default=64,
        help="Top-k rows for melody diagnostics report (default: 64).",
    )
    ap.add_argument(
        "--write-run-meta",
        action="store_true",
        help="Write run_meta.txt with args + composition config snapshot in dataset folder.",
    )
    args = ap.parse_args()

    version = _safe_version(str(args.version or ""))
    artifacts_dir = Path(str(args.artifacts_dir)).expanduser()
    if not artifacts_dir.is_absolute():
        artifacts_dir = root / artifacts_dir

    ds_dir = artifacts_dir / "datasets" / "live_melody" / version
    run_dir = artifacts_dir / "runs" / "offline_training" / version
    models_dir = artifacts_dir / "models" / version
    reports_dir = artifacts_dir / "reports" / version
    for d in (ds_dir, run_dir, models_dir, reports_dir):
        d.mkdir(parents=True, exist_ok=True)

    jsonl_path = ds_dir / "live_melody_training.jsonl"
    rejects_path = ds_dir / "live_melody_rejects.jsonl"
    raw_jsonl_path = jsonl_path.with_suffix(jsonl_path.suffix + ".raw.jsonl")
    eval_report = reports_dir / "melody_jsonl_eval.json"
    diag_report = reports_dir / "melody_emotion_diagnostics.json"
    env_snapshot_path = reports_dir / "env_snapshot.json"
    run_meta_path = ds_dir / "run_meta.txt"

    steps: List[Dict[str, object]] = []

    # Always write an environment snapshot for post-hoc reproducibility.
    # This is intentionally a sidecar file so it can be large without bloating manifests.
    _ = _write_env_snapshot(env_snapshot_path)

    if not bool(args.skip_promote) and not bool(args.require_metadata) and not bool(args.allow_promote_without_metadata):
        print(
            "Refusing to promote without metadata gate. Pass --require-metadata, or explicitly override with "
            "--allow-promote-without-metadata.",
            file=sys.stderr,
        )
        return 2

    if bool(args.write_run_meta):
        rc_meta = _write_run_meta(root, run_meta_path, version=version, args=args)
        steps.append(
            {
                "cmd": ["snapshot-run-meta", str(run_meta_path)],
                "returncode": int(rc_meta),
                "elapsed_seconds": 0.0,
            }
        )
        if rc_meta != 0:
            print(f"run meta snapshot failed: {run_meta_path}", file=sys.stderr)
            return int(rc_meta)

    # 1) Dataset generation
    dataset_cmd = [
        sys.executable,
        str(root / "scripts" / "generate_live_melody_training_jsonl.py"),
        "--out",
        str(jsonl_path),
        "--out-rejects",
        str(rejects_path),
        "--accept-threshold",
        "0.0",
        "--min-strongbeat-fit",
        str(float(args.min_strongbeat_fit)),
        "--tender-min-strongbeat-fit",
        str(float(args.tender_min_strongbeat_fit)),
        "--dedup-kept",
        "--per-emotion",
        str(int(args.per_emotion)),
        "--jobs",
        str(max(1, int(args.dataset_jobs))),
        "--bars",
        str(int(args.bars)),
        "--seed",
        str(int(args.seed)),
        "--target-notes-per-bar",
        str(float(args.target_notes_per_bar)),
        "--root",
        str(int(args.root)),
        "--role-cycle-length",
        str(max(1, int(args.role_cycle_length))),
    ]
    style_name = str(args.style or "").strip()
    if style_name:
        dataset_cmd.extend(["--style", style_name])
    if not bool(args.use_retrained_markov):
        dataset_cmd.append("--disable-retrained-markov")
    if args.emotions:
        dataset_cmd.append("--emotions")
        dataset_cmd.extend([str(x) for x in list(args.emotions or [])])
    if bool(args.append_dataset):
        dataset_cmd.append("--append")
    if bool(args.generate_only_dataset):
        dataset_cmd.append("--generate-only")
    if bool(args.disable_voice_leading_dataset):
        dataset_cmd.append("--disable-voice-leading")
    if bool(args.skip_dataset):
        if not jsonl_path.exists():
            print(f"--skip-dataset requested but dataset does not exist: {jsonl_path}", file=sys.stderr)
            return 2
        steps.append({"cmd": ["skip-dataset", str(jsonl_path)], "returncode": 0, "elapsed_seconds": 0.0})
    elif bool(args.resume_dataset):
        raw_counts = _count_raw_emotions(raw_jsonl_path)
        if args.emotions:
            target_emotions = [str(x).strip().lower() for x in list(args.emotions or []) if str(x).strip()]
        else:
            target_emotions = _default_emotion_names(root)
        target_count = max(1, int(args.per_emotion))
        missing = [
            (name, max(0, int(target_count) - int(raw_counts.get(str(name).lower(), 0))))
            for name in target_emotions
        ]
        missing = [(name, count) for name, count in missing if count > 0]
        steps.append(
            {
                "cmd": ["resume-dataset", str(raw_jsonl_path)],
                "returncode": 0,
                "elapsed_seconds": 0.0,
                "raw_counts": dict(raw_counts),
                "missing": [{"emotion": name, "count": int(count)} for name, count in missing],
            }
        )
        if missing:
            print(
                "resume-dataset: appending "
                + ", ".join(f"{name}:{count}" for name, count in missing)
            )
        else:
            print("resume-dataset: raw dataset already has requested rows; splitting existing raw")
        for name, count in missing:
            resume_cmd = [
                sys.executable,
                str(root / "scripts" / "generate_live_melody_training_jsonl.py"),
                "--out",
                str(jsonl_path),
                "--out-rejects",
                str(rejects_path),
                "--accept-threshold",
                "0.0",
                "--min-strongbeat-fit",
                str(float(args.min_strongbeat_fit)),
                "--tender-min-strongbeat-fit",
                str(float(args.tender_min_strongbeat_fit)),
                "--dedup-kept",
                "--per-emotion",
                str(int(count)),
                "--jobs",
                "1",
                "--bars",
                str(int(args.bars)),
                "--seed",
                str(int(args.seed)),
                "--target-notes-per-bar",
                str(float(args.target_notes_per_bar)),
                "--root",
                str(int(args.root)),
                "--role-cycle-length",
                str(max(1, int(args.role_cycle_length))),
                "--emotions",
                str(name),
                "--append",
                "--generate-only",
            ]
            if style_name:
                resume_cmd.extend(["--style", style_name])
            if not bool(args.use_retrained_markov):
                resume_cmd.append("--disable-retrained-markov")
            if bool(args.quality_mode):
                resume_cmd.extend(["--quality-mode", "--quality-k-samples", str(int(args.quality_k_samples))])
            if bool(args.disable_voice_leading_dataset):
                resume_cmd.append("--disable-voice-leading")
            steps.append(_run(resume_cmd, cwd=root))
            if int(steps[-1]["returncode"]) != 0:
                print(f"resume dataset generation failed for emotion={name}", file=sys.stderr)
                return int(steps[-1]["returncode"])
        recover_cmd = list(dataset_cmd)
        recover_cmd.append("--split-existing-raw")
        steps.append(_run(recover_cmd, cwd=root))
        if int(steps[-1]["returncode"]) != 0:
            print("raw dataset split after resume failed", file=sys.stderr)
            return int(steps[-1]["returncode"])
        if bool(args.generate_only_dataset):
            print(f"resume generate-only dataset step complete for version={version}")
            return 0
    elif bool(args.recover_raw_dataset):
        recover_cmd = list(dataset_cmd)
        recover_cmd.append("--split-existing-raw")
        steps.append(_run(recover_cmd, cwd=root))
        if int(steps[-1]["returncode"]) != 0:
            print("raw dataset recovery failed", file=sys.stderr)
            return int(steps[-1]["returncode"])
    else:
        if bool(args.quality_mode):
            dataset_cmd.extend(["--quality-mode", "--quality-k-samples", str(int(args.quality_k_samples))])
        steps.append(_run(dataset_cmd, cwd=root))
        if int(steps[-1]["returncode"]) != 0:
            print("dataset generation failed", file=sys.stderr)
            return int(steps[-1]["returncode"])
        if bool(args.generate_only_dataset):
            print(f"generate-only dataset step complete for version={version}")
            return 0

    train_jsonl_path = jsonl_path
    if args.reference_data:
        merged_path = ds_dir / "live_melody_training.with_references.jsonl"
        merge_cmd = [
            sys.executable,
            str(root / "scripts" / "merge_emotion_reference_dataset.py"),
            "--base",
            str(jsonl_path),
            "--out",
            str(merged_path),
            "--reference-weight",
            str(int(args.reference_weight)),
            "--references",
        ]
        merge_cmd.extend([str(x) for x in list(args.reference_data or [])])
        steps.append(_run(merge_cmd, cwd=root))
        if int(steps[-1]["returncode"]) != 0:
            print("reference dataset merge failed", file=sys.stderr)
            return int(steps[-1]["returncode"])
        train_jsonl_path = merged_path

    # Optional diagnostics pass for tuning and review.
    if bool(args.run_diagnostics):
        diag_cmd = [
            sys.executable,
            str(root / "scripts" / "melody_emotion_diagnostics.py"),
            str(train_jsonl_path),
            "--top",
            str(max(1, int(args.diagnostics_top))),
            "--json-out",
            str(diag_report),
        ]
        steps.append(_run(diag_cmd, cwd=root))
        if int(steps[-1]["returncode"]) != 0:
            print("melody diagnostics failed", file=sys.stderr)
            return int(steps[-1]["returncode"])

        joint_cmd = ["bash", str(root / "scripts" / "run_joint_fast_checks.sh"), str(train_jsonl_path)]
        steps.append(_run(joint_cmd, cwd=root))
        if int(steps[-1]["returncode"]) != 0:
            print("joint diagnostics failed", file=sys.stderr)
            return int(steps[-1]["returncode"])

    # 2) Eval gate
    gate_cmd = [
        sys.executable,
        str(root / "scripts" / "melody_eval_gate.py"),
        str(train_jsonl_path),
        "--report",
        str(eval_report),
        "--min-emotions",
        str(int(args.min_emotions)),
        "--min-section-roles",
        str(int(args.min_section_roles)),
        "--max-emotion-share",
        str(float(args.max_emotion_share)),
        "--max-dup-rate",
        str(float(args.max_dup_rate)),
    ]
    if bool(args.require_metadata):
        gate_cmd.append("--require-metadata")
        # Do not require chord_sequence alignment by default; generator exports bar-level chords.
    if args.max_rest_rate_by_emotion is not None:
        gate_cmd.extend(["--max-rest-rate-by-emotion", str(float(args.max_rest_rate_by_emotion))])
    if args.min_lines_per_emotion is not None:
        gate_cmd.extend(["--min-lines-per-emotion", str(int(args.min_lines_per_emotion))])
    if args.min_mean_lyrical is not None:
        gate_cmd.extend(["--min-mean-lyrical", str(float(args.min_mean_lyrical))])
    steps.append(_run(gate_cmd, cwd=root))
    if int(steps[-1]["returncode"]) != 0:
        print("eval gate failed", file=sys.stderr)
        return int(steps[-1]["returncode"])

    if bool(args.skip_train):
        manifest = {
            "schema_version": 1,
            "version": version,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git": _git_snapshot(root),
            "runtime": _python_runtime_snapshot(),
            "paths": {
                "artifacts_dir": str(artifacts_dir),
                "dataset_jsonl": str(jsonl_path),
                "training_jsonl": str(train_jsonl_path),
                "dataset_rejects_jsonl": str(rejects_path),
                "eval_report": str(eval_report),
                "diagnostics_report": str(diag_report) if bool(args.run_diagnostics) else "",
                "env_snapshot": str(env_snapshot_path),
                "run_meta": str(run_meta_path) if bool(args.write_run_meta) else "",
                "offline_run_dir": "",
                "active_dir": str(Path(str(args.active_dir)).expanduser()),
            },
            "checksums": {
                "dataset_jsonl_sha256": _sha256_file(jsonl_path),
                "training_jsonl_sha256": _sha256_file(train_jsonl_path),
                "dataset_rejects_jsonl_sha256": _sha256_file(rejects_path),
                "eval_report_sha256": _sha256_file(eval_report),
                "diagnostics_report_sha256": _sha256_file(diag_report) if bool(args.run_diagnostics) else None,
                "env_snapshot_sha256": _sha256_file(env_snapshot_path),
                "run_meta_sha256": _sha256_file(run_meta_path) if bool(args.write_run_meta) else None,
            },
            "config": {
                "per_emotion": int(args.per_emotion),
                "dataset_jobs": int(max(1, int(args.dataset_jobs))),
                "min_strongbeat_fit": float(args.min_strongbeat_fit),
                "tender_min_strongbeat_fit": float(args.tender_min_strongbeat_fit),
                "bars": int(args.bars),
                "role_cycle_length": int(max(1, int(args.role_cycle_length))),
                "seed": int(args.seed),
                "target_notes_per_bar": float(args.target_notes_per_bar),
                "root": int(args.root),
                "style": style_name or None,
                "use_retrained_markov": bool(args.use_retrained_markov),
                "emotions": None if not args.emotions else [str(x) for x in list(args.emotions or [])],
                "quality_mode": bool(args.quality_mode),
                "quality_k_samples": int(args.quality_k_samples),
                "disable_voice_leading_dataset": bool(args.disable_voice_leading_dataset),
                "append_dataset": bool(args.append_dataset),
                "recover_raw_dataset": bool(args.recover_raw_dataset),
                "resume_dataset": bool(args.resume_dataset),
                "skip_dataset": bool(args.skip_dataset),
                "generate_only_dataset": bool(args.generate_only_dataset),
                "skip_train": True,
                "skip_promote": True,
                "promote_stage": str(args.promote_stage),
                "train": str(args.train),
                "grouped": str(args.grouped),
                "min_group_melodies": int(args.min_group_melodies),
                "dedup": bool(args.dedup),
                "reference_data": None if not args.reference_data else [str(x) for x in list(args.reference_data or [])],
                "reference_weight": int(args.reference_weight),
                "run_diagnostics": bool(args.run_diagnostics),
                "diagnostics_top": int(args.diagnostics_top),
                "write_run_meta": bool(args.write_run_meta),
            },
            "gate": {
                "require_metadata": bool(args.require_metadata),
                "min_emotions": int(args.min_emotions),
                "min_section_roles": int(args.min_section_roles),
                "max_emotion_share": float(args.max_emotion_share),
                "max_dup_rate": float(args.max_dup_rate),
                "max_rest_rate_by_emotion": None if args.max_rest_rate_by_emotion is None else float(args.max_rest_rate_by_emotion),
                "min_lines_per_emotion": None if args.min_lines_per_emotion is None else int(args.min_lines_per_emotion),
                "min_mean_lyrical": None if args.min_mean_lyrical is None else float(args.min_mean_lyrical),
            },
            "steps": steps,
        }
        out = artifacts_dir / "manifests" / f"{version}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out}")
        return 0

    # 3) Offline train (main.py writes into .cache/offline_training/<tag>/)
    tag = f"{version}"
    train_cmd = [
        sys.executable,
        str(root / "main.py"),
        "--offline-train",
        str(args.train),
        "--offline-train-jsonl",
        str(train_jsonl_path),
        "--offline-train-tag",
        tag,
        "--offline-train-dir",
        str(run_dir),
        "--offline-train-grouped",
        str(args.grouped),
        "--offline-train-min-group-melodies",
        str(int(args.min_group_melodies)),
        "--offline-train-skip-eval",
        "--offline-train-min-emotions",
        str(int(args.min_emotions)),
        "--offline-train-min-section-roles",
        str(int(args.min_section_roles)),
        "--offline-train-max-emotion-share",
        str(float(args.max_emotion_share)),
    ]
    if bool(args.dedup):
        train_cmd.append("--offline-train-dedup")
    steps.append(_run(train_cmd, cwd=root))
    if int(steps[-1]["returncode"]) != 0:
        print("offline training failed", file=sys.stderr)
        return int(steps[-1]["returncode"])

    eval_ok, eval_reasons = _read_eval_gate_ok(eval_report)
    if eval_ok is not True:
        reason_s = "; ".join(eval_reasons or []) if eval_reasons else "(report missing/invalid)"
        print(f"promotion blocked: eval gate report not PASS: {reason_s}", file=sys.stderr)
        return 2

    expected_outputs: List[Path] = []
    tag_run_dir = run_dir / tag
    if str(args.train) in {"markov", "all"}:
        expected_outputs.extend(
            [
                tag_run_dir / f"{tag}_melody_markov.pkl",
                tag_run_dir / f"{tag}_chord_markov.pkl",
                tag_run_dir / f"{tag}_melody_markov.manifest.json",
                tag_run_dir / f"{tag}_chord_markov.manifest.json",
            ]
        )
    if str(args.train) in {"logit", "all"}:
        expected_outputs.append(tag_run_dir / f"{tag}_melody_logit_residual.npz")
    missing_outputs = [str(p) for p in expected_outputs if not p.exists()]
    if missing_outputs:
        print("promotion blocked: expected training outputs missing:", file=sys.stderr)
        for m in missing_outputs:
            print(f"  - {m}", file=sys.stderr)
        return 2

    # 4) Promote (copy into active models folder)
    promoted: Optional[Dict[str, object]] = None
    if not bool(args.skip_promote):
        promote_cmd = [
            sys.executable,
            str(root / "scripts" / "promote_training_artifact.py"),
            str(run_dir / tag),
            "--kind",
            "all" if str(args.train) == "all" else str(args.train),
            "--stage",
            str(args.promote_stage),
            "--active-dir",
            str(args.active_dir),
        ]
        promoted = _run(promote_cmd, cwd=root)
        steps.append(promoted)
        if int(promoted["returncode"]) != 0:
            print("promotion failed", file=sys.stderr)
            return int(promoted["returncode"])

    manifest = {
        "schema_version": 1,
        "version": version,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": _git_snapshot(root),
        "runtime": _python_runtime_snapshot(),
        "paths": {
            "artifacts_dir": str(artifacts_dir),
            "dataset_jsonl": str(jsonl_path),
            "training_jsonl": str(train_jsonl_path),
            "dataset_rejects_jsonl": str(rejects_path),
            "eval_report": str(eval_report),
            "diagnostics_report": str(diag_report) if bool(args.run_diagnostics) else "",
            "env_snapshot": str(env_snapshot_path),
            "run_meta": str(run_meta_path) if bool(args.write_run_meta) else "",
            "offline_run_dir": str(run_dir / tag),
            "active_dir": str(Path(str(args.active_dir)).expanduser()),
        },
        "checksums": {
            "dataset_jsonl_sha256": _sha256_file(jsonl_path),
            "training_jsonl_sha256": _sha256_file(train_jsonl_path),
            "dataset_rejects_jsonl_sha256": _sha256_file(rejects_path),
            "eval_report_sha256": _sha256_file(eval_report),
            "diagnostics_report_sha256": _sha256_file(diag_report) if bool(args.run_diagnostics) else None,
            "env_snapshot_sha256": _sha256_file(env_snapshot_path),
            "run_meta_sha256": _sha256_file(run_meta_path) if bool(args.write_run_meta) else None,
        },
        "config": {
            "per_emotion": int(args.per_emotion),
            "dataset_jobs": int(max(1, int(args.dataset_jobs))),
            "bars": int(args.bars),
            "role_cycle_length": int(max(1, int(args.role_cycle_length))),
            "seed": int(args.seed),
            "target_notes_per_bar": float(args.target_notes_per_bar),
            "root": int(args.root),
            "style": style_name or None,
            "use_retrained_markov": bool(args.use_retrained_markov),
            "emotions": None if not args.emotions else [str(x) for x in list(args.emotions or [])],
            "quality_mode": bool(args.quality_mode),
            "quality_k_samples": int(args.quality_k_samples),
            "disable_voice_leading_dataset": bool(args.disable_voice_leading_dataset),
            "append_dataset": bool(args.append_dataset),
            "recover_raw_dataset": bool(args.recover_raw_dataset),
            "resume_dataset": bool(args.resume_dataset),
            "skip_dataset": bool(args.skip_dataset),
            "generate_only_dataset": bool(args.generate_only_dataset),
            "promote_stage": str(args.promote_stage),
            "train": str(args.train),
            "grouped": str(args.grouped),
            "min_group_melodies": int(args.min_group_melodies),
            "dedup": bool(args.dedup),
            "reference_data": None if not args.reference_data else [str(x) for x in list(args.reference_data or [])],
            "reference_weight": int(args.reference_weight),
            "run_diagnostics": bool(args.run_diagnostics),
            "diagnostics_top": int(args.diagnostics_top),
            "write_run_meta": bool(args.write_run_meta),
        },
        "gate": {
            "require_metadata": bool(args.require_metadata),
            "min_emotions": int(args.min_emotions),
            "min_section_roles": int(args.min_section_roles),
            "max_emotion_share": float(args.max_emotion_share),
            "max_dup_rate": float(args.max_dup_rate),
            "max_rest_rate_by_emotion": None if args.max_rest_rate_by_emotion is None else float(args.max_rest_rate_by_emotion),
            "min_lines_per_emotion": None if args.min_lines_per_emotion is None else int(args.min_lines_per_emotion),
            "min_mean_lyrical": None if args.min_mean_lyrical is None else float(args.min_mean_lyrical),
        },
        "steps": steps,
    }
    out = artifacts_dir / "manifests" / f"{version}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
