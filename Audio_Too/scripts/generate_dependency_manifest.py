#!/usr/bin/env python3
"""Generate an SBOM-style license manifest from the resolved *.lock.txt files.

Release checklist item (docs/RELEASE_CHECKLIST.md, "Product and supply-chain
review"): "Generate exact per-platform, hash-locked dependency artifacts and
an SBOM." The exact-version lock files themselves are produced by pip-compile
(requirements.lock.txt / requirements-dev.lock.txt / requirements-agents.lock.txt
-- regenerate with `pip-compile --output-file=<name>.lock.txt <name>.txt`,
matching the convention already established in
studio/audiogen/audiogen/requirements-dev.lock). This script reads those
locked, exact versions and records each package's declared license from
whatever's currently installed in this environment.

Scope limitation (see docs/audits/2026-07-19-dependency-manifest.md): this
records ONLY what's actually installed and importable in the environment this
script runs in. It is not a true multi-platform SBOM -- AudioGen's native
arm64 environment and any Linux CI runner have their own dependency sets not
captured here. Do not treat this as satisfying "per-platform" without
regenerating it in each supported environment.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOCK_FILES = [
    "requirements.lock.txt",
    "requirements-dev.lock.txt",
    "requirements-agents.lock.txt",
]

_PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)==([A-Za-z0-9.\-+!]+)\s*\\?\s*$")

# Short, unambiguous licenses that don't need a human to re-read the full text.
_KNOWN_PERMISSIVE = {
    "MIT License",
    "BSD License",
    "Apache Software License",
    "Apache-2.0",
    "MIT",
    "BSD-3-Clause",
    "BSD-2-Clause",
    "Python Software Foundation License",
    "ISC License (ISCL)",
    "The Unlicense (Unlicense)",
    "Historical Permission Notice and Disclaimer (HPND)",
}


def _parse_lock_file(path: Path) -> dict[str, str]:
    """Return {package_name_lowercase: pinned_version} from a pip-compile lock file."""
    pins: dict[str, str] = {}
    if not path.exists():
        return pins
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _PIN_RE.match(line)
        if m:
            pins[m.group(1).lower()] = m.group(2)
    return pins


def _license_info(package_name: str) -> dict[str, str]:
    """Best-effort license lookup via importlib.metadata for an installed package."""
    try:
        dist = md.distribution(package_name)
    except md.PackageNotFoundError:
        return {"status": "not_installed", "license": "", "classifiers": []}

    classifiers = [
        c.removeprefix("License :: ").strip()
        for c in (dist.metadata.get_all("Classifier") or [])
        if c.startswith("License")
    ]
    license_expression = dist.metadata.get("License-Expression") or ""
    raw_license = (dist.metadata.get("License") or "").strip()

    if license_expression:
        return {"status": "ok", "license": license_expression, "classifiers": classifiers}
    if classifiers:
        # OSI classifiers look like "OSI Approved :: MIT License" -- keep the
        # most specific (last) segment.
        best = classifiers[-1].split(" :: ")[-1].strip()
        status = "ok" if best in _KNOWN_PERMISSIVE or "OSI Approved" in classifiers[-1] else "review"
        return {"status": status, "license": best, "classifiers": classifiers}
    if raw_license and len(raw_license) < 80 and "\n" not in raw_license:
        # A short License field (not a dumped full license text) is usable directly.
        return {"status": "ok" if raw_license in _KNOWN_PERMISSIVE else "review", "license": raw_license, "classifiers": []}
    if raw_license:
        return {"status": "review", "license": "(full license text in package metadata, not a short identifier)", "classifiers": []}
    return {"status": "unknown", "license": "", "classifiers": []}


def build_manifest() -> dict:
    entries: list[dict] = []
    seen: dict[str, str] = {}
    for lock_name in LOCK_FILES:
        pins = _parse_lock_file(ROOT / lock_name)
        for pkg, version in pins.items():
            if pkg in seen and seen[pkg] != version:
                entries.append(
                    {
                        "package": pkg,
                        "version": version,
                        "source_lock": lock_name,
                        "status": "version_conflict",
                        "license": "",
                        "note": f"also pinned to {seen[pkg]} elsewhere",
                    }
                )
                continue
            if pkg in seen:
                continue
            seen[pkg] = version
            info = _license_info(pkg)
            entries.append(
                {
                    "package": pkg,
                    "version": version,
                    "source_lock": lock_name,
                    "status": info["status"],
                    "license": info["license"],
                }
            )
    entries.sort(key=lambda e: e["package"])
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {
        "generated_by": "scripts/generate_dependency_manifest.py",
        "scope": "single-environment snapshot (this machine's active venv); not a multi-platform SBOM",
        "lock_files": LOCK_FILES,
        "package_count": len(entries),
        "status_counts": counts,
        "packages": entries,
    }


def render_markdown(manifest: dict) -> str:
    lines = [
        "# Dependency license manifest (SBOM-lite)",
        "",
        "Auto-generated by `scripts/generate_dependency_manifest.py`. Do not hand-edit --",
        "regenerate after any `*.lock.txt` change.",
        "",
        f"**Scope:** {manifest['scope']}.",
        "",
        f"**Packages:** {manifest['package_count']} | **Status counts:** "
        + ", ".join(f"{k}={v}" for k, v in sorted(manifest["status_counts"].items())),
        "",
        "`ok` = short, unambiguous license identifier found. `review` = a license was found but",
        "isn't in the pre-approved permissive set, or only full license text was available --",
        "read it before redistribution. `unknown`/`not_installed` = no license metadata found",
        "in this environment; install and re-run, or check the project's own repository.",
        "",
        "| Package | Version | Status | License |",
        "| --- | --- | --- | --- |",
    ]
    for e in manifest["packages"]:
        lines.append(f"| {e['package']} | {e['version']} | {e['status']} | {e.get('license', '')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs",
        help="Where to write dependency_manifest.json / .md",
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero if any package needs review")
    args = parser.parse_args()

    manifest = build_manifest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "dependency_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "dependency_manifest.md").write_text(render_markdown(manifest), encoding="utf-8")

    print(f"Wrote {manifest['package_count']} packages to {args.output_dir}/dependency_manifest.{{json,md}}")
    print("Status counts:", manifest["status_counts"])

    if args.check:
        needs_review = manifest["status_counts"].get("review", 0) + manifest["status_counts"].get("unknown", 0)
        if needs_review:
            print(f"FAIL: {needs_review} package(s) need manual license review", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
