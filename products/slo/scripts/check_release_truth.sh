#!/usr/bin/env bash
# Release-truth gate: every commit reference in a SLO report must resolve.
#
# The product-truth documents are the release authority, so a commit they cite
# that exists nowhere makes their rollback instruction unrunnable. That happened:
# fourteen SHAs across twelve reports dated from before the monorepo
# consolidation and resolved against no object database. A document that cannot
# be rolled back to should fail a gate rather than look authoritative.
#
# Retraction is a valid fix, recorded as an explicit null or an
# "unresolvable" note, so the gate passes only when the truth is stated.
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$product_dir"

python3 - <<'PY'
import json
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(".")
# Anything that states a commit, a checkpoint, or a build provenance claim.
targets = sorted(root.glob("*.md")) + sorted(root.glob("*.json")) + sorted((root / "docs").glob("*.md"))
targets = [p for p in targets if p.name != "SLO_REVIEW_V1.md"]

def resolves(sha):
    r = subprocess.run(["git", "cat-file", "-t", sha], capture_output=True, text=True)
    return r.returncode == 0

def branches_exist(names):
    known = subprocess.run(["git", "branch", "-a", "--format=%(refname:short)"],
                           capture_output=True, text=True).stdout.split()
    return [n for n in names if n not in known]

# 8-hex is a plausible short SHA; longer runs inside prose are usually hashes,
# sizes, or dates, so we only judge a token that looks like a commit reference.
shaish = re.compile(r"\b[0-9a-f]{7,40}\b")
date_like = re.compile(r"^(?:19|20)\d{6}$|^\d{8}$")

problems = []
seen_missing = {}

for path in targets:
    text = path.read_text(errors="replace")
    for m in shaish.finditer(text):
        token = m.group(0)
        if date_like.match(token) or len(token) < 8:
            continue
        # A 40-hex token inside a JSON string field named like a commit, or a
        # sentence that says commit/checkpoint/sha, is a claim.
        # A float is a temperature or a score, never a commit. The regex splits
        # `0.686393678188324` at the dot, so check the character before too.
        if "." in token or text[m.start() - 1: m.start()] == ".":
            continue
        # A truncated digest written as `83c8ab41…62682f` is a SHA-256, not a
        # commit. Real commit references are never elided like that.
        tail = text[m.end():m.end() + 1]
        if tail in ("…", "..."):
            continue
        # A sentence that says commit/checkpoint/sha, or a JSON field whose key
        # names one, is a claim.
        context = text[max(0, m.start() - 120):m.end() + 60].lower()
        if not re.search(r"commit|checkpoint|\bsha\b|rev\b|rollback|head ", context):
            continue
        if resolves(token):
            continue
        seen_missing.setdefault(token, []).append(str(path))
        problems.append(f"{path}: unresolved commit reference {token}")

for branch in ["engineering/slo-format-aware-scan-v1"]:
    for name in branches_exist([branch]):
        for path in targets:
            if branch in path.read_text(errors="replace"):
                problems.append(f"{path}: cites branch {name}, which does not exist")

truth = root / "SLO_PRODUCT_TRUTH_MANIFEST_V1.json"
if truth.exists():
    manifest = json.loads(truth.read_text())
    src = manifest.get("source", {})
    for field, value in src.items():
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) and not resolves(value):
            problems.append(f"{truth.name}: source.{field} = {value} does not resolve")
    if src.get("product_code_checkpoint_sha") is None and "unresolvable" not in str(
            src.get("product_code_checkpoint_sha_status", "")):
        problems.append(
            f"{truth.name}: a null product_code_checkpoint_sha needs a *_status note "
            "saying why, so a later reader does not read it as an omission")

for problem in sorted(set(problems)):
    print(problem)

if problems:
    print(f"\nrelease-truth-gate=FAIL problems={len(set(problems))}", file=sys.stderr)
    print("Resolve each reference to a real commit, or retract the claim explicitly.", file=sys.stderr)
    sys.exit(1)

print(f"release-truth-gate=pass reports={len(targets)}")
PY
