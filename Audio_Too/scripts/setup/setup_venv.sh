#!/usr/bin/env bash
# Create a single virtualenv at the repo root for website, agents, and Ableton LM.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${AUDIO_TOO_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  else
    PYTHON_BIN="python3"
  fi
fi

PYTHON_MINOR="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PYTHON_MINOR" != "3.12" ]]; then
  echo "Audio_Too requires Python 3.12; $PYTHON_BIN is Python $PYTHON_MINOR." >&2
  echo "Set AUDIO_TOO_PYTHON to a Python 3.12 executable and retry." >&2
  exit 1
fi

if [[ -d .venv ]]; then
  VENV_MINOR="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$VENV_MINOR" != "3.12" ]]; then
    echo "Existing .venv uses Python $VENV_MINOR; Python 3.12 is required." >&2
    echo "Move or remove .venv, then rerun ./audio-too setup." >&2
    exit 1
  fi
fi

if [[ ! -d .venv ]]; then
  echo "Creating .venv in $ROOT"
  "$PYTHON_BIN" -m venv .venv
else
  # Refresh scripts after patch-level Python upgrades. Virtual environments are
  # not relocatable; recreate .venv if the repository itself is moved.
  "$PYTHON_BIN" -m venv --upgrade .venv
fi

VENV_PYTHON="$ROOT/.venv/bin/python"
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt
"$VENV_PYTHON" -m pip install -r requirements-dev.txt
"$VENV_PYTHON" -m pip install -r studio/kenn/kenn/requirements.txt
"$VENV_PYTHON" -m pip install -e studio/audiogen/audiogen
"$VENV_PYTHON" -m pip install -r business/agents/requirements-optional.txt

echo ""
echo "Done. Activate with:"
echo "  source .venv/bin/activate"
echo ""
echo "Next (optional but recommended, ~200MB download): fetch the local"
echo "KENN embedding model and Kokoro TTS voice model. Without these, KENN"
echo "retrieval has no embeddings and voice output silently falls back to"
echo "macOS 'say' with no error telling you why:"
echo "  python main.py fetch-models"
echo ""
if [[ -d business/agents/.venv || -d studio/kenn/kenn/.venv ]]; then
  echo "Old nested venvs detected. Remove them after smoke tests pass:"
  echo "  rm -rf business/agents/.venv studio/kenn/kenn/.venv"
  echo "Or run: python main.py setup --prune-old-venvs"
fi

if [[ "${1:-}" == "--prune-old-venvs" ]]; then
  rm -rf business/agents/.venv studio/kenn/kenn/.venv
  echo "Removed old nested virtual environments"
fi

# Install pre-commit hook
HOOK_SRC="$ROOT/.git-hooks/pre-commit"
HOOK_DST="$ROOT/.git/hooks/pre-commit"
if [[ -f "$HOOK_SRC" ]] && [[ ! -L "$HOOK_DST" ]]; then
  ln -sf ../../.git-hooks/pre-commit "$HOOK_DST"
  echo "Installed pre-commit hook (.git-hooks/pre-commit)"
fi
