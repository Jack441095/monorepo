#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"

version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
archive="artifacts/Submit-${version}-macOS.zip"
[[ -f "$archive" ]] || { echo "Archive not found: $archive" >&2; exit 1; }

work_dir=$(/usr/bin/mktemp -d /tmp/nite-submit-archive-smoke.XXXXXX)
trap 'rm -rf "$work_dir"' EXIT
/usr/bin/unzip -q "$archive" -d "$work_dir"

app="$work_dir/Submit-${version}-macOS.app"
cli="$app/Contents/MacOS/nitesubmit-cli"
"$product_dir/tools/verify_app_bundle.sh" "$app"

/usr/bin/unzip -Z1 "$archive" | /usr/bin/grep \
  "^Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli$" >/dev/null

source_name="archive_smoke_75589.pdf"
source_path="$product_dir/real_validation_corpus/dissertations/whiterose_18613_long_phd_sheffield.pdf"
input_dir="$work_dir/input"
output_dir="$work_dir/output"
mkdir -p "$input_dir"
cp "$source_path" "$input_dir/$source_name"

suggest="$work_dir/suggest.txt"
"$cli" suggest "$input_dir/$source_name" --template '{project_title}' > "$suggest"
/usr/bin/grep -q '^student_name:   Yang Long' "$suggest"
/usr/bin/grep -q '^project_title:  Zero-shot Image Classification' "$suggest"

suggest_with_saved_id="$work_dir/suggest_with_saved_id.txt"
"$cli" suggest "$input_dir/$source_name" --student-id 75589 \
  --template '{student_id}_{first_name}_{last_name}_{project_title}' > "$suggest_with_saved_id"
/usr/bin/grep -q '^student_id:     75589 \[HIGH\]' "$suggest_with_saved_id"
/usr/bin/grep -q '^preview:        75589_Yang_Long_Zero-shot_Image_Classification.pdf' \
  "$suggest_with_saved_id"

approval="$work_dir/approval_manifest.json"
printf '%s\n' '{"approval_version":"BATCH_APPROVAL_V1","approved_sources":["archive_smoke_75589.pdf"]}' > "$approval"
"$cli" batch "$input_dir" --out "$output_dir" --student-id 75589 \
  --template '{student_id}_{first_name}_{last_name}_{project_title}' \
  --collision counter --approved-manifest "$approval"

/usr/bin/jq -e 'length == 1 and .[0].status == "processed" and .[0].gaps == ["explicit_approval"]' \
  "$output_dir/batch_results.json" >/dev/null
output_name=$(/usr/bin/jq -r '.[0].output' "$output_dir/batch_results.json")
expected_name='75589_Yang_Long_Zero-shot_Image_Classification.pdf'
[[ "$output_name" == "$expected_name" ]] || {
  echo "Filename did not preserve the expected name/title components: $output_name" >&2
  exit 1
}
/usr/bin/jq -e \
  '.[0].fields.first_name == "Yang" and
   .[0].fields.last_name == "Long" and
   .[0].fields.project_title == "Zero-shot Image Classification"' \
  "$output_dir/batch_results.json" >/dev/null
[[ -f "$output_dir/$output_name" && ! -L "$output_dir/$output_name" ]] || {
  echo "Extracted archive did not produce a regular approved PDF" >&2
  exit 1
}
/usr/bin/cmp -s "$source_path" "$output_dir/$output_name"

echo "Archive smoke check passed: extracted bundle, CLI detection, and approved copy verified."
