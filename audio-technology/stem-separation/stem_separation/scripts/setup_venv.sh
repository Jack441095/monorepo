#!/usr/bin/env bash
# Create .venv and install project deps (cloud/Linux: needs python3-venv).
# Mirrors studio/audiogen/audiogen/scripts/setup_venv.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! python3 -c "import venv" 2>/dev/null; then
  echo "python3-venv is missing. On Debian/Ubuntu run:" >&2
  echo "  sudo apt-get install -y python3.12-venv python3-pip" >&2
  exit 1
fi

rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"
echo "Done. Activate with: source .venv/bin/activate"
echo "First run will download the htdemucs model (~80MB) into torch's cache."
