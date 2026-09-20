#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_ROOT="${KENN_PLUGIN_BUILD_ROOT:-${REPO_ROOT}/build/plugins/kenn-vst3-au/KENNMixAssistant_artefacts/Release}"
VST3_SOURCE="${BUILD_ROOT}/VST3/KENN Mix Assistant.vst3"
AU_SOURCE="${BUILD_ROOT}/AU/KENN Mix Assistant.component"
OUTPUT_DIR="${KENN_PLUGIN_OUTPUT_DIR:-${REPO_ROOT}/dist}"
VERSION="${1:-0.1.0}"

echo "Packaging KENN Mix Assistant v${VERSION} for macOS..."

if [[ ! -d "${VST3_SOURCE}" ]]; then
    # Fallback to arm64 build directory if present
    if [[ -d "${REPO_ROOT}/build/plugins/kenn-vst3-au-arm64/KENNMixAssistant_artefacts/VST3/KENN Mix Assistant.vst3" ]]; then
        BUILD_ROOT="${REPO_ROOT}/build/plugins/kenn-vst3-au-arm64/KENNMixAssistant_artefacts"
        VST3_SOURCE="${BUILD_ROOT}/VST3/KENN Mix Assistant.vst3"
        AU_SOURCE="${BUILD_ROOT}/AU/KENN Mix Assistant.component"
    else
        echo "Error: VST3 source artifact not found at ${VST3_SOURCE}" >&2
        exit 1
    fi
fi

STAGING_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/kenn-dist-package.XXXXXX")"
cleanup() {
    rm -rf "${STAGING_ROOT}"
}
trap cleanup EXIT

PACKAGE_ROOT="${STAGING_ROOT}/KENN Mix Assistant ${VERSION}"
mkdir -p "${PACKAGE_ROOT}/VST3" "${PACKAGE_ROOT}/Components"

echo "Copying plug-in bundles..."
ditto "${VST3_SOURCE}" "${PACKAGE_ROOT}/VST3/KENN Mix Assistant.vst3"
if [[ -d "${AU_SOURCE}" ]]; then
    ditto "${AU_SOURCE}" "${PACKAGE_ROOT}/Components/KENN Mix Assistant.component"
fi

echo "Signing plug-in bundles with ad-hoc signature..."
codesign --force --deep --sign - "${PACKAGE_ROOT}/VST3/KENN Mix Assistant.vst3"
if [[ -d "${PACKAGE_ROOT}/Components/KENN Mix Assistant.component" ]]; then
    codesign --force --deep --sign - "${PACKAGE_ROOT}/Components/KENN Mix Assistant.component"
fi

# Add installation script
cat <<'EOF' > "${PACKAGE_ROOT}/install.sh"
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VST3_DEST="${HOME}/Library/Audio/Plug-Ins/VST3"
AU_DEST="${HOME}/Library/Audio/Plug-Ins/Components"

mkdir -p "${VST3_DEST}" "${AU_DEST}"

echo "Installing KENN Mix Assistant VST3 to ${VST3_DEST}..."
ditto "${SCRIPT_DIR}/VST3/KENN Mix Assistant.vst3" "${VST3_DEST}/KENN Mix Assistant.vst3"
codesign --force --deep --sign - "${VST3_DEST}/KENN Mix Assistant.vst3" >/dev/null 2>&1 || true

if [[ -d "${SCRIPT_DIR}/Components/KENN Mix Assistant.component" ]]; then
    echo "Installing KENN Mix Assistant Audio Unit (AU) to ${AU_DEST}..."
    ditto "${SCRIPT_DIR}/Components/KENN Mix Assistant.component" "${AU_DEST}/KENN Mix Assistant.component"
    codesign --force --deep --sign - "${AU_DEST}/KENN Mix Assistant.component" >/dev/null 2>&1 || true
fi

echo "Installation complete!"
echo "Please restart your DAW (Ableton Live, Logic Pro, Reaper) to load the plug-in."
EOF
chmod +x "${PACKAGE_ROOT}/install.sh"

# Add README
cat <<EOF > "${PACKAGE_ROOT}/README.txt"
================================================================================
KENN Mix Assistant v${VERSION} - macOS Release
================================================================================

KENN Mix Assistant is an AI-powered mixing assistant and DAW bridge for Ableton
Live 12 and other standard VST3 / Audio Unit hosts.

SYSTEM REQUIREMENTS:
- macOS 13 (Ventura) or later (Apple Silicon native & Intel universal)
- Ableton Live 11 / 12, Logic Pro, or any VST3 / Audio Unit compatible host
- KENN Local Server (running at http://127.0.0.1:8090)

MANUAL INSTALLATION:
1. Copy "VST3/KENN Mix Assistant.vst3" to:
   ~/Library/Audio/Plug-Ins/VST3/

2. Copy "Components/KENN Mix Assistant.component" to:
   ~/Library/Audio/Plug-Ins/Components/

OR AUTOMATED INSTALLATION:
Run ./install.sh from this directory in Terminal.

DAW SETUP (Ableton Live 12):
1. In Ableton Live, ensure OSC communication is enabled on UDP 11000/11001.
2. Insert "KENN Mix Assistant" onto your Master or sub-bus track.
3. Start the KENN server companion:
   ./tooling/scripts/start_server.sh
4. Open the plug-in UI. Verify that the status reports "Connected to KENN (8090)".
5. Use "Show Live Controls" to inspect current tracks and parameters, or ask
   mix questions via the Ask panel.

================================================================================
EOF

ARCHIVE_NAME="KENN-Mix-Assistant-${VERSION}-macOS.zip"
mkdir -p "${OUTPUT_DIR}"
ARCHIVE_PATH="${OUTPUT_DIR}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"

echo "Creating zip archive: ${ARCHIVE_NAME}..."
ditto -c -k --sequesterRsrc --keepParent "${PACKAGE_ROOT}" "${ARCHIVE_PATH}"

echo "Calculating SHA-256 checksum..."
shasum -a 256 "${ARCHIVE_PATH}" > "${CHECKSUM_PATH}"

echo ""
echo "================================================================================"
echo "Successfully created release archive:"
echo "Archive:  ${ARCHIVE_PATH} ($(du -h "${ARCHIVE_PATH}" | awk '{print $1}'))"
echo "Checksum: ${CHECKSUM_PATH}"
echo "Contents:"
unzip -l "${ARCHIVE_PATH}" | head -n 25
echo "..."
echo "================================================================================"
