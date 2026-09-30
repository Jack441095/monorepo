#!/usr/bin/env bash
# Rewrite the corpus manifest's expected_batch_summary from a real batch run.
#
# The full corpus write check compares a run against the processed/review split
# recorded in the manifest, so those numbers have to be re-measured whenever the
# detector legitimately changes. This runs the same batch the check runs and
# writes back what it saw. Review the diff before committing: a move in the split
# is a behaviour change to the release gate, not a test-data refresh.
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
corpus_root="$product_dir/tools/Fixtures/corpus"
input_dir="$corpus_root/pdf"
manifest="$corpus_root/manifest.json"
unit_manifest="$product_dir/Sources/NiteSubmitTests/Fixtures/corpus/manifest.json"

[[ -x "$cli" ]] || { echo "Missing executable CLI: $cli" >&2; exit 1; }
[[ -f "$manifest" ]] || { echo "Missing fixture manifest: $manifest" >&2; exit 1; }
[[ -f "$unit_manifest" ]] || { echo "Missing fixture manifest: $unit_manifest" >&2; exit 1; }

work_dir="$(mktemp -d /tmp/nite-submit-corpus-expect.XXXXXX)"
trap 'rm -rf "$work_dir"' EXIT

# macOS ships bash 3.2, which has no mapfile.
batch_keys=()
while IFS= read -r batch_key; do
    batch_keys+=("$batch_key")
done < <(jq -r '.expected_batch_summary | to_entries[] | .key' "$manifest")

for key in "${batch_keys[@]}"; do
    template="$(jq -r --arg k "$key" '.expected_batch_summary[$k].template' "$manifest")"
    output_dir="$work_dir/$key"
    "$cli" batch "$input_dir" \
        --out "$output_dir" \
        --template "$template" \
        --student-id 75589 \
        --collision counter >/dev/null

    results="$output_dir/batch_results.json"
    [[ -f "$results" ]] || { echo "Missing batch report: $results" >&2; exit 1; }

    processed="$(jq '[.[] | select(.status == "processed")] | length' "$results")"
    review="$(jq '[.[] | select(.status == "review_required")] | length' "$results")"
    collisions="$(jq '[.[] | select(.status == "collision")] | length' "$results")"
    failures="$(jq '[.[] | select(.status == "failed" or .status == "image_only")] | length' "$results")"

    jq --arg k "$key" --argjson processed "$processed" --argjson review "$review" \
       --argjson collisions "$collisions" --argjson failures "$failures" \
       '.expected_batch_summary[$k] += {processed: $processed, review_required: $review,
         collisions: $collisions, failures: $failures}' \
       "$manifest" > "$work_dir/manifest.json"
    mv "$work_dir/manifest.json" "$manifest"
    printf '%s\tprocessed=%s\treview_required=%s\tcollisions=%s\tfailures=%s\n' \
        "$key" "$processed" "$review" "$collisions" "$failures"
done

# Both copies carry the same numbers, or the parity gate fails on the spot.
cp "$manifest" "$unit_manifest"
"$product_dir/tools/check_corpus_parity.sh"
echo "Updated expected_batch_summary in both corpus manifests"
