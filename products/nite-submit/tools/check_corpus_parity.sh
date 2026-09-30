#!/usr/bin/env bash
# Parity gate for the two checked-in copies of NITE_SUBMIT_PDF_CORPUS_V1.
#
# The corpus used to live twice: Sources/NiteSubmitTests/Fixtures/corpus (the
# one swift run reads) and tools/Fixtures/corpus (the one the release scripts
# batch through). They drifted to 239 and 209 cases, so the unit tests measured
# a detector against documents the release gate never ran. One generator now
# builds both; this script fails the moment they stop matching.
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_corpus="$product_dir/Sources/NiteSubmitTests/Fixtures/corpus"
release_corpus="$product_dir/tools/Fixtures/corpus"

[[ -f "$unit_corpus/manifest.json" ]] || { echo "Missing manifest: $unit_corpus/manifest.json" >&2; exit 1; }
[[ -f "$release_corpus/manifest.json" ]] || { echo "Missing manifest: $release_corpus/manifest.json" >&2; exit 1; }

if ! cmp -s "$unit_corpus/manifest.json" "$release_corpus/manifest.json"; then
    echo "Corpus manifests differ. Re-sync with:" >&2
    echo "  tools/generate_corpus.py --manifest-only" >&2
    echo "  tools/generate_corpus.py --out tools/Fixtures/corpus" >&2
    diff -u "$unit_corpus/manifest.json" "$release_corpus/manifest.json" | head -40 >&2
    exit 1
fi

# Both PDFs have to be present for the same case ids. A manifest case with no
# PDF means the corpus is only half-generated, and the batch gate would quietly
# process fewer files than the manifest promises.
missing="$(python3 - "$unit_corpus" "$release_corpus" <<'PY'
import json, os, sys

unit_root, release_root = sys.argv[1], sys.argv[2]
manifest = json.load(open(os.path.join(unit_root, "manifest.json")))
unrenderable = manifest.get("unrenderable_case_count")
problems = []
for root, label in ((unit_root, "unit"), (release_root, "release")):
    pdf_dir = os.path.join(root, "pdf")
    have = {n[:-4] for n in os.listdir(pdf_dir) if n.endswith(".pdf")}
    want = set()
    for case in manifest["cases"]:
        meta = case.get("meta", {})
        if meta.get("malformed") == "true" or meta.get("image_only") == "true":
            continue
        want.add(case["id"])
    for missing_id in sorted(want - have):
        problems.append(f"{label} corpus is missing pdf/{missing_id}.pdf")
    for orphan in sorted(have - want):
        problems.append(f"{label} corpus has pdf/{orphan}.pdf that no manifest case claims")
    if unrenderable is not None and unrenderable != len(manifest["cases"]) - len(want):
        problems.append(f"{label} corpus: unrenderable_case_count={unrenderable} "
                        f"but {len(manifest['cases']) - len(want)} cases are unrenderable")
for problem in problems:
    print(problem)
sys.exit(1 if problems else 0)
PY
)" || { echo "$missing" >&2; exit 1; }

# Same visible content, not the same bytes. Each fixture embeds the
# /CreationDate of the moment it was rendered, so two runs of the generator
# produce byte-different PDFs holding identical text. Comparing bytes would
# fail on every regeneration and train us to ignore this gate, so we compare
# what the detector actually reads.
if ! python3 - "$unit_corpus/pdf" "$release_corpus/pdf" <<'PY'
import os, re, sys, zlib

def text_of(path):
    raw = open(path, 'rb').read()
    chunks = []
    for m in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', raw, re.S):
        try:
            chunks.append(zlib.decompress(m.group(1)))
        except zlib.error:
            chunks.append(m.group(1))
    body = b'\n'.join(chunks)
    out = []
    for m in re.finditer(rb'\((?:\\.|[^\\()])*\)', body):
        s = m.group(0)[1:-1]
        s = re.sub(rb'\\([()\\])', rb'\1', s)
        out.append(s)
    return b'|'.join(out)

unit_root, release_root = sys.argv[1], sys.argv[2]
problems = []
for name in sorted(os.listdir(unit_root)):
    other = os.path.join(release_root, name)
    if not os.path.exists(other):
        problems.append(f"tools corpus is missing pdf/{name}")
    elif text_of(os.path.join(unit_root, name)) != text_of(other):
        problems.append(f"pdf/{name} carries different text in the two trees")
for problem in problems:
    print(problem)
sys.exit(1 if problems else 0)
PY
then
    echo "Corpus PDF content differs between the two trees. Re-sync with:" >&2
    echo "  tools/generate_corpus.py --out tools/Fixtures/corpus" >&2
    exit 1
fi

case_count="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["cases"]))' "$unit_corpus/manifest.json")"
echo "corpus-parity=pass cases=$case_count"
