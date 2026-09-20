#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"

version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
[[ -x "$cli" ]] || {
  echo "Batch approval check needs an executable CLI: $cli" >&2
  exit 1
}

work_dir=$(mktemp -d /tmp/nite-submit-approval-check.XXXXXX)
trap 'rm -rf "$work_dir"' EXIT

source_name="75589_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf"
source_path="$product_dir/real_validation_corpus/public_examples/$source_name"
stage="$work_dir/approved-input"
output="$work_dir/approved-output"
approval="$work_dir/approval_manifest.json"
mkdir -p "$stage"
ln -s "$source_path" "$stage/$source_name"
printf '%s\n' '{"approval_version":"BATCH_APPROVAL_V1","approved_sources":["75589_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf"]}' > "$approval"

echo "== approved uncertain case =="
"$cli" batch "$stage" --out "$output" --student-id 75589 \
  --template '{student_id}_{first_name}_{last_name}_{project_title}' \
  --collision counter --approved-manifest "$approval"
approved_summary=$(jq -r '[length,(map(select(.status=="processed"))|length),(map(select(.status=="review_required"))|length)] | @tsv' "$output/batch_results.json")
[[ "$approved_summary" == $'1\t1\t0' ]] || {
  echo "Unexpected approved summary: $approved_summary" >&2
  exit 1
}
output_name=$(jq -r '.[0].output' "$output/batch_results.json")
[[ -n "$output_name" && -f "$output/$output_name" && ! -L "$output/$output_name" ]] || {
  echo "Approved output is not a regular file" >&2
  exit 1
}
cmp -s "$source_path" "$output/$output_name" || {
  echo "Approved output is not byte-identical to its source" >&2
  exit 1
}

echo "== required-gap case remains blocked =="
gap_stage="$work_dir/gap-input"
gap_output="$work_dir/gap-output"
gap_source="cambridge_cover_sheet_written_work.pdf"
mkdir -p "$gap_stage"
ln -s "$product_dir/real_validation_corpus/university_templates/$gap_source" "$gap_stage/$gap_source"
printf '%s\n' '{"approval_version":"BATCH_APPROVAL_V1","approved_sources":["cambridge_cover_sheet_written_work.pdf"]}' > "$approval"
"$cli" batch "$gap_stage" --out "$gap_output" --student-id 75589 \
  --template '{student_id}_{first_name}_{last_name}_{project_title}' \
  --collision counter --approved-manifest "$approval"
gap_summary=$(jq -r '[length,(map(select(.status=="processed"))|length),(map(select(.status=="review_required"))|length)] | @tsv' "$gap_output/batch_results.json")
[[ "$gap_summary" == $'1\t0\t1' ]] || {
  echo "Unexpected required-gap summary: $gap_summary" >&2
  exit 1
}
gap_pdfs=$(find "$gap_output" -maxdepth 1 -type f -name '*.pdf' | wc -l | tr -d ' ')
[[ "$gap_pdfs" == "0" ]] || {
  echo "Required-gap case wrote $gap_pdfs PDF(s)" >&2
  exit 1
}

echo "== guidance/template case remains review-held =="
guidance_stage="$work_dir/guidance-input"
guidance_output="$work_dir/guidance-output"
guidance_source="edge_hill_hea3183_assignment_header.pdf"
mkdir -p "$guidance_stage"
ln -s "$product_dir/real_validation_corpus/university_templates/$guidance_source" \
  "$guidance_stage/$guidance_source"
"$cli" batch "$guidance_stage" --out "$guidance_output" --student-id 75589 \
  --template '{student_id}_{project_title}' --collision counter
jq -e 'length == 1 and .[0].status == "review_required" and
  .[0].fields.document_type == "guidance_template" and
  .[0].output == null and (.[0].gaps | index("guidance_template_review")) != null' \
  "$guidance_output/batch_results.json" >/dev/null || {
  echo "Guidance/template batch case was not held for explicit review" >&2
  exit 1
}

echo "Batch approval check passed: explicit approval writes only approved complete cases."
