#!/usr/bin/env python3
"""Correction-log evaluation harness (A-04).

Turns SLO's append-only correction log (Source/CorrectionLog.h JSONL schema)
into a rolling, machine-readable evaluation set + CI gate.

Why this exists: the measurement in CorrectionLog.h is unambiguous -- by-ear
labels are the ONLY intervention that has ever improved SLO on unseen
libraries (+3.29pp accuracy, -17.9pp false-accept per 500). This harness makes
the log measurable per-commit instead of letting it accumulate unread.

Read-only on the log; only the receipt is written.

Usage:
    python3 correction_eval_harness.py --log corrections.jsonl
    python3 correction_eval_harness.py --log corrections.jsonl --samples-json model_view.json --gate
    python3 correction_eval_harness.py --gate --strict-taxonomy --receipt receipts/correction_eval_<date>.json

Exit codes: 0 = ran (gate passed when --gate), 1 = gate failed, 2 = input error.

Join mode (--samples-json): a JSON array of objects, each with at least
  {"content_hash": "...", "predicted_category": "..."} (confidence optional).
Computes end-to-end accuracy over the union set; corrections win per
content_hash (a by-ear label beats the model guess), remaining rows score the
model prediction against the user truth.
"""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Canonical taxonomy v2 (16 classes) + the honest escape hatch.
# Source of truth: products/slo/slo_class_metrics_v1.json .classes keys
# (verified 2026-09-18). "Unknown" is an accepted corrected target because the
# UI deliberately distinguishes "genuinely Unknown" from "never scanned"
# (Beta Blocker B-007 fix).
DEFAULT_TAXONOMY = frozenset({
    "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat", "Impact",
    "Kick", "Music Loop", "Percussion", "Riser", "Snare", "Synth",
    "Synth Loop", "Vocal Loop", "Vocal Phrase",
})
ESCAPE_TARGETS = frozenset({"Unknown"})

# Fields the C++ writer (CorrectionLog.h toJsonLine) emits. Unknown fields are
# tolerated but reported -- a forward-compatible parser never rejects new data.
REQUIRED_FIELDS = ("file_path", "original_category", "corrected_category")
KNOWN_FIELDS = frozenset({
    "ts", "file_path", "content_hash", "original_category",
    "original_subcategory", "original_evidence", "original_confidence",
    "corrected_category", "corrected_subcategory", "correction_type",
    "user_note", "taxonomy_version", "classifier_version", "policy_version",
    "status",
})

def iter_records(lines):
    """Yield (record_or_None, raw_line). Never raises on malformed JSON."""
    for raw in lines:
        line = raw.strip()
        if not line:
            yield None, raw
            continue
        try:
            yield json.loads(line), raw
        except json.JSONDecodeError:
            yield None, raw


def parse_log(path):
    """Read the append-only correction log. Crash-tolerant: a partial final
    line costs one record, never the file (mirrors the C++ writer's contract
    of append-only JSONL with no in-place rewrites)."""
    stats = {"records": 0, "malformed": 0, "blank": 0, "schema_warnings": 0}
    records, warnings = [], []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for rec, raw in iter_records(text.splitlines()):
        if rec is None:
            if raw.strip():
                stats["malformed"] += 1
            else:
                stats["blank"] += 1
            continue
        if not isinstance(rec, dict):
            stats["malformed"] += 1
            continue
        bad = [k for k in REQUIRED_FIELDS if not str(rec.get(k, "")).strip()]
        if bad:
            stats["schema_warnings"] += 1
            warnings.append({"reason": "missing_fields", "fields": bad,
                             "line": raw[:160]})
            continue
        unknown_fields = sorted(set(rec) - KNOWN_FIELDS)
        if unknown_fields:
            warnings.append({"reason": "unknown_fields", "fields": unknown_fields,
                             "line": raw[:160]})
        stats["records"] += 1
        records.append(rec)
    return records, stats, warnings


def dedupe(records):
    """Key = (content_hash, original_category, corrected_category); the LAST
    occurrence wins (a user may correct, revisit, re-correct). content_hash is
    the rename-stable identity; file_path is the documented fallback.
    Returns (deduped_records, n_collapsed)."""
    seen = {}
    for i, r in enumerate(records):
        key = (str(r.get("content_hash") or r.get("file_path")),
               str(r["original_category"]), str(r["corrected_category"]))
        seen[key] = (i, r)
    ordered = [r for _, r in sorted(seen.values(), key=lambda t: t[0])]
    return ordered, len(records) - len(ordered)


def identity_key(rec):
    """Rename-stable identity per the writer's contract: content_hash when
    present (survives a rename), else file_path."""
    h = str(rec.get("content_hash") or "").strip()
    return h if h else "path:" + str(rec["file_path"])


def _hist(values, edges=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)):
    """Bucket-label histogram; the top edge is inclusive (confidence 1.0 lands
    in 0.8-1.0, not nowhere)."""
    buckets = {f"{edges[i]:.1f}-{edges[i+1]:.1f}": 0 for i in range(len(edges) - 1)}
    last = len(edges) - 2
    for v in values:
        for i in range(len(edges) - 1):
            if edges[i] <= v <= edges[i + 1] + (1e-9 if i == last else 0.0):
                buckets[f"{edges[i]:.1f}-{edges[i+1]:.1f}"] += 1
                break
    return buckets


def summarize(records):
    """Aggregate the deduped correction set. The confidence histogram of the
    ORIGINAL model confidence is the cheapest calibration signal SLO has:
    corrections should concentrate at low confidence; a fat high-confidence
    bucket means the head is confidently wrong somewhere."""
    flips = defaultdict(Counter)
    evidence = Counter()
    types = Counter()
    conf_known, conf_unknown, conf_all = [], [], []
    versions = set()
    unknown_corrected = 0
    no_ops = 0

    per_hash = Counter(identity_key(r) for r in records)
    re_corrected = sum(1 for c in per_hash.values() if c > 1)

    for r in records:
        orig, corr = str(r["original_category"]), str(r["corrected_category"])
        flips[orig][corr] += 1
        evidence[str(r.get("original_evidence") or "unspecified")] += 1
        types[str(r.get("correction_type") or "label_correction")] += 1
        conf = r.get("original_confidence")
        if isinstance(conf, (int, float)) and not isinstance(conf, bool) \
                and 0.0 <= float(conf) <= 1.0:
            c = float(conf)
            conf_all.append(c)
            (conf_unknown if corr in ESCAPE_TARGETS else conf_known).append(c)
        versions.add((r.get("taxonomy_version"), r.get("classifier_version")))
        if corr in ESCAPE_TARGETS:
            unknown_corrected += 1
        if orig == corr:
            no_ops += 1

    lint = sorted({corr for orig in flips for corr in flips[orig]
                   if corr not in DEFAULT_TAXONOMY and corr not in ESCAPE_TARGETS})

    def mean(xs):
        return round(statistics.fmean(xs), 4) if xs else None

    return {
        "total_records": len(records),
        "unique_files": len(per_hash),
        "re_corrected_files": re_corrected,
        "no_op_corrections": no_ops,
        "unknown_escapes": unknown_corrected,
        "unknown_escape_pct": round(100.0 * unknown_corrected / len(records), 1) if records else 0.0,
        "flips": {k: dict(v) for k, v in sorted(flips.items())},
        "evidence_of_corrected": dict(evidence),
        "correction_types": dict(types),
        "confidence": {
            "count": len(conf_all),
            "mean": mean(conf_all),
            "stdev": round(statistics.pstdev(conf_all), 4) if len(conf_all) > 1 else None,
            "histogram": _hist(conf_all),
            "mean_when_corrected_to_known": mean(conf_known),
            "mean_when_corrected_to_unknown": mean(conf_unknown),
        },
        "version_pairs": sorted(([v[0], v[1]] for v in versions), key=lambda t: str(t)),
        "taxonomy_lint": lint,
    }


def end_to_end(records, samples):
    """Score the model against user truth over the UNION set.
    Corrections win per identity (content_hash, else file_path): a by-ear label
    beats the model's guess. Remaining rows are scored prediction-vs-truth."""
    truth = {identity_key(r): str(r["corrected_category"]) for r in records}
    by_key = defaultdict(list)
    for s in samples:
        if not isinstance(s, dict):
            continue
        h = str(s.get("content_hash") or "").strip()
        key = h if h else "path:" + str(s.get("file_path") or s.get("path") or "")
        by_key[key].append(s)
    scored = correct = 0
    misses = Counter()
    for key, rows in by_key.items():
        if key not in truth:
            continue
        scored += 1
        pred = rows[0].get("predicted_category")
        if str(pred) == truth[key]:
            correct += 1
        else:
            misses[str(pred)] += 1
    unmatched = len(truth) - scored
    return {
        "mode": "joined",
        "scored": scored,
        "correct": correct,
        "accuracy": round(correct / scored, 4) if scored else None,
        "corrections_without_matching_sample": max(unmatched, 0),
        "unmatched_samples": len(by_key) - scored,
        "misses_by_predicted": dict(misses),
    }


def evaluate_gates(summary, min_records, min_unique, max_unknown_pct, strict):
    """Gate philosophy mirrors clap_candidate_gate.py: explicit, named, with
    the observed-vs-threshold detail printed so a failure is actionable."""
    gates = []

    def add(name, ok, detail):
        gates.append({"gate": name, "ok": bool(ok), "detail": detail})

    add("min_records", summary["total_records"] >= min_records,
        f"{summary['total_records']} >= {min_records}")
    add("min_unique_files", summary["unique_files"] >= min_unique,
        f"{summary['unique_files']} >= {min_unique}")
    add("unknown_escape_ceiling", summary["unknown_escape_pct"] <= max_unknown_pct,
        f"{summary['unknown_escape_pct']}% <= {max_unknown_pct}%")
    add("no_no_op_noise", summary["no_op_corrections"] == 0,
        f"{summary['no_op_corrections']} no-op rows (writer filters these; nonzero means a foreign writer)")
    add("taxonomy_lint", (not strict) or not summary["taxonomy_lint"],
        f"strict={strict}, non_canonical_targets={summary['taxonomy_lint']}")
    return gates


def write_receipt(path, payload):
    p = Path(path)
    if p.parent and str(p.parent) not in ("", "."):
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default="corrections.jsonl",
                    help="append-only correction log (CorrectionLog.h JSONL)")
    ap.add_argument("--samples-json", default=None,
                    help="optional model-view JSON array for end-to-end scoring")
    ap.add_argument("--receipt", default=None, help="write a machine-readable JSON receipt")
    ap.add_argument("--gate", action="store_true", help="CI mode: exit 1 if any gate fails")
    ap.add_argument("--strict-taxonomy", action="store_true",
                    help="gate-fail on corrected targets outside the 16-class taxonomy")
    ap.add_argument("--min-records", type=int, default=20)
    ap.add_argument("--min-unique-files", type=int, default=10)
    ap.add_argument("--max-unknown-corrections-pct", type=float, default=35.0)
    args = ap.parse_args(argv)

    log_path = Path(args.log)
    if not log_path.is_file():
        print(f"ERROR: correction log not found: {log_path}", file=sys.stderr)
        return 2

    records, stats, warnings = parse_log(log_path)
    records, collapsed = dedupe(records)
    summary = summarize(records)
    summary["parser"] = {**stats, "dedup_collapsed": collapsed,
                         "warnings": warnings[:20],
                         "warnings_truncated": max(0, len(warnings) - 20)}

    joined = None
    if args.samples_json:
        try:
            samples = json.loads(Path(args.samples_json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: samples JSON unreadable: {exc}", file=sys.stderr)
            return 2
        if not isinstance(samples, list):
            print("ERROR: --samples-json must be a JSON array", file=sys.stderr)
            return 2
        joined = end_to_end(records, samples)
        summary["end_to_end"] = joined

    summary["gates"] = evaluate_gates(
        summary, args.min_records, args.min_unique_files,
        args.max_unknown_corrections_pct, args.strict_taxonomy)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.receipt:
        payload = dict(summary)
        payload["created_utc"] = datetime.now(timezone.utc).isoformat()
        payload["log_path"] = str(log_path)
        write_receipt(args.receipt, payload)
        print(f"receipt written: {args.receipt}")

    if args.gate:
        failed = [g for g in summary["gates"] if not g["ok"]]
        if failed:
            print("GATE FAILED: " + ", ".join(g["gate"] for g in failed), file=sys.stderr)
            return 1
        print("GATE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

