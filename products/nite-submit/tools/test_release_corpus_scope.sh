#!/bin/zsh
set -euo pipefail

fixture_root=$(mktemp -d /tmp/nite-submit-corpus-scope.XXXXXX)
trap 'rm -rf "$fixture_root"' EXIT

corpus="$fixture_root/real_validation_corpus"
stage="$fixture_root/stage"
mkdir -p "$corpus/public_examples" \
         "$corpus/beta_intake" \
         "$corpus/rejected" \
         "$corpus/edge_cases" \
         "$corpus/test_results" \
         "$stage"

touch "$corpus/public_examples/approved.pdf" \
      "$corpus/beta_intake/private.pdf" \
      "$corpus/rejected/rejected.pdf" \
      "$corpus/edge_cases/edge.pdf" \
      "$corpus/test_results/generated.pdf"

find "$corpus" -type f -name '*.pdf' \
  -not -path '*/test_results/*' \
  -not -path '*/rejected/*' \
  -not -path '*/edge_cases/*' \
  -not -path '*/beta_intake/*' \
  -exec ln -s {} "$stage/" \;

staged=$(find "$stage" -type l -exec basename {} \; | sort)
[[ "$staged" == "approved.pdf" ]] || {
  echo "Release corpus scope test failed: staged files were: $staged" >&2
  exit 1
}

echo "Release corpus scope check passed: private beta intake is excluded."
