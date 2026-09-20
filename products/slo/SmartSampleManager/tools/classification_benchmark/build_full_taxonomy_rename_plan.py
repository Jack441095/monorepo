#!/usr/bin/env python3
"""Build an immutable full-taxonomy rename plan from review predictions.

The default is deliberately review-only. Auto-action requires both an explicit
qualified-class policy and ``--enable-auto``; it also refuses filename/audio
conflicts. The script never renames, moves, deletes, or copies source files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time


def signature(path):
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
        candidate = os.path.join(folder, f"{safe_stem(label)} - {stem}_{suffix:02d}{ext}")
        suffix += 1
    reserved.add(candidate)
    return candidate, candidate != desired


def load_predictions(path):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if rows and rows[0].get("record_type") and "path" not in rows[0]:
        rows = rows[1:]
    return rows


def load_qualified(path):
    if not path:
        return set()
    with open(path) as f:
        text = f.read().strip()
    if not text:
        return set()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            value = (value.get("classes") or value.get("qualified_classes") or
                     value.get("suggest_classes") or [])
        return {str(x) for x in value}
    except json.JSONDecodeError:
        return {line.strip() for line in text.splitlines() if line.strip()}


def load_thresholds(path):
    if not path or not path.lower().endswith(".json"):
        return {}
    try:
        with open(path) as f:
            value = json.load(f)
        return {str(k): float(v) for k, v in
                (value.get("class_thresholds") or {}).items()}
    except (OSError, ValueError, TypeError):
        return {}


def passes_similarity_gate(value, threshold):
    """Return whether an optional calibrated similarity gate is satisfied."""
    if threshold is None:
        return True
    try:
        return float(value) >= float(threshold)
    except (TypeError, ValueError):
        return False


def write_jsonl(path, header, rows):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".full_taxonomy_plan_", suffix=".tmp",
                               dir=directory, text=True)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(header, sort_keys=True) + "\n")
            for row in rows:
                f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--qualified-classes", default=None,
                    help="JSON list/dict or newline list of classes that passed validation")
    ap.add_argument("--class-field", default="",
                    help="prediction field; defaults to fused_taxonomy_class when present")
    ap.add_argument("--enable-auto", action="store_true",
                    help="allow qualified, non-conflicting rows to be auto_rename")
    ap.add_argument("--suggest-classes", default=None,
                    help="JSON list/dict or newline list of classes allowed as suggestions")
    ap.add_argument("--enable-suggest", action="store_true",
                    help="emit reviewable suggestions for the supplied classes")
    ap.add_argument("--suggest-threshold", type=float, default=0.685,
                    help="confidence floor for suggestions")
    ap.add_argument("--threshold", type=float, default=0.827,
                    help="confidence floor for auto rows")
    ap.add_argument("--similarity-threshold", type=float, default=None,
                    help="optional cosine-similarity floor for actions")
    args = ap.parse_args()

    root = os.path.abspath(args.source_root)
    qualified = load_qualified(args.qualified_classes)
    suggest_classes = load_qualified(args.suggest_classes)
    suggest_thresholds = load_thresholds(args.suggest_classes)
    if args.enable_auto and not qualified:
        raise SystemExit("--enable-auto requires a non-empty --qualified-classes policy")
    if args.enable_suggest and not suggest_classes:
        raise SystemExit("--enable-suggest requires a non-empty --suggest-classes policy")

    predictions = load_predictions(args.predictions)
    class_field = args.class_field or (
        "fused_taxonomy_class" if any("fused_taxonomy_class" in p for p in predictions)
        else "full_taxonomy_class")
    confidence_field = (
        "fused_taxonomy_confidence" if class_field == "fused_taxonomy_class"
        else "full_taxonomy_confidence")

    reserved = set()
    rows = []
    action_counts = {"auto_rename": 0, "suggest": 0, "review": 0, "never_act": 0}
    for pred in predictions:
        path = os.path.abspath(str(pred["path"]))
        if not os.path.isfile(path):
            raise SystemExit(f"source missing: {path}")
        if os.path.commonpath([root, path]) != root:
            raise SystemExit(f"path outside source root: {path}")

        label = str(pred.get(class_field) or "Other/none")
        conf = float(pred.get(confidence_field, 0.0))
        similarity = pred.get("full_taxonomy_similarity", 0.0)
        similarity_ok = passes_similarity_gate(similarity, args.similarity_threshold)
        name_conflict = bool(pred.get("filename_class")) and (
            pred.get("filename_class") != label)
        accepted = bool(pred.get("accepted_at_calibrated_95"))
        action = "review"
        reason = "full-taxonomy precision not qualified for action"
        if label == "Other/none":
            action, reason = "never_act", "rejection class"
        elif (args.enable_auto and label in qualified and accepted and
              conf >= args.threshold and similarity_ok):
            if name_conflict:
                reason = "filename/audio disagreement"
            else:
                action, reason = "auto_rename", "qualified class and calibrated gate"
        elif args.enable_auto and label in qualified and accepted and conf >= args.threshold and not similarity_ok:
            reason = "similarity below calibrated action gate"
        elif (args.enable_suggest and label in suggest_classes and
              conf >= suggest_thresholds.get(label, args.suggest_threshold) and
              similarity_ok):
            action = "suggest"
            reason = "class passed new-domain suggestion receipt; approval required"
        elif (args.enable_suggest and label in suggest_classes and
              conf >= suggest_thresholds.get(label, args.suggest_threshold) and
              not similarity_ok):
            reason = "similarity below calibrated action gate"
        action_counts[action] += 1

        destination = ""
        collision = False
        if action in {"auto_rename", "suggest"}:
            destination, collision = reserve_destination(path, label, reserved)
        row = {
            "path": path,
            "full_taxonomy_class": label,
            "full_taxonomy_confidence": round(conf, 6),
            "full_taxonomy_similarity": pred.get("full_taxonomy_similarity", 0.0),
            "old_audio_class": pred.get("old_audio_class", ""),
            "old_audio_confidence": pred.get("old_audio_confidence", 0.0),
            "filename_class": pred.get("filename_class", ""),
            "accepted_at_calibrated_95": accepted,
            "decision": {
                "action": action,
                "displayed_label": label if action == "auto_rename" else "",
                "confidence": round(conf, 6),
                "reason": reason,
                "requires_approval": True,
                "policy_version": "full-taxonomy-1.0.0",
            },
            "destination": destination,
            "collision_resolved": collision,
            "signature": signature(path),
            "approved": False,
            "applied": False,
            "error": "",
        }
        rows.append(row)

    header = {
        # Keep the established plan envelope so the hardened validator/apply
        # and undo tools can consume this arm without a second mutation path.
        "record_type": "slo_rename_plan",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_root": root,
        "n_files": len(rows),
        "model": "full_taxonomy_model_v1.npz",
        "model_arm": "full_taxonomy_fusion_review" if class_field == "fused_taxonomy_class" else "full_taxonomy_review",
        "prediction_class_field": class_field,
        "qualified_classes": sorted(qualified),
        "suggest_classes": sorted(suggest_classes),
        "suggest_threshold": args.suggest_threshold,
        "suggest_thresholds": suggest_thresholds,
        "similarity_threshold": args.similarity_threshold,
        "auto_enabled": bool(args.enable_auto),
        "actions": action_counts,
        "collision_resolutions": sum(int(r["collision_resolved"]) for r in rows),
        "safety": [
            "review-only by default; auto requires explicit qualified classes",
            "source edge signature recorded before any apply step",
            "approval is false for every row",
            "no filesystem mutation is performed by this command",
        ],
    }
    write_jsonl(args.out, header, rows)
    print(f"wrote {args.out}: {len(rows)} rows")
    print("actions:", ", ".join(f"{k}={v}" for k, v in sorted(action_counts.items())))


if __name__ == "__main__":
    raise SystemExit(main())
