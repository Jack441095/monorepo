#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
reports_dir=$(mktemp -d /tmp/nite-submit-release-check.XXXXXX)

cd "$product_dir"
if [[ $# -gt 0 ]]; then
  batch_input=$(CDPATH= cd -- "$1" && pwd)
else
  # Stage only the approved public/controlled PDFs. This excludes rejected
  # documents, private beta intake, and the generated test_results directory,
  # while keeping the batch input isolated from any source-tree writes.
  batch_input=$(mktemp -d /tmp/nite-submit-qualified.XXXXXX)
  find real_validation_corpus -type f -name '*.pdf' \
    -not -path '*/test_results/*' \
    -not -path '*/rejected/*' \
    -not -path '*/edge_cases/*' \
    -not -path '*/beta_intake/*' \
    -exec ln -s "$product_dir/{}" "$batch_input/" \;

  # Keep this boundary fail-closed if the staging filter is changed later.
  if find "$batch_input" -type l -exec readlink {} \; | rg -q '/beta_intake/'; then
    echo "Release corpus scope error: private beta intake was staged." >&2
    exit 1
  fi
fi

[[ -d "$batch_input" ]] || {
  echo "Qualified batch corpus not found: $batch_input" >&2
  exit 1
}

echo "== regression suite =="
test_log="$reports_dir/test-suite.log"
swift run nitesubmit-tests | tee "$test_log"
test_checks=$(sed -n 's/^\([0-9][0-9]*\/[0-9][0-9]*\) checks passed$/\1/p' "$test_log" | tail -1)
[[ -n "$test_checks" ]] || {
  echo "Could not determine the deterministic test count from the regression suite" >&2
  exit 1
}
echo "== package and archive =="
./tools/package_app.sh
./tools/package_beta_zip.sh
echo "== artifact cleanup gate =="
./tools/test_artifact_cleanup.sh
echo "== release corpus scope gate =="
./tools/test_release_corpus_scope.sh
echo "== beta intake privacy gate =="
./tools/run_beta_intake_smoke_check.sh
echo "== deterministic archive gate =="
./tools/test_deterministic_archive.sh
echo "== PDF matrix gate =="
./tools/run_pdf_matrix_check.sh
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
echo "== bundle gate =="
./tools/verify_app_bundle.sh "artifacts/Submit-${version}-macOS.app"
echo "== extracted archive smoke gate =="
./tools/run_archive_smoke_check.sh
echo "== batch approval gate =="
./tools/run_batch_approval_check.sh
echo "== categorized acceptance sweep =="
./tools/run_acceptance_sweep.sh
echo "== full corpus write gate =="
./tools/run_full_corpus_write_check.sh

cli="artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli"
cli_help=$("$cli" 2>&1)
[[ "$cli_help" == *'--template "<tpl>"'* ]] || {
  echo "CLI help is missing batch --template documentation" >&2
  exit 1
}
[[ "$cli_help" == *'default template: {student_id}_{project_title}'* ]] || {
  echo "CLI help is missing the safe ID + Project batch default" >&2
  exit 1
}
echo "== targeted field policy =="
"$cli" validate \
  --manifest real_validation_corpus/manifests/field_policy_manifest_v1.json \
  --out "$reports_dir/field_policy.json"
echo "== governed corpus =="
"$cli" validate \
  --manifest real_validation_corpus/manifests/first_wave_manifest_v2.json \
  --out "$reports_dir/first_wave.json"
"$cli" validate \
  --manifest real_validation_corpus/manifests/accuracy_manifest_v2.json \
  --out "$reports_dir/accuracy.json"
"$cli" validate \
  --manifest real_validation_corpus/manifests/wave3_manifest.json \
  --out "$reports_dir/wave3.json"
"$cli" validate \
  --manifest real_validation_corpus/manifests/wave4_manifest.json \
  --out "$reports_dir/wave4.json"
"$cli" validate \
  --manifest real_validation_corpus/manifests/wave5_manifest.json \
  --out "$reports_dir/wave5.json"
echo "== batch dry run =="
"$cli" batch "$batch_input" \
  --out real_validation_corpus/test_results \
  --student-id 75589 --dry-run

echo "== release-check summary =="
for report in field_policy first_wave accuracy wave3 wave4 wave5; do
  jq -r '[.processed,.wrong_high_confidence_total,.failed_missing_files,.encrypted_or_unreadable] | @tsv' \
    "$reports_dir/$report.json" | sed "s/^/$report\t/"
done
batch_summary=$(jq -r '[length,(map(select(.status=="dry_run"))|length),(map(select(.status=="review_required"))|length),(map(select(.status=="processed"))|length)] | @tsv' \
  real_validation_corpus/test_results/batch_results.json)
jq -e 'all(.[]; (.fields.document_type != null))' \
  real_validation_corpus/test_results/batch_results.json >/dev/null
printf 'batch\t%s\n' "$batch_summary"
echo "== DMG parity gate =="
./tools/create_release_dmg.sh --app-ready
./tools/verify_release_artifacts.sh
./tools/write_release_manifest.sh --checks "$test_checks" --batch-summary "$batch_summary"
echo "reports=$reports_dir"
echo "release-check=pass"
