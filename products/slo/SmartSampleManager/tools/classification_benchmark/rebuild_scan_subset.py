#!/usr/bin/env python3
"""Rebuild the qualification scan subset from the authoritative manifest.

The V4-F/G/H qualification corpus (`fixtures/scan_subset`, 1,607 real-vendor
files) was derived from `dataset_manifest.json` by copying each source file to
a stable, prefixed name. When that derived tree is lost, the manifest plus the
declared source packs are still sufficient to rebuild a byte-identical corpus:
every entry records the `sha256` of its source audio, so a rebuild is
*verified* rather than assumed.

This is the missing capability that left the V4 closeout's Vocal-family
measurement "PENDING BUILD" -- see
`docs/SLO_VOCAL_FIX_MEASUREMENT_2026-09-15.md` (the measurement this tool
unblocked) and `docs/SLO_VOCAL_DISAMBIGUATION_PROPOSAL.md`.

Safety properties:

* never writes to the source packs;
* never rewrites `dataset_manifest.json`;
* refuses to publish if any file fails hash verification;
* publishes atomically (staged, then moved into place);
* refuses to overwrite an existing subset unless `--force` is given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "dataset_manifest.json"
# `dataset_manifest.json` records local_relative_path as
# "fixtures/scan_subset/<filename>", i.e. relative to SmartSampleManager.
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parents[1] / "fixtures" / "scan_subset"
AUDIO_SUFFIXES = {".wav", ".aif", ".aiff", ".flac"}
# Fixture names carry a stable ordinal prefix: "0760_<original basename>".
PREFIX_PATTERN = re.compile(r"^\d+_")


def strip_manifest_prefix(filename: str) -> str:
    """Return the source-pack basename for a manifest fixture filename."""
    return PREFIX_PATTERN.sub("", filename)


def index_corpus(corpus_dir: Path) -> dict:
    """Map source basename -> list of absolute paths across the declared packs.

    Basenames are NOT unique across real sample packs (e.g. two packs both
    contain `EAST.wav`), so callers must disambiguate by content hash. See
    `plan_rebuild`.
    """
    index: dict = {}
    for root, _dirs, files in os.walk(corpus_dir):
        for name in files:
            if Path(name).suffix.lower() not in AUDIO_SUFFIXES:
                continue
            index.setdefault(name, []).append(os.path.join(root, name))
    for paths in index.values():
        paths.sort()
    return index


def plan_rebuild(entries, index):
    """Resolve every manifest entry to a source file, without copying.

    Ambiguous basenames are disambiguated by content hash against the
    manifest's recorded `sha256`; this is the same value that later verifies
    the copy, so a successful plan cannot depend on an unverified guess.
    """
    resolved, missing, disambiguated, unresolved_ambiguous = [], [], 0, []
    hash_cache: dict = {}

    def cached_hash(path):
        if path not in hash_cache:
            hash_cache[path] = sha256_of(path)
        return hash_cache[path]

    for entry in entries:
        original = strip_manifest_prefix(entry.get("filename", ""))
        candidates = index.get(original, [])
        expected = (entry.get("sha256") or "").strip().lower()

        chosen = None
        if len(candidates) == 1:
            chosen = candidates[0]
            if expected and cached_hash(chosen) != expected:
                # Single candidate with wrong content is a manifest/corpus skew.
                missing.append((entry.get("filename", ""), original))
                continue
        elif len(candidates) > 1:
            matching = [p for p in candidates if cached_hash(p) == expected]
            if len(matching) == 1:
                chosen = matching[0]
                disambiguated += 1
            else:
                unresolved_ambiguous.append(
                    {"filename": original, "candidates": candidates,
                     "matching": len(matching)}
                )
                missing.append((entry.get("filename", ""), original))
                continue

        if chosen is None:
            missing.append((entry.get("filename", ""), original))
            continue

        resolved.append(
            {
                "filename": entry["filename"],
                "source": chosen,
                "sha256": expected,
                "expected_subcategory": entry.get("expected_subcategory", ""),
            }
        )
    return resolved, missing, disambiguated, unresolved_ambiguous


def sha256_of(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rebuild(manifest_path, corpus_dir, output_dir, dry_run=False, force=False):
    """Rebuild the subset and return a receipt describing exactly what happened."""
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    index = index_corpus(Path(corpus_dir))
    resolved, missing, disambiguated, unresolved = plan_rebuild(entries, index)

    receipt = {
        "record_type": "slo_scan_subset_rebuild",
        "schema_version": "1.0.0",
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256_of(manifest_path),
        "corpus_dir": str(Path(corpus_dir).resolve()),
        "output_dir": str(output_dir.resolve()),
        "manifest_entries": len(entries),
        "corpus_audio_files": sum(len(v) for v in index.values()),
        "resolved": len(resolved),
        "missing": len(missing),
        "missing_samples": [name for name, _ in missing[:20]],
        "disambiguated_by_hash": disambiguated,
        "unresolved_ambiguous": unresolved[:20],
        "dry_run": bool(dry_run),
        "verified": 0,
        "hash_mismatches": [],
        "bytes_written": 0,
        "policy": {
            "source_packs_modified": False,
            "manifest_rewritten": False,
            "publishes_only_verified_files": True,
        },
    }

    if missing:
        raise RuntimeError(
            f"cannot rebuild: {len(missing)} manifest entries unresolved in the "
            f"source packs; first: {receipt['missing_samples'][:3]}"
        )
    if dry_run:
        return receipt
    if output_dir.exists() and not force:
        raise RuntimeError(
            f"refusing to overwrite existing subset without --force: {output_dir}"
        )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".scan_subset.stage-",
                                    dir=str(output_dir.parent)))
    backup = None
    try:
        for item in resolved:
            destination = staging / item["filename"]
            shutil.copyfile(item["source"], destination)
            actual = sha256_of(destination)
            if item["sha256"] and actual != item["sha256"]:
                receipt["hash_mismatches"].append(item["filename"])
                raise RuntimeError(
                    f"hash mismatch after copy: {item['filename']} "
                    f"(expected {item['sha256']}, got {actual})"
                )
            receipt["verified"] += 1
            receipt["bytes_written"] += destination.stat().st_size

        if output_dir.exists():
            backup = Path(tempfile.mkdtemp(prefix=".scan_subset.previous-",
                                           dir=str(output_dir.parent)))
            backup.rmdir()
            os.replace(output_dir, backup)
        os.replace(staging, output_dir)
    except BaseException:
        if staging.is_dir():
            shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and not output_dir.exists():
            os.replace(backup, output_dir)
        raise

    receipt["previous_subset_preserved_at"] = str(backup) if backup else None
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--corpus-dir", type=Path, required=True,
                        help="declared source packs (see prepare_subset.SOURCE_ROOT)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve and report the plan without copying")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing subset, preserving it as backup")
    args = parser.parse_args(argv)

    receipt = rebuild(args.manifest, args.corpus_dir, args.output_dir,
                      dry_run=args.dry_run, force=args.force)
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n",
                                    encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in
                      ("resolved", "missing", "verified", "bytes_written", "dry_run")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
