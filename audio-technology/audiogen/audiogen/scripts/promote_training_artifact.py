#!/usr/bin/env python3
"""Promote offline training artifacts into the active local model folder."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


ACTIVE_NAMES = {
    "markov_pickle": "melody_markov.pkl",
    "chord_markov_pickle": "chord_markov.pkl",
    "logit_residual": "melody_logit_residual.npz",
}
STAGES = ("candidate", "canary", "active")


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"{path}: failed to read manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: manifest must be a JSON object")
    return payload


def _find_manifest(run_dir: Path, explicit: str) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = run_dir / path
        if not path.is_file():
            raise SystemExit(f"manifest not found: {path}")
        return path
    candidates = sorted(run_dir.glob("*_offline_training_manifest.json"))
    if len(candidates) != 1:
        raise SystemExit(f"expected exactly one offline training manifest in {run_dir}, found {len(candidates)}")
    return candidates[0]


def _selected_outputs(manifest: Dict[str, Any], kind: str) -> List[Tuple[str, Path, str]]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise SystemExit("offline manifest has no outputs object")
    wanted = set(ACTIVE_NAMES)
    if kind == "markov":
        wanted = {"markov_pickle", "chord_markov_pickle"}
    elif kind == "logit":
        wanted = {"logit_residual"}

    selected: List[Tuple[str, Path, str]] = []
    for key in sorted(wanted):
        raw = outputs.get(key)
        if not raw:
            if kind != "all":
                raise SystemExit(f"offline manifest has no {key!r} output")
            continue
        src = Path(str(raw)).expanduser()
        selected.append((key, src, ACTIVE_NAMES[key]))
    if not selected:
        raise SystemExit(f"no promotable outputs found for kind={kind}")
    return selected


def _load_existing_active_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"schema_version": 2, "stages": {}, "active_stage": "active", "artifacts": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 2, "stages": {}, "active_stage": "active", "artifacts": []}
    if not isinstance(payload, dict):
        return {"schema_version": 2, "stages": {}, "active_stage": "active", "artifacts": []}
    if "stages" not in payload or not isinstance(payload.get("stages"), dict):
        payload["stages"] = {}
    if "active_stage" not in payload:
        payload["active_stage"] = "active"
    if "artifacts" not in payload or not isinstance(payload.get("artifacts"), list):
        payload["artifacts"] = []
    payload["schema_version"] = 2
    return payload


def _activation_plan_from_manifest(active_dir: Path, active_manifest: Dict[str, Any], stage: str) -> List[Dict[str, str]]:
    stages = active_manifest.get("stages")
    if not isinstance(stages, dict):
        raise SystemExit(f"active manifest has no stages data: {active_dir / 'active_manifest.json'}")
    stage_entry = stages.get(str(stage))
    if not isinstance(stage_entry, dict):
        raise SystemExit(f"stage '{stage}' not found in active manifest")
    artifacts = stage_entry.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise SystemExit(f"stage '{stage}' has no artifacts to activate")
    plan: List[Dict[str, str]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if kind not in ACTIVE_NAMES:
            continue
        src = Path(str(item.get("destination") or "")).expanduser()
        if not src.is_absolute():
            src = active_dir / src
        if not src.is_file():
            raise SystemExit(f"stage source missing for activation: {src}")
        dst = active_dir / ACTIVE_NAMES[kind]
        plan.append({"kind": kind, "source": str(src), "destination": str(dst)})
    if not plan:
        raise SystemExit(f"stage '{stage}' has no valid promotable artifacts")
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "run_dir",
        nargs="?",
        default=".",
        help="Offline training run directory containing *_offline_training_manifest.json.",
    )
    ap.add_argument(
        "--manifest",
        default="",
        help="Optional manifest filename/path. Defaults to the only *_offline_training_manifest.json in run_dir.",
    )
    ap.add_argument("--kind", choices=("markov", "logit", "all"), default="all")
    ap.add_argument("--active-dir", default="training_data/active_models", help="Destination directory for active model files.")
    ap.add_argument("--stage", choices=STAGES, default="active", help="Promotion stage (candidate/canary/active).")
    ap.add_argument(
        "--activate-stage",
        choices=STAGES,
        default="",
        help="Activate an already staged bundle by copying it to runtime filenames.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print planned promotion without writing files.")
    args = ap.parse_args()

    active_dir = Path(str(args.active_dir)).expanduser()

    manifest_out = active_dir / "active_manifest.json"
    existing_active = _load_existing_active_manifest(manifest_out)

    if str(args.activate_stage or "").strip():
        activate_stage = str(args.activate_stage).strip().lower()
        if activate_stage not in STAGES:
            raise SystemExit(f"invalid activate stage: {activate_stage}")
        plan = _activation_plan_from_manifest(active_dir, existing_active, activate_stage)
        active_manifest = dict(existing_active)
        active_manifest["active_stage"] = str(activate_stage)
        active_manifest["activated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        active_manifest["artifacts"] = plan
        active_manifest["dry_run"] = bool(args.dry_run)
        if args.dry_run:
            print(json.dumps(active_manifest, indent=2, sort_keys=True))
            return 0
        active_dir.mkdir(parents=True, exist_ok=True)
        for item in plan:
            shutil.copy2(item["source"], item["destination"])
            print(f"activated {item['kind']}: {item['destination']}")
        manifest_out.write_text(json.dumps(active_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {manifest_out}")
        return 0

    run_dir = Path(str(args.run_dir)).expanduser()
    if not run_dir.is_dir():
        raise SystemExit(f"run directory not found: {run_dir}")

    manifest_path = _find_manifest(run_dir, str(args.manifest or ""))
    manifest = _load_json(manifest_path)
    selected = _selected_outputs(manifest, str(args.kind))
    stage = str(args.stage).strip().lower()
    if stage not in STAGES:
        raise SystemExit(f"invalid stage: {stage}")

    stage_dir = active_dir / "stages" / stage
    plan: List[Dict[str, str]] = []
    for key, src, active_name in selected:
        if not src.is_absolute():
            src = run_dir / src
        if not src.is_file():
            raise SystemExit(f"{key} source not found: {src}")
        stage_dst = stage_dir / active_name
        plan.append({"kind": key, "source": str(src), "destination": str(stage_dst)})

    active_manifest = dict(existing_active)
    stages = dict(active_manifest.get("stages") or {})
    stage_entry = {
        "source_manifest": str(manifest_path),
        "source_run_dir": str(run_dir),
        "source_tag": str(manifest.get("tag") or ""),
        "kind": str(args.kind),
        "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifacts": plan,
    }
    stages[str(stage)] = stage_entry
    active_manifest["stages"] = stages
    active_manifest["last_promotion"] = {"stage": str(stage), "at": stage_entry["promoted_at"]}
    active_manifest["dry_run"] = bool(args.dry_run)

    # Backward-compatible behavior: staging to "active" also updates runtime roots.
    root_plan: List[Dict[str, str]] = []
    if str(stage) == "active":
        for item in plan:
            kind = str(item["kind"])
            root_plan.append(
                {
                    "kind": kind,
                    "source": str(item["destination"]),
                    "destination": str(active_dir / ACTIVE_NAMES[kind]),
                }
            )
        active_manifest["active_stage"] = "active"
        active_manifest["activated_at"] = stage_entry["promoted_at"]
        active_manifest["artifacts"] = root_plan

    if args.dry_run:
        print(json.dumps(active_manifest, indent=2, sort_keys=True))
        return 0

    stage_dir.mkdir(parents=True, exist_ok=True)
    for item in plan:
        shutil.copy2(item["source"], item["destination"])
        print(f"staged {stage} {item['kind']}: {item['destination']}")

    if str(stage) == "active":
        active_dir.mkdir(parents=True, exist_ok=True)
        for item in root_plan:
            shutil.copy2(item["source"], item["destination"])
            print(f"promoted active {item['kind']}: {item['destination']}")

    manifest_out.write_text(json.dumps(active_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {manifest_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
