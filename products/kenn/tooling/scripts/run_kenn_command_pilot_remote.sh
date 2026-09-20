#!/usr/bin/env bash
set -euo pipefail

# Ship the allow-listed command-training subset to a remote compute host and
# run the guarded command-model pilot there. This script never receives,
# stores, or prints a password. SSH may prompt through the user's configured
# authentication flow.

usage() {
  cat <<'EOF'
Usage: tooling/scripts/run_kenn_command_pilot_remote.sh [options]

Options:
  --host HOST             Remote host (default: www.haoee.com)
  --user USER             Remote user (default: ubuntu)
  --port PORT             SSH port (default: 2022)
  --identity-file PATH    SSH private key to use (optional)
  --remote-workdir PATH   Empty remote pilot directory (default: generated /tmp path)
  --run                   Train and evaluate after preflight (default: preflight only)
  --allow-download        Allow Transformers to download the base model remotely
  -h, --help              Show this help

The local repository must be clean. Only the committed training scripts,
deterministic parser modules, and synthetic shadow fixture are archived and
sent over SSH; Git credentials, local secrets, project notes, and uncommitted
files are not copied. The remote pilot itself refuses to overwrite existing
artifacts.
EOF
}

host="www.haoee.com"
user="ubuntu"
port="2022"
identity_file=""
remote_workdir="/tmp/kenn-command-pilot-$(date -u +%Y%m%d-%H%M%S)"
run_training=0
allow_download=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || { echo "--host requires a value" >&2; exit 2; }
      host="$2"
      shift 2
      ;;
    --user)
      [[ $# -ge 2 ]] || { echo "--user requires a value" >&2; exit 2; }
      user="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "--port requires a value" >&2; exit 2; }
      port="$2"
      shift 2
      ;;
    --identity-file)
      [[ $# -ge 2 ]] || { echo "--identity-file requires a value" >&2; exit 2; }
      identity_file="$2"
      shift 2
      ;;
    --remote-workdir)
      [[ $# -ge 2 ]] || { echo "--remote-workdir requires a value" >&2; exit 2; }
      remote_workdir="$2"
      shift 2
      ;;
    --run)
      run_training=1
      shift
      ;;
    --allow-download)
      allow_download=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to ship a dirty worktree; commit or stash local changes first." >&2
  exit 2
fi

ssh_target="${user}@${host}"
ssh_opts=(-p "$port" -o PreferredAuthentications=publickey,password)
if [[ -n "$identity_file" ]]; then
  [[ -f "$identity_file" ]] || { echo "SSH identity file does not exist: $identity_file" >&2; exit 2; }
  ssh_opts+=(-i "$identity_file" -o IdentitiesOnly=yes)
fi
remote_q="$(printf '%q' "$remote_workdir")"

echo "Checking SSH access to ${ssh_target}:${port}..."
ssh "${ssh_opts[@]}" "$ssh_target" "mkdir -p ${remote_q}"

training_paths=(
  apps/backend/requirements-training.txt
  tooling/scripts/audit_kenn_command_corpus.py
  tooling/scripts/build_kenn_command_corpus.py
  tooling/scripts/build_kenn_command_training.py
  tooling/scripts/evaluate_kenn_command_lora.py
  tooling/scripts/run_kenn_command_pilot.py
  tooling/scripts/train_kenn_command_lora.py
  apps/backend/src/kenn/__init__.py
  apps/backend/src/kenn/ableton_osc_bridge.py
  apps/backend/src/kenn/abletonosc_protocol.py
  apps/backend/src/kenn/core/__init__.py
  apps/backend/src/kenn/core/confirmation.py
  apps/backend/src/kenn/core/device_units.py
  apps/backend/src/kenn/core/live_action_service.py
  apps/backend/src/kenn/core/live_command.py
  apps/backend/src/kenn/core/live_intent.py
  apps/backend/src/kenn/core/live_recipe.py
  apps/backend/src/kenn/evals/ableton_llm_shadow_holdout.json
  apps/backend/src/kenn/training/__init__.py
  apps/backend/src/kenn/training/training_records.py
)
for path in "${training_paths[@]}"; do
  git ls-files --error-unmatch -- "$path" >/dev/null
done

echo "Shipping the allow-listed training subset from committed HEAD $(git rev-parse --short HEAD) to ${ssh_target}:${remote_workdir}..."
git archive --format=tar HEAD -- "${training_paths[@]}" | ssh "${ssh_opts[@]}" "$ssh_target" "tar -xf - -C ${remote_q}"

echo "Installing the isolated training environment on the remote host..."
ssh "${ssh_opts[@]}" "$ssh_target" "cd ${remote_q} && python3 -m venv .venv-kenn-training && . .venv-kenn-training/bin/activate && python -m pip install --upgrade pip && python -m pip install -r apps/backend/requirements-training.txt"

pilot_args=(
  --workdir "${remote_workdir}/pilot"
  --device cuda
)
if [[ "$run_training" -eq 1 ]]; then
  pilot_args+=(--run)
fi
if [[ "$allow_download" -eq 1 ]]; then
  pilot_args+=(--allow-download)
fi

pilot_command="PYTHONPATH=apps/backend/src python tooling/scripts/run_kenn_command_pilot.py"
for arg in "${pilot_args[@]}"; do
  pilot_command+=" $(printf '%q' "$arg")"
done

echo "Running KENN command pilot remotely (run=${run_training}, allow_download=${allow_download})..."
ssh "${ssh_opts[@]}" "$ssh_target" "cd ${remote_q} && . .venv-kenn-training/bin/activate && ${pilot_command}"

echo "Remote pilot completed. Artifacts remain at ${ssh_target}:${remote_workdir}/pilot"
