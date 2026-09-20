#!/usr/bin/env python3
"""Build a non-destructive inventory of the dirty SLO beta worktree.

The output is evidence for positive-inclusion release assembly. It never moves,
deletes, stages, or edits inventoried files. Reviewable files are SHA-256
hashed; very large data is recorded by size and deliberately not read in full.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "_artifacts" / "slo_beta_source_inventory_20260915.json"
MAX_HASH_BYTES = 64 * 1024 * 1024


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def dirty_entries() -> list[tuple[str, str]]:
    fields = git("status", "--porcelain=v1", "-z", "-uall").split(b"\0")
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        text = record.decode("utf-8", errors="surrogateescape")
        status, path = text[:2], text[3:]
        if "R" in status or "C" in status:
            if index >= len(fields) or not fields[index]:
                raise RuntimeError(f"missing rename/copy destination for {path!r}")
            destination = fields[index].decode("utf-8", errors="surrogateescape")
            index += 1
            entries.append((status, destination))
        else:
            entries.append((status, path))
    return entries


def classify(path: str) -> str:
    suffix = Path(path).suffix.lower()
    name = Path(path).name.lower()
    lower_path = path.lower()

    if path.startswith("nitedsp/"):
        return "adjacent_platform_or_website"
    if path.startswith("_artifacts/"):
        return "generated_evidence_or_research_data"
    if lower_path.startswith("smartsamplemanager/source/test"):
        return "shipping_test"
    if path == "SmartSampleManager/tools/classification_benchmark/parity_references.json":
        # Runtime fixture for TestAcousticClassifierParity.  It must travel
        # with the shipping test even though it lives below the research tree.
        return "shipping_test"
    if path == "SmartSampleManager/Source/parity_references.json":
        # A duplicate export at this path is not consumed by the test binary.
        return "generated_evidence_or_research_data"
    if path.startswith("SmartSampleManager/Source/"):
        return "shipping_source_candidate"
    if path in {"SmartSampleManager/CMakeLists.txt", "SmartSampleManager/CMakePresets.json"}:
        return "build_configuration"
    if path.startswith("SmartSampleManager/Models/"):
        return "shipping_model_or_notice"
    if path.startswith("SmartSampleManager/scripts/"):
        return "release_or_qualification_tooling"
    if path == "tools/build_slo_beta_source_inventory.py":
        return "release_or_qualification_tooling"
    if path.startswith("SmartSampleManager/tools/"):
        if suffix in {".json", ".jsonl", ".csv", ".npz", ".npy", ".pt", ".pkl", ".log", ".sha256"}:
            return "generated_evidence_or_research_data"
        return "research_or_benchmark_tooling"
    if path.startswith("SmartSampleManager/docs/") or path.startswith("docs/"):
        return "product_or_engineering_documentation"
    if suffix in {".md", ".json"} and not "/" in path:
        return "product_plan_report_or_manifest"
    return "unclassified_review_required"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()

    rows: list[dict[str, object]] = []
    category_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    total_bytes = 0

    for status, relative in dirty_entries():
        file_path = ROOT / relative
        if file_path.resolve() == output:
            continue
        category = classify(relative)
        category_counts[category] += 1
        status_counts[status] += 1
        row: dict[str, object] = {
            "path": relative,
            "git_status": status,
            "category": category,
        }
        if file_path.is_file():
            size = file_path.stat().st_size
            total_bytes += size
            row["size_bytes"] = size
            if size <= MAX_HASH_BYTES:
                row["sha256"] = sha256(file_path)
                row["hash_status"] = "complete"
            else:
                row["sha256"] = None
                row["hash_status"] = "skipped_over_64_mib"
        elif file_path.is_dir():
            row["entry_type"] = "directory"
        else:
            row["entry_type"] = "missing_or_git_special"
        rows.append(row)

    document = {
        "schema_version": "slo.beta-source-inventory.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(ROOT),
        "branch": git("branch", "--show-current").decode().strip(),
        "head_sha": git("rev-parse", "HEAD").decode().strip(),
        "safety": {
            "read_only_inventory": True,
            "files_moved": False,
            "files_deleted": False,
            "files_staged": False,
            "large_file_hash_limit_bytes": MAX_HASH_BYTES,
            "output_self_excluded": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        },
        "summary": {
            "dirty_file_entries": len(rows),
            "tracked_modified_entries": sum(count for status, count in status_counts.items() if status != "??"),
            "untracked_file_entries": status_counts.get("??", 0),
            "total_inventory_bytes": total_bytes,
            "category_counts": dict(sorted(category_counts.items())),
            "git_status_counts": dict(sorted(status_counts.items())),
        },
        "entries": sorted(rows, key=lambda row: str(row["path"])),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], indent=2, sort_keys=True))
    print(f"inventory={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
