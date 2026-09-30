#!/usr/bin/env bash
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
corpus_root="$product_dir/tools/Fixtures/corpus"
input_dir="$corpus_root/pdf"
manifest="$corpus_root/manifest.json"
results_root="$product_dir/real_validation_corpus/test_results"

[[ -x "$cli" ]] || { echo "Missing executable CLI: $cli" >&2; exit 1; }
[[ -d "$input_dir" ]] || { echo "Missing fixture corpus: $input_dir" >&2; exit 1; }
[[ -f "$manifest" ]] || { echo "Missing fixture manifest: $manifest" >&2; exit 1; }

# The unit tests and this gate run the same corpus. If the two copies have
# drifted, the counts below are being compared against a different set of
# documents than the detector was measured on, so refuse before running.
"$product_dir/tools/check_corpus_parity.sh"

# Every expected count comes out of the manifest. Hardcoding them here meant a
# corpus regeneration and a release gate could disagree without either noticing.
expected_sources="$(jq '(.cases | length) - .unrenderable_case_count' "$manifest")"
# macOS ships bash 3.2, which has no mapfile.
batch_keys=()
while IFS= read -r batch_key; do
    batch_keys+=("$batch_key")
done < <(jq -r '.expected_batch_summary | to_entries[] | .key' "$manifest")
[[ "${#batch_keys[@]}" -gt 0 ]] || { echo "No expected_batch_summary entries in $manifest" >&2; exit 1; }

mkdir -p "$results_root"

# These are the only directories this check may delete. The pattern is anchored
# to $results_root so cleanup cannot expand beyond generated validation output.
output_dirs=()
for key in "${batch_keys[@]}"; do
    target="$results_root/full_corpus_${key}_current"
    case "$target" in
        "$results_root"/full_corpus_*_current) ;;
        *) echo "Refusing unexpected cleanup target: $target" >&2; exit 1 ;;
    esac
    if [[ -e "$target" ]]; then rm -rf "$target"; fi
    output_dirs+=("$target")
done

source_hashes_before="$(mktemp)"
source_hashes_after="$(mktemp)"
cleanup() { rm -f "$source_hashes_before" "$source_hashes_after"; }
trap cleanup EXIT

hash_sources() {
    find "$input_dir" -type f -name '*.pdf' -print | sort | xargs shasum -a 256
}

hash_sources > "$source_hashes_before"
source_count="$(wc -l < "$source_hashes_before" | tr -d ' ')"
[[ "$source_count" == "$expected_sources" ]] || {
    echo "Manifest promises $expected_sources fixture PDFs, found $source_count" >&2
    echo "Run tools/generate_corpus.py --out tools/Fixtures/corpus" >&2
    exit 1
}

run_batch() {
    local output_dir="$1"
    local template="$2"
    "$cli" batch "$input_dir" \
        --out "$output_dir" \
        --template "$template" \
        --student-id 75589 \
        --collision counter
}

assert_batch() {
    local key="$1"
    local output_dir="$results_root/full_corpus_${key}_current"
    local template want_processed want_review want_collisions want_failures
    template="$(jq -r --arg k "$key" '.expected_batch_summary[$k].template' "$manifest")"
    want_processed="$(jq -r --arg k "$key" '.expected_batch_summary[$k].processed' "$manifest")"
    want_review="$(jq -r --arg k "$key" '.expected_batch_summary[$k].review_required' "$manifest")"
    want_collisions="$(jq -r --arg k "$key" '.expected_batch_summary[$k].collisions' "$manifest")"
    want_failures="$(jq -r --arg k "$key" '.expected_batch_summary[$k].failures' "$manifest")"

    run_batch "$output_dir" "$template"

    local results="$output_dir/batch_results.json"
    [[ -f "$results" ]] || { echo "Missing batch report: $results" >&2; exit 1; }

    local reported processed review collisions failures gaps missing_output
    reported="$(jq 'length' "$results")"
    processed="$(jq '[.[] | select(.status == "processed")] | length' "$results")"
    review="$(jq '[.[] | select(.status == "review_required")] | length' "$results")"
    collisions="$(jq '[.[] | select(.status == "collision")] | length' "$results")"
    failures="$(jq '[.[] | select(.status == "failed" or .status == "image_only")] | length' "$results")"
    gaps="$(jq '[.[] | select(.status == "processed") | select((.gaps | length) > 0)] | length' "$results")"
    missing_output="$(jq '[.[] | select(.status == "processed") | select(.output == null or .output == "")] | length' "$results")"

    # A silently dropped fixture is the failure mode this gate exists to catch:
    # every source has to come back with a status, and the statuses have to add
    # up to the manifest's case count.
    [[ "$reported" == "$expected_sources" ]] || {
        echo "Batch reported $reported results for $expected_sources manifest cases ($key)" >&2
        exit 1
    }
    [[ $((processed + review + collisions + failures)) == "$expected_sources" ]] || {
        echo "Batch statuses do not cover every source ($key): processed=$processed review_required=$review collisions=$collisions failures=$failures" >&2
        exit 1
    }
    [[ "$processed" == "$want_processed" && "$review" == "$want_review" &&
       "$collisions" == "$want_collisions" &&
       "$failures" == "$want_failures" && "$gaps" == "0" && "$missing_output" == "0" ]] || {
        echo "Unexpected batch summary for $key: processed=$processed (want $want_processed) review_required=$review (want $want_review) collisions=$collisions (want $want_collisions) failures=$failures (want $want_failures) gaps=$gaps missing_output=$missing_output" >&2
        echo "If this detector change was meant to move the split, refresh the manifest with tools/record_corpus_batch_expectations.sh" >&2
        exit 1
    }

    local pdf_count symlink_count
    pdf_count="$(find "$output_dir" -type f -name '*.pdf' | wc -l | tr -d ' ')"
    symlink_count="$(find "$output_dir" -type l | wc -l | tr -d ' ')"
    [[ "$pdf_count" == "$processed" && "$symlink_count" == "0" ]] || {
        echo "Unexpected output file shape for $output_dir: pdfs=$pdf_count (want $processed) symlinks=$symlink_count" >&2
        exit 1
    }

    if [[ "$template" == *full_name* ]]; then
        local missing_names
        missing_names="$(jq '[.[] | select(.status == "processed") | select(.fields.student_name == null or .fields.first_name == null or .fields.last_name == null)] | length' "$results")"
        [[ "$missing_names" == "0" ]] || { echo "Name-bearing output has $missing_names missing names" >&2; exit 1; }
    fi

    while IFS=$'\t' read -r source output; do
        cmp -s "$input_dir/$source" "$output_dir/$output" || {
            echo "Byte mismatch: $source -> $output" >&2
            exit 1
        }
    done < <(jq -r '.[] | select(.status == "processed") | [.source, .output] | @tsv' "$results")

    printf '%s\tprocessed=%s\treview_required=%s\tcollisions=%s\tfailures=%s\n' \
        "$key" "$processed" "$review" "$collisions" "$failures"
}

for key in "${batch_keys[@]}"; do
    assert_batch "$key"
done

hash_sources > "$source_hashes_after"
cmp -s "$source_hashes_before" "$source_hashes_after" || {
    echo "Source corpus changed during write check" >&2
    exit 1
}

echo "full-corpus-write-check=pass sources=$expected_sources"
