#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"

git_bin=$(command -v git)
branch=$($git_bin branch --show-current)
[[ -n "$branch" ]] || { echo "Public releases require a named branch." >&2; exit 1; }

dirty=$($git_bin status --porcelain -- . \
  ':(exclude)artifacts' ':(exclude)real_validation_corpus/test_results')
[[ -z "$dirty" ]] || {
  echo "Public release refused: source checkout is not clean." >&2
  printf '%s\n' "$dirty" >&2
  exit 1
}

echo "Public release source gate passed: $branch at $($git_bin rev-parse HEAD)."
