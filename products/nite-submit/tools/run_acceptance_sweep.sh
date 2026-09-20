#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
results_dir="$product_dir/real_validation_corpus/test_results/acceptance_sweep_current"
work_dir=$(mktemp -d /tmp/nite-submit-acceptance-sweep.XXXXXX)
trap 'rm -R -- "$work_dir"' EXIT

[[ -x "$cli" ]] || {
  echo "Acceptance sweep needs an executable CLI: $cli" >&2
  exit 1
}

mkdir -p "$results_dir"

student_stage="$work_dir/student-submissions"
mkdir -p "$student_stage"
find "$product_dir/real_validation_corpus/dissertations" \
     "$product_dir/real_validation_corpus/project_reports" \
     "$product_dir/real_validation_corpus/public_examples" \
     -type f -name '*.pdf' -exec ln -s {} "$student_stage/" \;

run_batch() {
  local input_dir="$1"
  local output_dir="$2"
  shift 2
  "$cli" batch "$input_dir" --out "$output_dir" --student-id 75589 --dry-run "$@" >/dev/null
}

run_batch "$student_stage" "$results_dir/student_submissions"
run_batch "$product_dir/real_validation_corpus/university_templates" \
  "$results_dir/university_guidance"

anonymous_stage="$work_dir/anonymous"
mkdir -p "$anonymous_stage"
ln -s "$product_dir/Sources/NiteSubmitTests/Fixtures/corpus/pdf/id_variant_01.pdf" \
  "$anonymous_stage/anonymous.pdf"
run_batch "$anonymous_stage" "$results_dir/anonymous_candidate" \
  --template '{candidate_number}_{project_title}'

image_stage="$work_dir/image-only"
mkdir -p "$image_stage"
ln -s "$product_dir/real_validation_corpus/edge_cases/image_only_blank.pdf" \
  "$image_stage/image_only.pdf"
run_batch "$image_stage" "$results_dir/image_only"

run_batch "$product_dir/real_validation_corpus/public_examples" \
  "$results_dir/name_prohibited" --identity-policy name-prohibited
run_batch "$product_dir/real_validation_corpus/public_examples" \
  "$results_dir/module_code_required" \
  --template '{module_code}_{student_id}_{project_title}'

echo "Acceptance sweep reports: $results_dir"
for report in "$results_dir"/*/batch_results.json; do
  label=$(basename "$(dirname "$report")")
  jq -r --arg label "$label" \
    '[$label, length,
      (map(select(.status == "dry_run")) | length),
      (map(select(.status == "review_required")) | length),
      (map(select(.status == "image_only")) | length),
      (map(select(.status == "processed" or .status == "failed" or .status == "collision")) | length)] | @tsv' \
    "$report"
done | sort

jq -e 'length == 1 and .[0].status == "dry_run" and
  .[0].fields.candidate_number == "A12345678"' \
  "$results_dir/anonymous_candidate/batch_results.json" >/dev/null
jq -e 'length == 1 and .[0].status == "image_only" and .[0].output == null' \
  "$results_dir/image_only/batch_results.json" >/dev/null
jq -e 'all(.[]; .status == "review_required" and
  .fields.document_identity_status == "name_present" and
  (.gaps | index("document_identity")) != null)' \
  "$results_dir/name_prohibited/batch_results.json" >/dev/null
jq -e 'all(.[]; .status == "review_required" and
  (.gaps | index("module_code")) != null and .output == null)' \
  "$results_dir/module_code_required/batch_results.json" >/dev/null

echo "Acceptance sweep assertions passed."
