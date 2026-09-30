#!/usr/bin/env bash
# Gate: no owner's home path, username, or library vendor may reach a tracked file.
#
# The benchmark result dumps embed the owner's absolute library path once per
# classified file. Before the 2026-09-30 review that was 168,749 occurrences
# across 216 tracked files, which publishes their real name, their commercial
# library vendors, and their folder structure. .gitignore now excludes that
# content class, but an ignore rule only helps for files not yet added, so this
# gate covers the tracked tree as well.
#
# The history still contains the data. Rewriting history is an owner decision,
# not something a pre-commit gate can do; see docs/SLO_REVIEW_V1.md.
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$product_dir"

# Anything matching these is an absolute path into someone's home directory or
# their media library. Match on the shape, not one literal, so the gate still
# works on another machine.
patterns=(
  '/Volumes/[A-Za-z0-9._-]+/'
  '/Users/[A-Za-z0-9._-]+/'
  '/home/[A-Za-z0-9._-]+/'
  'mnt/data/'
  'claude-usage'
)

status=0
for pattern in "${patterns[@]}"; do
  # Only tracked files: the whole point is catching what is already in the index.
  if hits="$(git grep -Il -- "$pattern" -- . 2>/dev/null)"; then
    if [ -n "$hits" ]; then
      count="$(printf '%s\n' "$hits" | wc -l | tr -d ' ')"
      echo "tracked file(s) containing a personal path matching '$pattern':" >&2
      printf '%s\n' "$hits" | head -20 >&2
      if [ "$count" -gt 20 ]; then
        echo "  ... and $((count - 20)) more" >&2
      fi
      status=1
    fi
  fi
done

if [ "$status" -ne 0 ]; then
  echo >&2
  echo "personal-path-gate=FAIL" >&2
  echo "Add the file to .gitignore if it is regenerable, or scrub the paths before" >&2
  echo "committing. Do not commit absolute paths into anyone's home or library." >&2
  exit 1
fi

tracked="$(git ls-files | wc -l | tr -d ' ')"
echo "personal-path-gate=pass tracked_files=$tracked"
