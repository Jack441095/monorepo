#!/usr/bin/env bash
# Gate: no owner's home path, username, or media-library path in a tracked file.
#
# Background. The benchmark result dumps embedded the owner's absolute library
# path once per classified file. Before the 2026-09-30 review that was 168,749
# occurrences across 216 tracked files, publishing their real name, their
# commercial library vendors, and their folder structure. .gitignore now excludes
# that content class, the 157 result dumps are untracked, and the remote GPU host
# root is gone. What remains is dated research and qualification reports.
#
# Those are listed in known_personal_path_debt.txt. This gate fails on any file
# NOT on that list, so the debt cannot grow, and it prints the remaining file and
# occurrence counts on every run so the debt stays visible rather than being
# quietly forgotten. It does not pretend the debt is zero.
#
# History still contains the original data. Rewriting history is an owner
# decision, not something a gate can do; see docs/SLO_REVIEW_V1.md.
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$product_dir"

debt_list="scripts/known_personal_path_debt.txt"
self="scripts/check_no_personal_paths.sh"

# Absolute paths into someone's home directory or their media library. Matched on
# shape, not one literal, so the gate still works on another machine.
patterns=(
  '/Volumes/[A-Za-z0-9._-]+/'
  '/Users/[A-Za-z0-9._-]+/'
  '/home/[A-Za-z0-9._-]+/'
  'mnt/data/'
)

# -E matters: git grep defaults to POSIX basic regex, where a bare `+` is a
# literal plus rather than a quantifier, so the class would never match.
# The script excludes itself, which necessarily contains the patterns.
matches_for() {
    git grep -IlE -- "$1" -- . ":(exclude)$self" 2>/dev/null || true
}

status=0
seen="$(mktemp)"
trap 'rm -f "$seen"' EXIT

for pattern in "${patterns[@]}"; do
    hits="$(matches_for "$pattern")"
    [ -n "$hits" ] || continue

    if [ -f "$debt_list" ]; then
        new="$(printf '%s\n' "$hits" | grep -vxF -f "$debt_list" || true)"
        printf '%s\n' "$hits" | grep -xF -f "$debt_list" >> "$seen" || true
    else
        new="$hits"
        printf '%s\n' "$hits" >> "$seen"
    fi

    if [ -n "$new" ]; then
        echo "NEW personal path matching '$pattern' in a file not on the debt list:" >&2
        printf '%s\n' "$new" >&2
        status=1
    fi
done

tracked="$(git ls-files | wc -l | tr -d ' ')"

if [ "$status" -ne 0 ]; then
    echo >&2
    echo "personal-path-gate=FAIL" >&2
    echo "Add a regenerable file to .gitignore, or scrub the path before committing." >&2
    echo "If it is an accepted exception, add it to $debt_list -- the list is the" >&2
    echo "record of what we already tolerate, not a pardon." >&2
    exit 1
fi

debt_files="$(sort -u "$seen" | grep -c . || true)"
debt_hits=0
if [ "$debt_files" -gt 0 ]; then
    debt_hits="$(sort -u "$seen" | tr '\n' '\0' \
        | xargs -0 grep -hoE '/Volumes/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|mnt/data/' 2>/dev/null \
        | wc -l | tr -d ' ')"
    echo "personal-path-gate=pass tracked_files=$tracked known_debt_files=$debt_files known_debt_hits=$debt_hits"
    echo "  ^ known debt on $debt_files files ($debt_hits occurrences), listed in $debt_list."
    echo "    It cannot grow. It has not been scrubbed, and it is still in git history."
else
    echo "personal-path-gate=pass tracked_files=$tracked known_debt_files=0 known_debt_hits=0"
fi
