#!/usr/bin/env python3
"""Build a non-mutating, evidence-backed rename plan.

This is the bridge between research classification and production action. It
evaluates the existing fusion classifier on a real folder, records filename
and physical-audio evidence separately, applies the measured decision policy,
resolves proposed-name collisions, and writes an immutable plan. It never
renames, moves, deletes, or copies audio.

An apply step is intentionally separate. A plan can be inspected, approved,
and then handed to a journaled filesystem executor.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(SD, "rename_plan_v1.jsonl")
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}

# Child processes load these once, rather than serialising sklearn models per
# file. The model is read-only during plan generation.
_CLF = None
_LOOP_CLF = None


def load_qualified(path):
    """Load an explicit, owner-reviewed auto-action class policy.

    The default is an empty set.  An empty policy is intentional: a model's
    internal action recommendation must not become a filesystem permission.
    JSON may contain a list or a ``qualified_classes``/``classes`` field;
    newline-delimited text is also accepted for convenient review packets.
    """
    if not path:
        return set()
    with open(path, encoding="utf-8") as handle:
        text = handle.read().strip()
    if not text:
        return set()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            value = value.get("qualified_classes") or value.get("classes") or []
        if not isinstance(value, list):
            raise ValueError("qualified-class policy must contain a list")
        return {str(item).strip() for item in value if str(item).strip()}
    except json.JSONDecodeError:
        return {line.strip() for line in text.splitlines() if line.strip()}


def load_class_thresholds(path):
    """Load optional per-class gates without granting any action permission.

    The file may be a ``{"thresholds": {"Kick": 0.8}}`` object or a plain
    class-to-number mapping.  Validation is deliberately strict: a malformed
    threshold aborts plan generation instead of silently falling back to a
    more permissive gate.
    """
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if isinstance(value, dict) and "thresholds" in value:
        value = value["thresholds"]
    if not isinstance(value, dict):
        raise ValueError("class-threshold policy must be an object")
    result = {}
    for cls, threshold in value.items():
        if not isinstance(cls, str) or not cls.strip():
            raise ValueError("class-threshold policy contains an invalid class")
        if not isinstance(threshold, (int, float)) or not 0.0 <= float(threshold) <= 1.0:
            raise ValueError(f"invalid threshold for {cls!r}: {threshold!r}")
        result[cls.strip()] = float(threshold)
    return result


def apply_qualification_gate(decision_row, qualified_classes, auto_enabled):
    """Turn an internal action recommendation into a product-safe action.

    ``decision_policy`` describes what the classifier believes, while this
    gate describes what the product is permitted to do.  Those are kept
    separate so a future policy file cannot silently grant auto-renaming.
    """
    if decision_row.get("action") != "auto_rename":
        return decision_row
    candidate = decision_row.get("displayed_label", "")
    if auto_enabled and candidate in qualified_classes:
        decision_row["requires_approval"] = False
        return decision_row
    decision_row = dict(decision_row)
    decision_row["candidate_action"] = "auto_rename"
    decision_row["action"] = "review"
    decision_row["displayed_label"] = candidate
    decision_row["requires_approval"] = True
    decision_row["reason"] = (
        "classifier proposed auto_rename, but the class is not in the "
        "explicit owner-qualified policy; routed to review"
    )
    return decision_row


def _init_worker():
    global _CLF, _LOOP_CLF
    import fusion_renamer as fr
    _CLF, _LOOP_CLF = fr.train(force=False)


def _signature(path):
    st = os.stat(path)
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(65536))
        if st.st_size > 131072:
            f.seek(-65536, os.SEEK_END)
            h.update(f.read(65536))
    return {"size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns),
            "edge_sha256": h.hexdigest()}


def _classify(path):
    import fusion_renamer as fr
    import name_detect as nd

    try:
        label, conf, source = fr.classify(path, _CLF, _LOOP_CLF)
        filename_class, token = nd.detect(os.path.basename(path))
        return {
            "path": os.path.abspath(path),
            "filename_class": filename_class or "",
            "filename_token": token or "",
            "audio_class": label or "",
            "audio_confidence": round(float(conf), 5),
            "audio_source": source,
            "signature": _signature(path),
            "error": "",
        }
    except Exception as exc:
        return {
            "path": os.path.abspath(path), "filename_class": "",
            "filename_token": "", "audio_class": "",
            "audio_confidence": 0.0, "audio_source": "error",
            "signature": {}, "error": str(exc)[:240],
        }


def collect(root):
    root = os.path.abspath(root)
    paths = []
    for dp, dn, files in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".")]
        for name in files:
            if name.startswith(".") or name.startswith("._"):
                continue
            path = os.path.join(dp, name)
            if os.path.islink(path) or os.path.splitext(name)[1].lower() not in AUDIO_EXTS:
                continue
            paths.append(path)
    return sorted(paths)


def safe_stem(label):
    value = " ".join(str(label).replace("/", "-").split())
    return "".join(c for c in value if c not in "\0\n\r<>:\"/\\|?*").strip() or "sample"


def reserve_destination(source, label, reserved):
    folder, name = os.path.split(source)
    stem, ext = os.path.splitext(name)
    desired = os.path.join(folder, f"{safe_stem(label)} - {stem}{ext}")
    candidate = desired
    suffix = 1
    while (candidate in reserved or
           (os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(source))):
        candidate = os.path.join(
            folder, f"{safe_stem(label)} - {stem}_{suffix:02d}{ext}")
        suffix += 1
    reserved.add(candidate)
    return candidate, candidate != desired


def decision(row, threshold, class_thresholds=None):
    from decision_policy import decide
    label = row["audio_class"] or "Other/none"
    d = decide(predicted_class=label,
               confidence=float(row["audio_confidence"]),
               path=row["path"],
               filename_class=row["filename_class"] or None,
               filename_confidence=0.0,
               audio_confidence=float(row["audio_confidence"]),
               threshold=threshold, class_thresholds=class_thresholds,
               arm="fusion_renamer",
               taxonomy_version="1.1.0")
    return d.as_dict()


def write_jsonl(path, header, rows):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".rename_plan_", suffix=".tmp",
                               dir=directory, text=True)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(header, sort_keys=True) + "\n")
            for row in rows:
                f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-conf", type=float, default=0.75)
    ap.add_argument("--name-only", action="store_true",
                    help="record filename evidence without decoding audio")
    ap.add_argument("--qualified-classes", default=None,
                    help="JSON or newline list of owner-qualified auto-action classes")
    ap.add_argument("--class-thresholds", default=None,
                    help="optional JSON object of measured per-class confidence gates")
    ap.add_argument("--enable-auto", action="store_true",
                    help="permit auto_rename only for classes in --qualified-classes")
    args = ap.parse_args()
    qualified_classes = load_qualified(args.qualified_classes)
    class_thresholds = load_class_thresholds(args.class_thresholds)
    if args.enable_auto and not qualified_classes:
        raise SystemExit("--enable-auto requires a non-empty --qualified-classes policy")
    paths = collect(args.root)
    if args.limit:
        paths = paths[:args.limit]
    print(f"planning {len(paths)} audio files under {os.path.abspath(args.root)}")
    print(f"policy gate: {args.min_conf:.2f}; {'filename-only' if args.name_only else 'fusion audio + filename'}")

    if args.name_only:
        import name_detect as nd
        rows = []
        for path in paths:
            fn, token = nd.detect(os.path.basename(path))
            rows.append({"path": path, "filename_class": fn or "",
                         "filename_token": token or "",
                         "audio_class": "", "audio_confidence": 0.0,
                         "audio_source": "not_run", "signature": _signature(path),
                         "error": ""})
    elif paths:
        with ProcessPoolExecutor(max_workers=max(1, args.workers),
                                 initializer=_init_worker) as pool:
            rows = list(pool.map(_classify, paths, chunksize=8))
    else:
        rows = []

    reserved = set()
    action_counts = {}
    collision_count = 0
    planned = []
    for row in rows:
        d = decision(row, args.min_conf, class_thresholds) if not args.name_only else {
            "action": "review", "displayed_label": "",
            "confidence": 0.0, "reason": "filename-only plan is advisory",
            "evidence": {"filename_class": row["filename_class"],
                         "filename_token": row["filename_token"]},
            "requires_approval": True, "subtype": "",
            "policy_version": "1.0.0", "taxonomy_version": "1.1.0"}
        d = apply_qualification_gate(d, qualified_classes, args.enable_auto)
        row["decision"] = d
        action = d["action"]
        action_counts[action] = action_counts.get(action, 0) + 1
        label = d.get("displayed_label", "")
        if action in {"auto_rename", "suggest"} and label:
            dest, collided = reserve_destination(row["path"], label, reserved)
            row["destination"] = dest
            row["collision_resolved"] = collided
            collision_count += int(collided)
        else:
            row["destination"] = ""
            row["collision_resolved"] = False
        row["approved"] = False
        row["applied"] = False
        planned.append(row)

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=os.path.join(SD, "..", "..", ".."),
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        commit = ""
    header = {
        "record_type": "slo_rename_plan",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_root": os.path.abspath(args.root),
        "n_files": len(planned),
        "min_confidence": args.min_conf,
        "mode": "filename-only" if args.name_only else "fusion_audio_filename",
        "model": "fusion_model.pkl" if not args.name_only else "none",
        "qualified_classes": sorted(qualified_classes),
        "class_thresholds": class_thresholds,
        "auto_enabled": bool(args.enable_auto),
        "git_commit": commit,
        "actions": action_counts,
        "collision_resolutions": collision_count,
        "safety": [
            "read-only plan generation; no audio path is mutated",
            "source edge signature recorded for apply-time identity check",
            "approval is false for every row by default",
            "auto_rename requires --enable-auto plus an explicit qualified-class policy",
            "destination preserves the source container extension",
        ],
    }
    write_jsonl(args.out, header, planned)
    print(f"wrote {args.out}")
    print("actions:", ", ".join(f"{k}={v}" for k, v in sorted(action_counts.items())))
    print(f"collision resolutions: {collision_count}")


if __name__ == "__main__":
    raise SystemExit(main())
