#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

usage() {
  cat <<'EOF'
Safe repo pruning helper (dry-run by default).

Usage:
  bash scripts/prune_repo_fat.sh [options]

Options:
  --apply                          Execute deletions (default is dry-run)
  --keep-tags N                    Keep newest N dataset tags (default: 3)
  --protect-tags "tag1 tag2 ..."   Space-separated tags to never delete
  --prune-artifacts                Prune old tag-linked artifacts (datasets/reports/runs/models/manifests)
  --prune-cache                    Remove .cache/sample_cache_v2 if present
  --prune-logs                     Remove large note logs (logs/note_log.csv and *.csv.gz in logs/archive older than keep count)
  --keep-log-archives N            Keep newest N compressed note log archives (default: 5)
  --prune-pycache                  Remove __pycache__ folders under repo
  --prune-pytest-cache             Remove .pytest_cache
  --help                           Show this help

Examples:
  # Preview what would be deleted:
  bash scripts/prune_repo_fat.sh --prune-artifacts --prune-cache --prune-logs

  # Actually delete (safe policy):
  bash scripts/prune_repo_fat.sh --apply --prune-artifacts --keep-tags 4 --protect-tags "v013_newset primary" --prune-cache --prune-logs
EOF
}

APPLY=0
KEEP_TAGS=3
KEEP_LOG_ARCHIVES=5
PROTECT_TAGS_RAW=""
PRUNE_ARTIFACTS=0
PRUNE_CACHE=0
PRUNE_LOGS=0
PRUNE_PYCACHE=0
PRUNE_PYTEST_CACHE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      shift
      ;;
    --keep-tags)
      KEEP_TAGS="${2:-3}"
      shift 2
      ;;
    --protect-tags)
      PROTECT_TAGS_RAW="${2:-}"
      shift 2
      ;;
    --prune-artifacts)
      PRUNE_ARTIFACTS=1
      shift
      ;;
    --prune-cache)
      PRUNE_CACHE=1
      shift
      ;;
    --prune-logs)
      PRUNE_LOGS=1
      shift
      ;;
    --keep-log-archives)
      KEEP_LOG_ARCHIVES="${2:-5}"
      shift 2
      ;;
    --prune-pycache)
      PRUNE_PYCACHE=1
      shift
      ;;
    --prune-pytest-cache)
      PRUNE_PYTEST_CACHE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if ! [[ "${KEEP_TAGS}" =~ ^[0-9]+$ ]]; then
  echo "--keep-tags must be a non-negative integer." >&2
  exit 2
fi
if ! [[ "${KEEP_LOG_ARCHIVES}" =~ ^[0-9]+$ ]]; then
  echo "--keep-log-archives must be a non-negative integer." >&2
  exit 2
fi

run_or_echo() {
  if [[ "${APPLY}" -eq 1 ]]; then
    "$@"
  else
    echo "DRY-RUN: $*"
  fi
}

echo "== Repo size snapshot =="
du -sh .[!.]* * 2>/dev/null | sort -h || true
echo ""

declare -a PROTECT_TAGS=()
if [[ -n "${PROTECT_TAGS_RAW}" ]]; then
  # shellcheck disable=SC2206
  PROTECT_TAGS=(${PROTECT_TAGS_RAW})
fi

tag_is_protected() {
  local t="$1"
  for p in "${PROTECT_TAGS[@]:-}"; do
    if [[ "${p}" == "${t}" ]]; then
      return 0
    fi
  done
  return 1
}

if [[ "${PRUNE_ARTIFACTS}" -eq 1 ]]; then
  echo "== Artifact tag pruning =="
  DATASET_DIR="artifacts/datasets/live_melody"
  if [[ ! -d "${DATASET_DIR}" ]]; then
    echo "No dataset dir: ${DATASET_DIR}"
  else
    TAGS=()
    while IFS= read -r line; do
      [[ -n "${line}" ]] && TAGS+=("${line}")
    done < <(ls -1t "${DATASET_DIR}" 2>/dev/null || true)
    echo "Found tags (${#TAGS[@]}): ${TAGS[*]:-}"
    for i in "${!TAGS[@]}"; do
      tag="${TAGS[$i]}"
      if [[ "${i}" -lt "${KEEP_TAGS}" ]]; then
        continue
      fi
      if tag_is_protected "${tag}"; then
        echo "KEEP (protected): ${tag}"
        continue
      fi
      echo "PRUNE TAG: ${tag}"
      run_or_echo rm -rf "artifacts/datasets/live_melody/${tag}"
      run_or_echo rm -rf "artifacts/reports/${tag}"
      run_or_echo rm -rf "artifacts/runs/offline_training/${tag}"
      run_or_echo rm -rf "artifacts/models/${tag}"
      run_or_echo rm -f "artifacts/manifests/${tag}.json"
    done
  fi
  echo ""
fi

if [[ "${PRUNE_CACHE}" -eq 1 ]]; then
  echo "== Cache pruning =="
  if [[ -d ".cache/sample_cache_v2" ]]; then
    run_or_echo rm -rf ".cache/sample_cache_v2"
  else
    echo "No .cache/sample_cache_v2 found."
  fi
  echo ""
fi

if [[ "${PRUNE_LOGS}" -eq 1 ]]; then
  echo "== Log pruning =="
  mkdir -p "logs/archive"
  if [[ -f "logs/note_log.csv" ]]; then
    ts="$(date -u +%Y%m%d_%H%M%S)"
    arch="logs/archive/note_log_${ts}.csv"
    if [[ "${APPLY}" -eq 1 ]]; then
      mv "logs/note_log.csv" "${arch}"
      gzip -9 "${arch}"
      : > "logs/note_log.csv"
      echo "Archived + reset note log: ${arch}.gz"
    else
      echo "DRY-RUN: mv logs/note_log.csv ${arch} && gzip -9 ${arch} && truncate logs/note_log.csv"
    fi
  else
    echo "No logs/note_log.csv found."
  fi

  ARCHIVES=()
  while IFS= read -r line; do
    [[ -n "${line}" ]] && ARCHIVES+=("${line}")
  done < <(ls -1t logs/archive/note_log_*.csv.gz 2>/dev/null || true)
  for i in "${!ARCHIVES[@]}"; do
    if [[ "${i}" -lt "${KEEP_LOG_ARCHIVES}" ]]; then
      continue
    fi
    run_or_echo rm -f "${ARCHIVES[$i]}"
  done
  echo ""
fi

if [[ "${PRUNE_PYCACHE}" -eq 1 ]]; then
  echo "== __pycache__ pruning =="
  if [[ "${APPLY}" -eq 1 ]]; then
    python3 - <<'PY'
from pathlib import Path
root = Path(".")
count = 0
for p in root.rglob("__pycache__"):
    if p.is_dir():
        for child in sorted(p.rglob("*"), reverse=True):
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            except Exception:
                pass
        try:
            p.rmdir()
            count += 1
        except Exception:
            pass
print(f"Removed __pycache__ dirs: {count}")
PY
  else
    echo "DRY-RUN: remove __pycache__ directories recursively"
  fi
  echo ""
fi

if [[ "${PRUNE_PYTEST_CACHE}" -eq 1 ]]; then
  echo "== pytest cache pruning =="
  if [[ -d ".pytest_cache" ]]; then
    run_or_echo rm -rf ".pytest_cache"
  else
    echo "No .pytest_cache found."
  fi
  echo ""
fi

echo "== Post-prune snapshot =="
du -sh .[!.]* * 2>/dev/null | sort -h || true
echo ""
if [[ "${APPLY}" -eq 1 ]]; then
  echo "Prune complete."
else
  echo "Dry-run complete. Re-run with --apply to execute."
fi
