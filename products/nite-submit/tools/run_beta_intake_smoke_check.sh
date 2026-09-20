#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
manifest="$product_dir/real_validation_corpus/manifests/first_wave_manifest_v2.json"
work_dir=$(mktemp -d /tmp/nite-submit-beta-intake-smoke.XXXXXX)
trap 'rm -R -- "$work_dir"' EXIT
out="$work_dir/validation_results.json"

./tools/run_beta_intake.sh "$manifest" "$out" >/dev/null

jq -e '
  .processed == 21 and
  .encrypted_or_unreadable == 0 and
  .failed_missing_files == 0 and
  .wrong_high_confidence_total == 0 and
  (.privacy_note | contains("no document text or personal values")) and
  ((keys | sort) == ["corpus_id", "encrypted_or_unreadable", "failed_missing_files", "fields", "latency_max_s", "latency_p50_s", "latency_p95_s", "latency_p99_s", "privacy_note", "processed", "wrong_high_confidence_total"])
' "$out" >/dev/null

echo "Beta intake smoke check passed: aggregate-only output for 21 public fixtures."
