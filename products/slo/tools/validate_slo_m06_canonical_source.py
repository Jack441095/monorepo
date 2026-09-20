#!/usr/bin/env python3
"""Fail-closed validator for the SLO M-06 canonical-source candidate."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


SOURCE_SHA = "68b67009dc25bd9424d0c7cdbc11d2a7ce487c2f"
SOURCE_BRANCH = "engineering/slo-m06-canonical-source-v1"


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def validate(manifest_path: Path, source_worktree: Path | None = None) -> list[str]:
    errors: list[str] = []
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        return [f"cannot parse manifest: {exc}"]
    if document.get("schema_version") != "slo_canonical_source_migration_readiness_v1":
        errors.append("unexpected schema_version")
    if document.get("status") != "canonical_candidate_release_blocked":
        errors.append("candidate must remain release-blocked")
    candidate = document.get("candidate", {})
    if candidate.get("sha") != SOURCE_SHA or candidate.get("branch") != SOURCE_BRANCH:
        errors.append("candidate provenance drifted")
    controls = document.get("controls", {})
    for key in ("physical_migration_performed", "shared_checkout_modified", "unrelated_audio_too_code_imported", "protected_audio_or_data_opened", "models_or_holdouts_moved", "duplicate_platform_trees_retired", "release_authorized", "external_action_taken"):
        if controls.get(key) is not False:
            errors.append(f"controls.{key} must be false")
    if len(document.get("gates", [])) != 8:
        errors.append("expected eight M-06 gates")
    if source_worktree is not None:
        try:
            live_sha = _git(source_worktree, "rev-parse", "HEAD")
            if live_sha != SOURCE_SHA:
                ancestry = subprocess.run(
                    ["git", "-C", str(source_worktree), "merge-base", "--is-ancestor", SOURCE_SHA, live_sha],
                    check=False,
                )
                if ancestry.returncode != 0:
                    errors.append("live candidate no longer descends from the declared source checkpoint")
            if _git(source_worktree, "branch", "--show-current") != SOURCE_BRANCH:
                errors.append("live candidate branch drifted")
            if _git(source_worktree, "status", "--short"):
                errors.append("live candidate is dirty")
            if not (source_worktree / "SmartSampleManager/CMakeLists.txt").is_file():
                errors.append("SmartSampleManager/CMakeLists.txt missing")
            if not (source_worktree / "SLO_PRODUCT_TRUTH_MANIFEST_V1.json").is_file():
                errors.append("SLO product-truth manifest missing")
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"live candidate check failed: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parents[1] / "validation/audits/stage-6-migration-inventory-v1/slo_m06_canonical_source_readiness_v1.json")
    parser.add_argument("--source-worktree", type=Path)
    args = parser.parse_args()
    errors = validate(args.manifest, args.source_worktree)
    if errors:
        print("INVALID SLO M-06 canonical-source candidate")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALID SLO M-06 canonical-source candidate: 8 gates; release blocked; shared checkout preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
