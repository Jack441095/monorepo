#!/usr/bin/env bash
set -euo pipefail

PRODUCT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLIST_SRC="${PRODUCT_ROOT}/apps/desktop/launchd/com.shenrendao.kenn.companion.plist"
USER_AGENTS_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${USER_AGENTS_DIR}/com.shenrendao.kenn.companion.plist"

UID_NUM="$(id -u)"

echo "=== Installing KENN Companion macOS LaunchAgent ==="
mkdir -p "${USER_AGENTS_DIR}"

launchctl bootout "gui/${UID_NUM}/com.shenrendao.kenn.companion" 2>/dev/null || true

sed \
  -e "s#<KENN_REPO_ROOT>#${PRODUCT_ROOT}#g" \
  -e "s#<USER_HOME>#${HOME}#g" \
  "${PLIST_SRC}" > "${TARGET_PLIST}"
echo "[*] Installed plist to: ${TARGET_PLIST}"

launchctl bootstrap "gui/${UID_NUM}" "${TARGET_PLIST}"
echo "[✓] KENN Companion background service loaded and active."
echo "    Check status with: launchctl print gui/${UID_NUM}/com.shenrendao.kenn.companion"
