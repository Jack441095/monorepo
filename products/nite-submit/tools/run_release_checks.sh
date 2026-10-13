#!/bin/zsh
set -euo pipefail
product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"
[[ $# == 0 ]] || { echo 'Release inputs come only from pinned review records; no directory argument is accepted.' >&2; exit 2; }
version=$(tr -d '[:space:]' < VERSION)
evidence_root="$product_dir/artifacts/shipping-$(date -u +%Y-%m-%d)"
mkdir -p "$evidence_root"
reports_dir=$(mktemp -d "$evidence_root/release.XXXXXX")
work_dir=$(mktemp -d /tmp/nite-submit-release.XXXXXX)
trap 'rm -R -- "$work_dir"' EXIT
# A failing rerun must not leave an earlier pass manifest next to new binaries.
rm -f "artifacts/Submit-${version}-release-manifest.json"
python3 tools/stage_release_corpus.py "$work_dir/qualified"
./tools/check_corpus_parity.sh
python3 -m unittest discover -s tools -p 'test_*corpus.py'
python3 -m unittest discover -s tools -p 'test_update_appcast.py'
swift run nitesubmit-tests | tee "$reports_dir/test-suite.log"
test_checks=$(sed -n 's/^\([0-9][0-9]*\/[0-9][0-9]*\) checks passed$/\1/p' "$reports_dir/test-suite.log" | tail -1)
[[ -n "$test_checks" ]] || { echo 'No successful regression count was recorded.' >&2; exit 1; }
./tools/package_app.sh
./tools/package_beta_zip.sh
export NITE_SUBMIT_CLI="$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli"
./tools/test_validation_identity.sh
python3 tools/check_rebuilt_corpus.py --cli "$NITE_SUBMIT_CLI"
./tools/test_artifact_cleanup.sh
./tools/test_release_corpus_scope.sh
./tools/run_beta_intake_smoke_check.sh
./tools/test_deterministic_archive.sh
./tools/run_pdf_matrix_check.sh
./tools/verify_app_bundle.sh "artifacts/Submit-${version}-macOS.app"
./tools/run_archive_smoke_check.sh
./tools/run_bundled_tools_check.sh
./tools/run_batch_approval_check.sh
./tools/run_acceptance_sweep.sh
./tools/run_full_corpus_write_check.sh
cli_help=$("$NITE_SUBMIT_CLI" 2>&1)
[[ "$cli_help" == *'--template "<tpl>"'* && "$cli_help" == *'default template: {student_id}_{project_title}'* ]]
"$NITE_SUBMIT_CLI" batch "$work_dir/qualified" --out "$reports_dir/batch" --student-id 75589 --dry-run >/dev/null
jq -e 'length == 47 and all(.[]; .fields.document_type != null and (.status == "dry_run" or .status == "review_required"))' "$reports_dir/batch/batch_results.json" >/dev/null
batch_summary=$(jq -r '[length,(map(select(.status=="dry_run"))|length),(map(select(.status=="review_required"))|length),(map(select(.status=="processed"))|length)] | @tsv' "$reports_dir/batch/batch_results.json")
./tools/create_release_dmg.sh --app-ready
./tools/verify_release_artifacts.sh
./tools/write_release_manifest.sh --checks "$test_checks" --batch-summary "$batch_summary"
echo "reports=$reports_dir"
echo 'release-check=pass'
