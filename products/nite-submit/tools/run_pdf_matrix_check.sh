#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
[[ -x "$cli" ]] || {
  echo "PDF matrix check needs an executable CLI: $cli" >&2
  exit 1
}

work_dir=$(mktemp -d /tmp/nite-submit-pdf-matrix.XXXXXX)
trap 'rm -R -- "$work_dir"' EXIT

name_stage="$work_dir/name-input"
name_output="$work_dir/name-output"
mkdir -p "$name_stage"
ln -s "$product_dir/real_validation_corpus/dissertations/utar_3904_meow_fyp_2019.pdf" \
  "$name_stage/utar.pdf"
ln -s "$product_dir/real_validation_corpus/dissertations/whiterose_18613_long_phd_sheffield.pdf" \
  "$name_stage/white_rose.pdf"
ln -s "$product_dir/real_validation_corpus/project_reports/aiub_capstone_smart_water_metering_2023.pdf" \
  "$name_stage/aiub.pdf"
ln -s "$product_dir/real_validation_corpus/university_templates/edge_hill_hea3183_assignment_header.pdf" \
  "$name_stage/edge_hill_guidance.pdf"

"$cli" batch "$name_stage" --out "$name_output" --student-id 75589 \
  --template '{student_id}_{first_name}_{last_name}_{project_title}' --dry-run >/dev/null

jq -e '
  (map(select(.source == "utar.pdf" and .status == "dry_run" and
             .fields.first_name == "MERVYN" and .fields.last_name == "YANG")) | length) == 1 and
  (map(select(.source == "white_rose.pdf" and .status == "dry_run" and
             .fields.first_name == "Yang" and .fields.last_name == "Long" and
             (.output | contains("Zero-shot_Image_Classification")))) | length) == 1 and
  (map(select(.source == "aiub.pdf" and .status == "dry_run" and
             .fields.first_name == "Majid" and .fields.last_name == "Abdul" and
             (.fields.project_title | length) > 10)) | length) == 1 and
  (map(select(.source == "edge_hill_guidance.pdf" and .status == "review_required" and
             (.gaps | index("student_name")))) | length) == 1
' "$name_output/batch_results.json" >/dev/null

required_stage="$work_dir/required-input"
required_output="$work_dir/required-output"
mkdir -p "$required_stage"
ln -s "$product_dir/real_validation_corpus/public_examples/75589_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf" \
  "$required_stage/public.pdf"
"$cli" batch "$required_stage" --out "$required_output" --student-id 75589 \
  --template '{module_code}_{student_id}_{project_title}' --dry-run >/dev/null
jq -e '
  length == 1 and .[0].status == "review_required" and .[0].output == null and
  .[0].fields.module_code == null and (.[0].gaps | index("module_code")) != null
' "$required_output/batch_results.json" >/dev/null

us_assignment_stage="$work_dir/us-assignment-input"
us_assignment_output="$work_dir/us-assignment-output"
mkdir -p "$us_assignment_stage"
ln -s "$product_dir/real_validation_corpus/university_templates/uw_tacoma_mscss_capstone_guidelines.pdf" \
  "$us_assignment_stage/uw_guidance.pdf"
"$cli" batch "$us_assignment_stage" --out "$us_assignment_output" --student-id 75589 \
  --template '{last_name}_{assignment_code}' --dry-run >/dev/null
jq -e '
  length == 1 and .[0].status == "review_required" and .[0].output == null and
  .[0].fields.document_type == "guidance_template" and
  (.[0].gaps | index("assignment_code")) != null
' "$us_assignment_output/batch_results.json" >/dev/null

identity_output="$work_dir/identity-output"
"$cli" batch "$required_stage" --out "$identity_output" --student-id 75589 \
  --template '{student_id}_{project_title}' --identity-policy name-prohibited --dry-run >/dev/null
jq -e '
  length == 1 and .[0].status == "review_required" and .[0].output == null and
  .[0].fields.document_identity_policy == "name_prohibited" and
  .[0].fields.document_identity_status == "name_present" and
  (.[0].gaps | index("document_identity")) != null
' "$identity_output/batch_results.json" >/dev/null

anonymous_stage="$work_dir/anonymous-input"
anonymous_output="$work_dir/anonymous-output"
mkdir -p "$anonymous_stage"
ln -s "$product_dir/Sources/NiteSubmitTests/Fixtures/corpus/pdf/id_variant_01.pdf" \
  "$anonymous_stage/anonymous.pdf"
"$cli" batch "$anonymous_stage" --out "$anonymous_output" \
  --template '{candidate_number}_{project_title}' --dry-run >/dev/null
jq -e '
  length == 1 and .[0].status == "dry_run" and
  .[0].fields.candidate_number == "A12345678" and
  (.[0].output | startswith("A12345678_")) and
  (.[0].output | contains("student") | not)
' "$anonymous_output/batch_results.json" >/dev/null

image_stage="$work_dir/image-input"
image_output="$work_dir/image-output"
mkdir -p "$image_stage"
ln -s "$product_dir/real_validation_corpus/edge_cases/image_only_blank.pdf" \
  "$image_stage/image_only.pdf"
"$cli" batch "$image_stage" --out "$image_output" --student-id 75589 \
  --template '{student_id}_{project_title}' --dry-run >/dev/null
jq -e 'length == 1 and .[0].status == "image_only" and .[0].output == null and
  .[0].fields.document_type == "image_only" and
  (.[0].fields.document_reason | contains("OCR"))' \
  "$image_output/batch_results.json" >/dev/null

invalid_output="$work_dir/invalid-output"
if "$cli" batch "$image_stage" --out "$invalid_output" \
  --template '{student_id}_{unknown_field}' --dry-run >/dev/null 2>&1; then
  echo "Invalid template was unexpectedly accepted by batch mode." >&2
  exit 1
fi
[[ ! -e "$invalid_output/batch_results.json" ]] || {
  echo "Invalid template created a batch report." >&2
  exit 1
}

echo "PDF matrix check passed: dissertation, capstone, guidance, anonymous, and image-only cases."
