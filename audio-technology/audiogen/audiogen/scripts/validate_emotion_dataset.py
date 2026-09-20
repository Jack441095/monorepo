#!/usr/bin/env python3
"""Validate structured emotion dataset exports."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _fail(message: str, errors: List[str]) -> None:
    errors.append(str(message))


def _load_json(path: Path, errors: List[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _fail(f"{path}: failed to parse JSON: {exc}", errors)
        return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_schema_path(dataset_dir: Path, raw: str) -> Path:
    p = Path(str(raw))
    if p.is_absolute():
        return p
    candidate = dataset_dir / p
    if candidate.is_file():
        return candidate
    return _repo_root() / p


def _load_schemas(dataset_dir: Path, errors: List[str]) -> Dict[str, Dict[str, Any]]:
    manifest_path = dataset_dir / "manifest.json"
    schemas = {
        "emotion_profiles": _repo_root() / "data/datasets/schemas/emotion_profile.schema.json",
        "harmony_progressions": _repo_root() / "data/datasets/schemas/harmony_progression.schema.json",
    }
    if manifest_path.is_file():
        manifest = _load_json(manifest_path, errors)
        if isinstance(manifest, dict):
            raw_schemas = manifest.get("schemas")
            if isinstance(raw_schemas, dict):
                for key in ("emotion_profiles", "harmony_progressions"):
                    if raw_schemas.get(key):
                        schemas[key] = _resolve_schema_path(dataset_dir, str(raw_schemas[key]))
    out: Dict[str, Dict[str, Any]] = {}
    for key, path in schemas.items():
        payload = _load_json(Path(path), errors)
        if isinstance(payload, dict):
            out[key] = payload
        else:
            _fail(f"{path}: schema must be an object", errors)
    return out


def _validate_schema(row: Dict[str, Any], schema: Dict[str, Any], where: str, errors: List[str]) -> None:
    required = list(schema.get("required") or [])
    props = dict(schema.get("properties") or {})
    for key in required:
        if key not in row:
            _fail(f"{where}: missing required key {key!r}", errors)
    for key, spec in props.items():
        if key not in row:
            continue
        if not isinstance(spec, dict):
            continue
        value = row.get(key)
        typ = str(spec.get("type") or "")
        if typ == "string":
            if not isinstance(value, str):
                _fail(f"{where}: {key} must be string", errors)
                continue
            if int(spec.get("min_length", 0) or 0) > 0 and len(value.strip()) < int(spec.get("min_length")):
                _fail(f"{where}: {key} is too short", errors)
        elif typ == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                _fail(f"{where}: {key} must be int", errors)
                continue
            if "min" in spec and int(value) < int(spec["min"]):
                _fail(f"{where}: {key} below min {spec['min']}", errors)
            if "max" in spec and int(value) > int(spec["max"]):
                _fail(f"{where}: {key} above max {spec['max']}", errors)
        elif typ == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                _fail(f"{where}: {key} must be number", errors)
                continue
            if "min" in spec and float(value) < float(spec["min"]):
                _fail(f"{where}: {key} below min {spec['min']}", errors)
            if "max" in spec and float(value) > float(spec["max"]):
                _fail(f"{where}: {key} above max {spec['max']}", errors)
        elif typ == "enum":
            values = set(str(v) for v in list(spec.get("values") or []))
            if str(value) not in values:
                _fail(f"{where}: {key} must be one of {sorted(values)}", errors)
        elif typ == "list":
            if not isinstance(value, list):
                _fail(f"{where}: {key} must be list", errors)
                continue
            min_len = int(spec.get("min_length", 0) or 0)
            if len(value) < min_len:
                _fail(f"{where}: {key} length {len(value)} < {min_len}", errors)
            item_type = str(spec.get("item_type") or "")
            for item in value:
                if item_type == "int":
                    if not isinstance(item, int) or isinstance(item, bool):
                        _fail(f"{where}: {key} item {item!r} must be int", errors)
                        continue
                    if "item_min" in spec and int(item) < int(spec["item_min"]):
                        _fail(f"{where}: {key} item {item!r} below min", errors)
                    if "item_max" in spec and int(item) > int(spec["item_max"]):
                        _fail(f"{where}: {key} item {item!r} above max", errors)
                elif item_type == "string":
                    if not isinstance(item, str):
                        _fail(f"{where}: {key} item must be string", errors)
                        continue
                    min_item_len = int(spec.get("item_min_length", 0) or 0)
                    if min_item_len > 0 and len(item.strip()) < min_item_len:
                        _fail(f"{where}: {key} contains empty string item", errors)


def _validate_profile(row: Dict[str, Any], idx: int, schema: Dict[str, Any], errors: List[str]) -> None:
    where = f"emotion_profiles[{idx}]"
    _validate_schema(row, schema, where, errors)
    emotion = str(row.get("emotion") or "").strip()
    if not emotion:
        _fail(f"{where}: missing emotion", errors)
    scale = row.get("scale_intervals")
    if not isinstance(scale, list) or not scale:
        _fail(f"{where}: scale_intervals must be a non-empty list", errors)
    else:
        for v in scale:
            if not isinstance(v, int) or v < 0 or v > 11:
                _fail(f"{where}: invalid scale interval {v!r}", errors)
    for key in ("tempo_multiplier", "velocity_multiplier", "density"):
        try:
            float(row.get(key))
        except Exception:
            _fail(f"{where}: {key} must be numeric", errors)


def _validate_progression(
    row: Dict[str, Any],
    idx: int,
    known_emotions: set[str],
    schema: Dict[str, Any],
    errors: List[str],
) -> None:
    where = f"harmony_progressions[{idx}]"
    _validate_schema(row, schema, where, errors)
    emotion = str(row.get("emotion") or "").strip()
    if not emotion:
        _fail(f"{where}: missing emotion", errors)
    elif emotion not in known_emotions:
        _fail(f"{where}: unknown emotion {emotion!r}", errors)
    kind = str(row.get("kind") or "").strip()
    if kind not in {"progression", "cadence", "arrangement"}:
        _fail(f"{where}: invalid kind {kind!r}", errors)
    progression = row.get("progression")
    if not isinstance(progression, list) or len(progression) < 2:
        _fail(f"{where}: progression must contain at least two chords", errors)
    else:
        for ch in progression:
            if not str(ch or "").strip():
                _fail(f"{where}: empty chord symbol", errors)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "dataset_dir",
        nargs="?",
        default="data/datasets/emotions/v1",
        help="Directory containing emotion_profiles.json and harmony_progressions.jsonl.",
    )
    ap.add_argument(
        "--report",
        default=None,
        help="Optional path to write validation/audit report JSON.",
    )
    args = ap.parse_args()

    root = Path(str(args.dataset_dir))
    profile_path = root / "emotion_profiles.json"
    progression_path = root / "harmony_progressions.jsonl"
    errors: List[str] = []
    schemas = _load_schemas(root, errors)

    if not profile_path.is_file():
        _fail(f"missing {profile_path}", errors)
    if not progression_path.is_file():
        _fail(f"missing {progression_path}", errors)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 2

    profiles = _load_json(profile_path, errors)
    if not isinstance(profiles, list):
        _fail(f"{profile_path}: expected list", errors)
        profiles = []
    known_emotions: set[str] = set()
    profile_schema = schemas.get("emotion_profiles", {})
    for idx, row in enumerate(profiles):
        if not isinstance(row, dict):
            _fail(f"emotion_profiles[{idx}]: expected object", errors)
            continue
        _validate_profile(row, idx, profile_schema, errors)
        emotion = str(row.get("emotion") or "").strip()
        if emotion:
            if emotion in known_emotions:
                _fail(f"emotion_profiles[{idx}]: duplicate emotion {emotion!r}", errors)
            known_emotions.add(emotion)

    progression_count = 0
    kind_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    emotion_progression_counts: Counter[str] = Counter()
    progression_schema = schemas.get("harmony_progressions", {})
    with progression_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                _fail(f"harmony_progressions[{idx}]: invalid JSON: {exc}", errors)
                continue
            if not isinstance(row, dict):
                _fail(f"harmony_progressions[{idx}]: expected object", errors)
                continue
            _validate_progression(row, idx, known_emotions, progression_schema, errors)
            progression_count += 1
            kind_counts[str(row.get("kind") or "")] += 1
            role_counts[str(row.get("section_role") or "")] += 1
            emotion_progression_counts[str(row.get("emotion") or "")] += 1

    if progression_count <= 0:
        _fail("harmony_progressions: no rows", errors)
    missing_progressions = sorted(e for e in known_emotions if emotion_progression_counts.get(e, 0) <= 0)
    if missing_progressions:
        _fail(f"emotions without progressions: {missing_progressions}", errors)

    report = {
        "schema_version": 1,
        "dataset_dir": str(root),
        "emotion_count": len(known_emotions),
        "progression_rows": int(progression_count),
        "kind_counts": dict(sorted(kind_counts.items())),
        "section_role_counts": dict(sorted(role_counts.items())),
        "emotion_progression_counts": dict(sorted(emotion_progression_counts.items())),
        "errors": list(errors),
    }
    if args.report:
        out = Path(str(args.report))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"FAIL errors={len(errors)}", file=sys.stderr)
        return 2
    print(f"PASS emotions={len(known_emotions)} progression_rows={progression_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
