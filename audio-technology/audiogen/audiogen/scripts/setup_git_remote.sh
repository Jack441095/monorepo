#!/usr/bin/env bash
# Configure origin for this repo and show push commands.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_URL="${1:-}"

if [[ -z "${REMOTE_URL}" ]]; then
  echo "Usage: $0 <git-remote-url>" >&2
  echo "  e.g. $0 git@github.com:Ganders4/LLM_AudioGen_Markov_FineTune_01.git" >&2
  echo "  e.g. $0 https://github.com/Ganders4/LLM_AudioGen_Markov_FineTune_01.git" >&2
  exit 1
fi

if [[ "${REMOTE_URL}" == *YOUR_USER* ]] || [[ "${REMOTE_URL}" == *YOUR_REPO* ]]; then
  echo "Error: replace YOUR_USER and YOUR_REPO with your real GitHub path." >&2
  exit 1
fi

if git remote get-url origin &>/dev/null; then
  echo "Updating existing origin:"
  git remote set-url origin "${REMOTE_URL}"
else
  echo "Adding origin:"
  git remote add origin "${REMOTE_URL}"
fi

echo ""
git remote -v
echo ""
echo "Current branch: $(git branch --show-current)"
echo ""
echo "Push commands:"
echo "  git push -u origin main"
echo "  git push -u origin wip/markov-audio-refactor"
echo ""
if [[ "${REMOTE_URL}" == git@github.com:* ]]; then
  echo "SSH test: ssh -T git@github.com"
else
  echo "HTTPS: use a Personal Access Token as the password when prompted."
fi
