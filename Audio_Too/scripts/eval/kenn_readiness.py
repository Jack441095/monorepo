#!/usr/bin/env python3
"""Report whether KENN has the core files and services needed for demos/training."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
KENN = ROOT / "studio" / "kenn" / "kenn"
INDEX_DIR = KENN / "data" / "index"
CHUNKS_PATH = INDEX_DIR / "chunks.jsonl"
TERMS_PATH = INDEX_DIR / "terms.json"
NOTES_DIR = KENN / "Training_Data_Notes"
PDF_DIR = KENN / "Training_Data_PDF"
EVAL_SUITE = KENN / "evals" / "questions.json"
TRAINING_DIR = KENN / "artifacts" / "training"
AUDITS_DIR = KENN / "artifacts" / "audits"
sys.path.insert(0, str(ROOT / "studio" / "kenn"))


def count_jsonl(path: Path) -> tuple[int, int]:
    rows = 0
    bad = 0
    if not path.exists():
        return rows, bad
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
            rows += 1
        except json.JSONDecodeError:
            bad += 1
    return rows, bad


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, int(port))) == 0


def latest_json(directory: Path, pattern: str = "*.json") -> Path | None:
    if not directory.exists():
        return None
    files = [path for path in directory.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def eval_case_count(path: Path | None = None) -> int:
    data = load_json(path or EVAL_SUITE)
    cases = data.get("cases")
    return len(cases) if isinstance(cases, list) else 0


def held_out_eval_case_count() -> int:
    names = ("questions.json", "conversation_cases.json", "knowledge_upgrade_cases.json", "internet_source_cases.json")
    return sum(eval_case_count(KENN / "evals" / name) for name in names)


def repair_training_summary(training_dir: Path | None = None) -> dict[str, Any]:
    root = training_dir or TRAINING_DIR
    raw = root / "creative_lab_repair_records.jsonl"
    reviews = root / "creative_lab_repair_reviews.json"
    approved = root / "creative_lab_repair_records.approved.jsonl"
    manifest = root / "creative_lab_repair_records.approved.manifest.json"

    raw_rows, raw_bad = count_jsonl(raw)
    approved_rows, approved_bad = count_jsonl(approved)
    reviews_data = load_json(reviews)
    review_map = reviews_data.get("reviews") if isinstance(reviews_data.get("reviews"), dict) else {}
    review_counts: dict[str, int] = {}
    for review in review_map.values() if isinstance(review_map, dict) else []:
        decision = str(review.get("decision") if isinstance(review, dict) else "unknown") or "unknown"
        review_counts[decision] = review_counts.get(decision, 0) + 1

    manifest_data = load_json(manifest)
    manifest_selected = manifest_data.get("selected_records")
    manifest_ok = bool(
        manifest_data
        and manifest_data.get("schema") == "kenn.creative_repair_dataset_manifest.v1"
        and manifest_selected == approved_rows
    )
    return {
        "raw_records": raw_rows,
        "raw_bad_rows": raw_bad,
        "review_counts": review_counts,
        "approved_records": approved_rows,
        "approved_bad_rows": approved_bad,
        "manifest_ok": manifest_ok,
        "manifest_selected_records": manifest_selected,
    }


def index_summary() -> dict[str, Any]:
    from kenn.retrieval.index_store import active_version_dir

    version_dir = active_version_dir(INDEX_DIR)
    chunks_path = version_dir / "chunks.jsonl" if version_dir else CHUNKS_PATH
    terms_path = version_dir / "terms.json" if version_dir else TERMS_PATH
    manifest = load_json(version_dir / "manifest.json") if version_dir else {}
    chunk_rows = count_lines(chunks_path)
    terms = load_json(terms_path)
    total_docs = int(terms.get("total_docs") or 0)
    version = terms.get("version")
    return {
        "chunks_exists": chunks_path.exists(),
        "terms_exists": terms_path.exists(),
        "chunks": chunk_rows,
        "terms_total_docs": total_docs,
        "terms_version": version,
        "counts_match": bool(chunk_rows and total_docs and chunk_rows == total_docs),
        "storage": "versioned" if version_dir else "legacy",
        "active_version": version_dir.name if version_dir else "",
        "content_sha256": str(manifest.get("content_sha256") or ""),
        "embedding_dimensions": int(manifest.get("embedding_dimensions") or 0),
        "manifest_valid": bool(version_dir),
        "manifest_schema_version": int(manifest.get("schema_version") or 0),
        "build_metadata": manifest.get("build") if isinstance(manifest.get("build"), dict) else {},
    }


def source_summary() -> dict[str, int]:
    note_paths = list(NOTES_DIR.glob("*.md")) if NOTES_DIR.exists() else []
    notes = len(note_paths)
    approved_notes = sum(
        1
        for path in note_paths
        if any(
            line.strip().lower() == "status: approved"
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:20]
        )
    )
    pdfs = len(list(PDF_DIR.glob("*.pdf"))) if PDF_DIR.exists() else 0
    catalog = load_json(KENN / "Training_Data_Sources" / "pdf_sources.json")
    if not catalog:
        try:
            loaded = json.loads((KENN / "Training_Data_Sources" / "pdf_sources.json").read_text(encoding="utf-8"))
            catalog_rows = loaded if isinstance(loaded, list) else []
        except (OSError, json.JSONDecodeError):
            catalog_rows = []
    else:
        catalog_rows = []
    reference_only_pdfs = sum(
        1
        for row in catalog_rows
        if row.get("filename")
        and (PDF_DIR / str(row["filename"])).exists()
        and str(row.get("index_policy", "index")).lower() == "reference_only"
    )
    transcripts = len(list((KENN / "Training_Data_Transcripts").glob("*.txt")))
    return {
        "notes": notes,
        "approved_notes": approved_notes,
        "pdfs": pdfs,
        "reference_only_pdfs": reference_only_pdfs,
        "transcripts": transcripts,
        "eval_cases": eval_case_count(),
        "held_out_eval_cases": held_out_eval_case_count(),
    }


def audit_summary() -> dict[str, Any]:
    latest = latest_json(AUDITS_DIR, "ableton_audit_*.json")
    if latest is None:
        return {"latest": "", "status": "missing"}
    data = load_json(latest)
    return {
        "latest": str(latest.relative_to(ROOT)),
        "status": str(data.get("status") or "unknown"),
        "mtime": latest.stat().st_mtime,
    }


def build_report() -> dict[str, Any]:
    services = {"website_8080": port_open(8080), "kenn_8090": port_open(8090)}
    index = index_summary()
    sources = source_summary()
    repair = repair_training_summary()
    audit = audit_summary()
    issues: list[str] = []
    warnings: list[str] = []

    if not index["chunks_exists"] or not index["terms_exists"]:
        issues.append("KENN index is missing; run ./ableton build.")
    elif not index["counts_match"]:
        issues.append("KENN index chunk and term counts do not match; rebuild the index.")
    if sources["eval_cases"] <= 0:
        issues.append("KENN eval suite has no cases.")
    if repair["raw_bad_rows"] or repair["approved_bad_rows"]:
        issues.append("Repair-training JSONL contains invalid rows.")
    if repair["approved_records"] and not repair["manifest_ok"]:
        issues.append("Repair-training approved manifest is missing or out of sync.")
    if not services["kenn_8090"]:
        warnings.append("KENN service is offline on :8090; run ./audio-too start --no-open before demos.")
    if not services["website_8080"]:
        warnings.append("Website service is offline on :8080; run ./audio-too start --no-open before demos.")
    if audit["status"] == "missing":
        warnings.append("No KENN audit artifact found; run ./audio-too audit when you want a fresh quality baseline.")

    status = "ready" if not issues and services["kenn_8090"] else "needs_attention"
    return {
        "status": status,
        "services": services,
        "sources": sources,
        "index": index,
        "repair_training": repair,
        "latest_audit": audit,
        "issues": issues,
        "warnings": warnings,
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"KENN readiness: {report['status']}")
    services = report["services"]
    print(f"Services: Website :8080 {'online' if services['website_8080'] else 'offline'}; KENN :8090 {'online' if services['kenn_8090'] else 'offline'}")
    sources = report["sources"]
    print(
        "Sources: "
        f"{sources['approved_notes']}/{sources['notes']} approved notes, {sources['pdfs']} PDFs "
        f"({sources['reference_only_pdfs']} reference-only), "
        f"{sources['transcripts']} transcripts, {sources['held_out_eval_cases']} held-out eval cases"
    )
    index = report["index"]
    print(
        "Index: "
        f"{index['chunks']} chunks, terms docs {index['terms_total_docs']}, "
        f"version {index['active_version'] or index['terms_version'] or 'unknown'}, "
        f"{index['embedding_dimensions']} embedding dimensions"
    )
    repair = report["repair_training"]
    print(
        "Repair training: "
        f"{repair['raw_records']} raw, {repair['approved_records']} approved, "
        f"reviews {json.dumps(repair['review_counts'], sort_keys=True)}, "
        f"manifest {'ok' if repair['manifest_ok'] else 'not ready'}"
    )
    audit = report["latest_audit"]
    print(f"Latest audit: {audit.get('status', 'unknown')} {audit.get('latest', '')}".rstrip())
    for issue in report["issues"]:
        print(f"ISSUE: {issue}")
    for warning in report["warnings"]:
        print(f"WARN: {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show KENN readiness for demos, evals, and future Torch work.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero for warnings as well as issues.")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_report(report)
    if report["issues"] or (args.strict and report["warnings"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
