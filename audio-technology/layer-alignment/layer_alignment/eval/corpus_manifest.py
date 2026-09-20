"""Corpus manifest tooling — deterministic, provenance-first.

Real-audio corpus lives under real_audio_import/ (gitignored; only
manifests + hashes are committed). Original files are NEVER moved,
renamed or modified: manifests reference them in place by sha256.

Licence categories are explicit strings chosen by the OWNER at import:
  owner_authorised | licensed_pack | public_domain | research_licensed
Anything else/missing => category UNVERIFIED and cases built from it are
excluded from qualification automatically.
"""
from __future__ import annotations

import hashlib
import json
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .audio_io import AudioLoadError, file_sha256, load_wav

ALLOWED_CATEGORIES = {"owner_authorised", "licensed_pack", "public_domain",
                      "research_licensed"}


def probe_wav(path: Path) -> dict:
    """Light read-only probe (no full decode)."""
    try:
        with wave.open(str(path), "rb") as w:
            return {"sample_rate": w.getframerate(),
                    "channels": w.getnchannels(),
                    "frames": w.getnframes(),
                    "bit_width": w.getsampwidth() * 8,
                    "duration_s": round(w.getnframes() / w.getframerate(), 3)}
    except Exception as e:                       # noqa: BLE001 — manifest must record bad files, not die
        return {"error": f"{type(e).__name__}: {e}"}


def scan_source_dir(source_dir: Path, licences: dict | None = None) -> list:
    """Read-only inventory of a source directory.

    licences: optional {relative_path_or_glob: category} hints supplied by
    the owner. Anything unmatched => UNVERIFIED.
    """
    entries = []
    for p in sorted(Path(source_dir).rglob("*")):
        if not p.is_file() or p.suffix.lower() != ".wav":
            continue
        cat = "UNVERIFIED"
        if licences:
            for pattern, c in licences.items():
                if p.match(pattern) or str(p).endswith(pattern):
                    cat = c
                    break
        info = {"path": str(p.relative_to(source_dir)),
                "sha256": file_sha256(p),
                "bytes": p.stat().st_size,
                "licence_category": cat}
        info.update(probe_wav(p))
        entries.append(info)
    return entries


def build_manifest(source_dirs: dict, out_path: Path,
                   corpus_id: str) -> dict:
    """source_dirs: {group_name: {dir: Path, licences: {...}, role: str}}"""
    groups = {}
    for group, spec in source_dirs.items():
        entries = scan_source_dir(spec["dir"], spec.get("licences"))
        verified = sum(1 for e in entries
                       if e["licence_category"] in ALLOWED_CATEGORIES)
        groups[group] = {"role": spec.get("role", "unspecified"),
                         "root": str(spec["dir"]),
                         "files": len(entries),
                         "files_verified": verified,
                         "entries": entries}
    manifest = {
        "corpus_id": corpus_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "licence_categories_allowed": sorted(ALLOWED_CATEGORIES),
        "groups": groups,
        "note": ("originals referenced in place, read-only; this manifest "
                 "is committed, the audio is not"),
    }
    blob = json.dumps(manifest, sort_keys=True).encode()
    manifest["manifest_sha256"] = hashlib.sha256(blob).hexdigest()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=1))
    return manifest


def load_verified(path: Path, licence_category: str):
    """Load audio only if its provenance is qualified for R&D use."""
    if licence_category not in ALLOWED_CATEGORIES:
        raise AudioLoadError("UNVERIFIED_LICENCE", path.name)
    return load_wav(path)
