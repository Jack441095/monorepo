#!/usr/bin/env bash
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
input_dir="$product_dir/tools/Fixtures/corpus/pdf"
results_root="$product_dir/real_validation_corpus/test_results"
id_output="$results_root/full_corpus_id_project_current"
name_output="$results_root/full_corpus_name_project_current"

[[ -x "$cli" ]] || { echo "Missing executable CLI: $cli" >&2; exit 1; }
[[ -d "$input_dir" ]] || { echo "Missing fixture corpus: $input_dir" >&2; exit 1; }
mkdir -p "$results_root"

# These are the two disposable directories owned by this check. Refuse any
# other target so cleanup cannot expand beyond generated validation output.
for target in "$id_output" "$name_output"; do
    case "$target" in
        "$results_root/full_corpus_id_project_current"|"$results_root/full_corpus_name_project_current") ;;
        *) echo "Refusing unexpected cleanup target: $target" >&2; exit 1 ;;
    esac
    if [[ -e "$target" ]]; then rm -rf "$target"; fi
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
[[ "$source_count" == "203" ]] || {
    echo "Expected 203 fixture PDFs, found $source_count" >&2
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

run_batch "$id_output" '{student_id}_{project_title}'
run_batch "$name_output" '{student_id}_{full_name}_{project_title}'

assert_batch() {
    local output_dir="$1"
    local expected_name="${2:-false}"
    local results="$output_dir/batch_results.json"
    [[ -f "$results" ]] || { echo "Missing batch report: $results" >&2; exit 1; }

    local processed review collisions failures gaps missing_output
    processed="$(jq '[.[] | select(.status == "processed")] | length' "$results")"
    review="$(jq '[.[] | select(.status == "review_required")] | length' "$results")"
    collisions="$(jq '[.[] | select(.status == "collision")] | length' "$results")"
    failures="$(jq '[.[] | select(.status == "failed" or .status == "image_only")] | length' "$results")"
    gaps="$(jq '[.[] | select(.status == "processed") | select((.gaps | length) > 0)] | length' "$results")"
    missing_output="$(jq '[.[] | select(.status == "processed") | select(.output == null or .output == "")] | length' "$results")"

    [[ "$processed" == "152" && "$review" == "51" && "$collisions" == "0" &&
       "$failures" == "0" && "$gaps" == "0" && "$missing_output" == "0" ]] || {
        echo "Unexpected batch summary for $output_dir: processed=$processed review_required=$review collisions=$collisions failures=$failures gaps=$gaps missing_output=$missing_output" >&2
        exit 1
    }

    local pdf_count symlink_count
    pdf_count="$(find "$output_dir" -type f -name '*.pdf' | wc -l | tr -d ' ')"
    symlink_count="$(find "$output_dir" -type l | wc -l | tr -d ' ')"
    [[ "$pdf_count" == "152" && "$symlink_count" == "0" ]] || {
        echo "Unexpected output file shape for $output_dir: pdfs=$pdf_count symlinks=$symlink_count" >&2
        exit 1
    }

    if [[ "$expected_name" == "true" ]]; then
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
        "$(basename "$output_dir")" "$processed" "$review" "$collisions" "$failures"
}

assert_batch "$id_output"
assert_batch "$name_output" true

hash_sources > "$source_hashes_after"
cmp -s "$source_hashes_before" "$source_hashes_after" || {
    echo "Source corpus changed during write check" >&2
    exit 1
}

echo "full-corpus-write-check=pass"
