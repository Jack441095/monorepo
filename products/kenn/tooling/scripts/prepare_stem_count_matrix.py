#!/usr/bin/env python3
"""Prepare a deterministic, no-copy AutoMix stem-count matrix manifest.

The command records selected source paths and manifest hashes only. It never
copies or rewrites audio, which keeps private/third-party fixtures outside the
repository while making the exact 1/8/16/32/64-stem selection reproducible.
Use ``--require-rights-cleared`` for a fail-closed release qualification run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_COUNTS = (1, 8, 16, 32, 64)
DEFAULT_RIGHTS_CLEARED_LICENSES = frozenset(
    {
        "owned",
        "licensed",
        "public-domain",
        "public domain",
        "cc0",
        "cc-by",
        "cc-by-sa",
    }
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_matrix(
    manifest_path: Path,
    *,
    track: str,
    counts: tuple[int, ...] = DEFAULT_COUNTS,
    verify_files: bool = False,
    require_rights_cleared: bool = False,
    rights_cleared_licenses: frozenset[str] | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracks = manifest.get("tracks")
    if not isinstance(tracks, dict) or track not in tracks:
        available = sorted(tracks) if isinstance(tracks, dict) else []
        raise ValueError(f"track {track!r} is missing; available tracks: {available}")

    manifest_root = Path(manifest.get("root") or manifest_path.parent).expanduser()
    entries = [
        item
        for item in tracks[track]
        if isinstance(item, dict) and str(item.get("path", "")).lower().endswith(".wav")
    ]
    entries.sort(key=lambda item: str(item["path"]))
    if not entries:
        raise ValueError(f"track {track!r} contains no WAV entries")

    normalized_counts = tuple(sorted(set(int(count) for count in counts)))
    if any(count < 1 for count in normalized_counts):
        raise ValueError("stem counts must be positive")
    if any(count > len(entries) for count in normalized_counts):
        raise ValueError(
            f"track {track!r} has {len(entries)} WAV stems; requested {normalized_counts}"
        )

    allowed_licenses = (
        frozenset(str(value).strip().lower() for value in rights_cleared_licenses)
        if rights_cleared_licenses
        else DEFAULT_RIGHTS_CLEARED_LICENSES
    )
    unapproved = [
        (str(item["path"]), item.get("license"))
        for item in entries
        if str(item.get("license", "")).strip().lower() not in allowed_licenses
    ]
    if require_rights_cleared:
        if unapproved:
            examples = ", ".join(f"{path} ({license!r})" for path, license in unapproved[:3])
            suffix = "" if len(unapproved) <= 3 else f"; {len(unapproved) - 3} more"
            raise ValueError(
                "rights-cleared gate failed for "
                f"track {track!r}: {examples}{suffix}. "
                "Pass an explicit --rights-cleared-license value only after verifying "
                "the source terms."
            )

    matrix: list[dict[str, Any]] = []
    for count in normalized_counts:
        selected = entries[:count]
        files: list[dict[str, Any]] = []
        for item in selected:
            relative = Path(str(item["path"]))
            source_path = manifest_root / relative
            if verify_files:
                if not source_path.is_file():
                    raise FileNotFoundError(source_path)
                actual_hash = _sha256_file(source_path)
                if actual_hash != item.get("sha256"):
                    raise ValueError(
                        f"manifest hash mismatch for {source_path}: "
                        f"{actual_hash} != {item.get('sha256')}"
                    )
            files.append(
                {
                    "path": str(source_path),
                    "relative_path": str(relative),
                    "sha256": item.get("sha256"),
                    "size_bytes": item.get("size_bytes"),
                    "license": item.get("license"),
                }
            )
        matrix.append({"stem_count": count, "files": files})

    licenses = sorted(
        {str(item.get("license")) for item in entries if item.get("license") is not None}
    )
    return {
        "schema": "kenn.testing_assets.stem_count_matrix.v1",
        "manifest": str(manifest_path),
        "manifest_version": manifest.get("version"),
        "track": track,
        "available_wav_stems": len(entries),
        "requested_stem_counts": list(normalized_counts),
        "selection_policy": "lexicographic manifest path prefix; no audio copied",
        "source_license_statuses": licenses,
        "rights_cleared_required": require_rights_cleared,
        "rights_cleared": not unapproved,
        "files_verified": verify_files,
        "matrix": matrix,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--track", required=True)
    parser.add_argument("--count", type=int, action="append", dest="counts")
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument(
        "--verify-files",
        action="store_true",
        help="re-hash every selected source WAV before writing the manifest",
    )
    parser.add_argument(
        "--require-rights-cleared",
        action="store_true",
        help="fail unless every WAV entry has a verified license label",
    )
    parser.add_argument(
        "--rights-cleared-license",
        action="append",
        dest="rights_cleared_licenses",
        help="additional verified license label allowed by --require-rights-cleared (repeatable)",
    )
    args = parser.parse_args()
    counts = tuple(args.counts) if args.counts else DEFAULT_COUNTS
    result = prepare_matrix(
        args.manifest,
        track=args.track,
        counts=counts,
        verify_files=args.verify_files,
        require_rights_cleared=args.require_rights_cleared,
        rights_cleared_licenses=(
            frozenset(value.strip().lower() for value in args.rights_cleared_licenses)
            if args.rights_cleared_licenses
            else None
        ),
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"track": args.track, "counts": result["requested_stem_counts"], "out": str(args.json_out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
