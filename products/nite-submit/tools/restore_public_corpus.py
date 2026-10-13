#!/usr/bin/env python3
"""Restore public QA PDFs only when they match the recorded provenance hash.

Run from any directory. Failed or changed sources are reported without replacing
local files. This restores source bytes, not reviewed extraction truth.
"""

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.request


PRODUCT_DIR = Path(__file__).resolve().parent.parent
SOURCE_MANIFESTS = (
    "NITE_SUBMIT_REAL_CORPUS_MANIFEST_V1.json",
    "NITE_SUBMIT_CORPUS_WAVE2_MANIFEST_V1.json",
    "NITE_SUBMIT_CORPUS_WAVE3_MANIFEST_V1.json",
)
LICENSES = {
    "INSTITUTIONALLY_PUBLISHED_PUBLIC_DOCUMENT",
    "TEMPLATE_FOR_PUBLIC_USE",
    "PUBLIC_REPOSITORY_RESEARCH_DOCUMENT",
    "OPEN_LICENSE",
}
MAX_BYTES = 64 * 1024 * 1024  # 64 MiB bounds a changed or misdirected source.


def source_path(row, corpus):
    """Resolve a provenance filename strictly inside the ignored corpus."""
    name = row.get("local_filename") or row["file"]
    name = name.removeprefix("real_validation_corpus/")
    relative = Path(name)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        # A manifest must never choose a destination outside the QA workspace.
        raise ValueError("Source filename must be relative without parent traversal")
    if relative.parts[0] in {"beta_intake", "test_results", "rejected", "manifests"}:
        # Public recovery must not overwrite private intake or generated results.
        raise ValueError("Source filename uses a reserved corpus directory")
    target = corpus / relative
    if not target.resolve().is_relative_to(corpus.resolve()):
        # Existing symlinks cannot redirect public downloads into another folder.
        raise ValueError("Source filename resolves outside the corpus")
    return target


def digest(path):
    """Hash without loading an entire dissertation into memory."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def restore(row, corpus, *, check=False, opener=urllib.request.urlopen):
    """Verify one existing PDF or install its hash-matching public source."""
    license_class = row.get("licence_status") or row.get("licence_class")
    if license_class not in LICENSES or row.get("qualification_eligible") is False:
        # Unknown or rejected reuse status cannot enter the qualified collection.
        raise ValueError("Source is not approved for local public-document QA")
    expected = row["sha256"].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Source needs a complete SHA-256 provenance hash")
    target = source_path(row, corpus)
    if target.exists():
        # Never overwrite a local document, including a changed public source.
        if digest(target) != expected:
            raise ValueError("Existing file differs from recorded provenance")
        return "verified"
    if check:
        # Offline verification has no network side effects.
        raise ValueError("Source PDF is missing")

    # Three recorded URLs carry prose after the URL; that prose is not a URL.
    url = row["source_url"].split()[0]
    if not url.startswith(("https://", "http://")):
        raise ValueError("Only public HTTP source URLs can be recovered")
    request = urllib.request.Request(url, headers={"User-Agent": "NiteDSP-CorpusRecovery/1.0"})
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            with opener(request, timeout=30) as response:  # 30 seconds per read.
                total = 0
                while block := response.read(1024 * 1024):  # 1 MiB chunks.
                    total += len(block)
                    if total > MAX_BYTES:
                        raise ValueError("Source exceeds the 64 MiB recovery limit")
                    output.write(block)
        with temporary.open("rb") as source:
            if source.read(5) != b"%PDF-":
                raise ValueError("Source response is not a PDF")
        if digest(temporary) != expected:
            raise ValueError("Downloaded PDF differs from recorded provenance")
        temporary.replace(target)
        return "restored"
    finally:
        # Network errors and hash drift leave no partial PDF in the corpus.
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify locally without downloading")
    parser.add_argument("--source-manifest", action="append", type=Path, default=[],
                        help="Additional reviewed provenance JSON, kept outside Git")
    args = parser.parse_args()
    manifests = [PRODUCT_DIR / "docs" / name for name in SOURCE_MANIFESTS]
    manifests.extend(args.source_manifest)
    rows = [row for manifest in manifests
            for row in json.loads(manifest.read_text())["documents"]]
    corpus = PRODUCT_DIR / "real_validation_corpus"
    results = []

    def recover(row):
        identifier = row.get("document_id") or Path(row["file"]).stem
        try:
            status = restore(row, corpus, check=args.check)
            return {"id": identifier, "status": status}
        except Exception as error:
            # Finish independent sources so one retired URL cannot hide others.
            return {"id": identifier, "status": "blocked", "reason": str(error)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(recover, rows):
            results.append(result)
            print(f"{result['id']}: {result['status']} {result.get('reason', '')}", flush=True)
    report = corpus / "manifests" / "recovery_results.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"results": results}, indent=2) + "\n")
    failed = sum(row["status"] == "blocked" for row in results)
    print(f"public_sources={len(rows)} verified_or_restored={len(rows) - failed} blocked={failed}")
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
