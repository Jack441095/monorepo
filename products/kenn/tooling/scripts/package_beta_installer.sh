#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# KENN Mix Assistant - Native macOS .pkg Universal Installer Generator
# ==============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-0.5.0}"
OUTPUT_DIR="${KENN_PKG_OUTPUT_DIR:-${REPO_ROOT}/dist}"
SIGNING_IDENTITY="${KENN_INSTALLER_IDENTITY:-}"
NOTARY_PROFILE="${KENN_NOTARY_PROFILE:-}"

# Locate source plug-ins
BUILD_ROOT="${KENN_PLUGIN_BUILD_ROOT:-${REPO_ROOT}/build/plugins/kenn-vst3-au/KENNMixAssistant_artefacts/Release}"
VST3_SRC="${BUILD_ROOT}/VST3/KENN Mix Assistant.vst3"
AU_SRC="${BUILD_ROOT}/AU/KENN Mix Assistant.component"

if [[ ! -d "${VST3_SRC}" ]]; then
    if [[ -d "${HOME}/Library/Audio/Plug-Ins/VST3/KENN Mix Assistant.vst3" ]]; then
        VST3_SRC="${HOME}/Library/Audio/Plug-Ins/VST3/KENN Mix Assistant.vst3"
        AU_SRC="${HOME}/Library/Audio/Plug-Ins/Components/KENN Mix Assistant.component"
    else
        echo "[-] Error: VST3 source artifact not found at ${VST3_SRC}" >&2
        exit 1
    fi
fi

echo "================================================================================"
echo " Packaging KENN Mix Assistant Universal Installer (macOS .pkg)"
echo " Version:  ${VERSION}"
echo " Source:   ${VST3_SRC}"
echo " Output:   ${OUTPUT_DIR}"
echo "================================================================================"

STAGING_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/kenn-pkg-staging.XXXXXX")"
cleanup() {
    rm -rf "${STAGING_ROOT}"
}
trap cleanup EXIT

mkdir -p "${STAGING_ROOT}/pkg_vst3" "${STAGING_ROOT}/pkg_au" "${STAGING_ROOT}/pkg_support"
mkdir -p "${STAGING_ROOT}/scripts_support" "${STAGING_ROOT}/packages" "${OUTPUT_DIR}"

# 1. Stage VST3 Component
echo "[1/5] Staging VST3 plugin..."
ditto "${VST3_SRC}" "${STAGING_ROOT}/pkg_vst3/KENN Mix Assistant.vst3"
codesign --force --deep --sign - "${STAGING_ROOT}/pkg_vst3/KENN Mix Assistant.vst3" 2>/dev/null || true

# 2. Stage AU Component
echo "[2/5] Staging Audio Unit (AU) plugin..."
if [[ -d "${AU_SRC}" ]]; then
    ditto "${AU_SRC}" "${STAGING_ROOT}/pkg_au/KENN Mix Assistant.component"
    codesign --force --deep --sign - "${STAGING_ROOT}/pkg_au/KENN Mix Assistant.component" 2>/dev/null || true
fi

# 3. Stage Support Files (Remote Scripts & Demo)
echo "[3/5] Staging Remote Scripts & Demo Project..."
SUPPORT_DIR="${STAGING_ROOT}/pkg_support"
mkdir -p "${SUPPORT_DIR}/Remote Scripts" "${SUPPORT_DIR}/Demo"

if [[ -d "${REPO_ROOT}/integrations/ableton-remote-script/KENN_Bridge" ]]; then
    ditto "${REPO_ROOT}/integrations/ableton-remote-script/KENN_Bridge" "${SUPPORT_DIR}/Remote Scripts/KENN_Bridge"
fi
if [[ -d "${REPO_ROOT}/integrations/ableton-osc" ]]; then
    ditto "${REPO_ROOT}/integrations/ableton-osc" "${SUPPORT_DIR}/Remote Scripts/AbletonOSC"
fi
if [[ -f "${REPO_ROOT}/assets/demo/KENN_Live12_Demo.als" ]]; then
    cp "${REPO_ROOT}/assets/demo/KENN_Live12_Demo.als" "${SUPPORT_DIR}/Demo/"
fi
if [[ -f "${REPO_ROOT}/assets/demo/README.md" ]]; then
    cp "${REPO_ROOT}/assets/demo/README.md" "${SUPPORT_DIR}/Demo/"
fi

# Write postinstall script
cat <<'EOF' > "${STAGING_ROOT}/scripts_support/postinstall"
#!/bin/bash
set -e

# Detect GUI console user (macOS installer runs as root)
CONSOLE_USER=$(stat -f '%Su' /dev/console 2>/dev/null || echo "$USER")
if [[ "$CONSOLE_USER" == "root" || -z "$CONSOLE_USER" ]]; then
    CONSOLE_USER=$(who | awk '/console/{print $1}' | head -n 1)
fi

if [[ -n "$CONSOLE_USER" && "$CONSOLE_USER" != "root" ]]; then
    USER_HOME=$(eval echo "~$CONSOLE_USER")
else
    USER_HOME="$HOME"
fi

SUPPORT_SRC="/Library/Application Support/KENN/Remote Scripts"
USER_REMOTE_SCRIPTS="${USER_HOME}/Music/Ableton/User Library/Remote Scripts"

# Install Remote Scripts to User Library
if [[ -d "$SUPPORT_SRC" ]]; then
    mkdir -p "$USER_REMOTE_SCRIPTS"
    if [[ -d "$SUPPORT_SRC/KENN_Bridge" ]]; then
        rm -rf "$USER_REMOTE_SCRIPTS/KENN_Bridge"
        cp -R "$SUPPORT_SRC/KENN_Bridge" "$USER_REMOTE_SCRIPTS/"
    fi
    if [[ -d "$SUPPORT_SRC/AbletonOSC" ]]; then
        rm -rf "$USER_REMOTE_SCRIPTS/AbletonOSC"
        cp -R "$SUPPORT_SRC/AbletonOSC" "$USER_REMOTE_SCRIPTS/"
    fi
    if [[ -n "$CONSOLE_USER" && "$CONSOLE_USER" != "root" ]]; then
        chown -R "$CONSOLE_USER" "$USER_REMOTE_SCRIPTS/KENN_Bridge" "$USER_REMOTE_SCRIPTS/AbletonOSC" 2>/dev/null || true
    fi
fi

# Also link/copy to any installed Ableton Live application bundles
for app_dir in /Applications/Ableton\ Live*.app/Contents/App-Resources/MIDI\ Remote\ Scripts; do
    if [[ -d "$app_dir" && -d "$SUPPORT_SRC" ]]; then
        cp -R "$SUPPORT_SRC/KENN_Bridge" "$app_dir/" 2>/dev/null || true
        cp -R "$SUPPORT_SRC/AbletonOSC" "$app_dir/" 2>/dev/null || true
    fi
done

# Clear quarantine flags on plugins
xattr -dr com.apple.quarantine "/Library/Audio/Plug-Ins/VST3/KENN Mix Assistant.vst3" 2>/dev/null || true
xattr -dr com.apple.quarantine "/Library/Audio/Plug-Ins/Components/KENN Mix Assistant.component" 2>/dev/null || true

exit 0
EOF
chmod +x "${STAGING_ROOT}/scripts_support/postinstall"

# 4. Build Component Packages using pkgbuild
echo "[4/5] Building component packages with pkgbuild..."
pkgbuild --root "${STAGING_ROOT}/pkg_vst3" \
         --identifier "com.nitedsp.kenn.pkg.vst3" \
         --version "${VERSION}" \
         --install-location "/Library/Audio/Plug-Ins/VST3" \
         "${STAGING_ROOT}/packages/kenn-vst3.pkg"

if [[ -d "${AU_SRC}" ]]; then
    pkgbuild --root "${STAGING_ROOT}/pkg_au" \
             --identifier "com.nitedsp.kenn.pkg.au" \
             --version "${VERSION}" \
             --install-location "/Library/Audio/Plug-Ins/Components" \
             "${STAGING_ROOT}/packages/kenn-au.pkg"
fi

pkgbuild --root "${STAGING_ROOT}/pkg_support" \
         --scripts "${STAGING_ROOT}/scripts_support" \
         --identifier "com.nitedsp.kenn.pkg.support" \
         --version "${VERSION}" \
         --install-location "/Library/Application Support/KENN" \
         "${STAGING_ROOT}/packages/kenn-support.pkg"

# 5. Synthesize Distribution XML and Build Final Product Package
echo "[5/5] Synthesizing distribution package with productbuild..."
DIST_XML="${STAGING_ROOT}/distribution.xml"

productbuild --synthesize \
             --package "${STAGING_ROOT}/packages/kenn-vst3.pkg" \
             --package "${STAGING_ROOT}/packages/kenn-au.pkg" \
             --package "${STAGING_ROOT}/packages/kenn-support.pkg" \
             "${DIST_XML}"

# Customize Distribution XML with Title
python3 - <<PYEOF
import re
with open("${DIST_XML}", "r") as f:
    content = f.read()

title_tag = "<title>KENN Mix Assistant v${VERSION}</title>\n"
if "<installer-gui-script" in content:
    content = re.sub(r"(<installer-gui-script[^>]*>)", r"\1\n    " + title_tag, content)

with open("${DIST_XML}", "w") as f:
    f.write(content)
PYEOF

FINAL_PKG="${OUTPUT_DIR}/KENN_Mix_Assistant_v${VERSION}.pkg"
CHECKSUM_FILE="${FINAL_PKG}.sha256"

productbuild --distribution "${DIST_XML}" \
             --package-path "${STAGING_ROOT}/packages" \
             "${FINAL_PKG}"

# Developer ID signing if identity provided
if [[ -n "${SIGNING_IDENTITY}" ]]; then
    echo "Signing package with Developer ID Installer identity: ${SIGNING_IDENTITY}..."
    SIGNED_PKG="${OUTPUT_DIR}/KENN_Mix_Assistant_v${VERSION}-signed.pkg"
    productsign --sign "${SIGNING_IDENTITY}" "${FINAL_PKG}" "${SIGNED_PKG}"
    mv "${SIGNED_PKG}" "${FINAL_PKG}"


    if [[ -n "${NOTARY_PROFILE}" ]]; then
        echo "Submitting to Apple notarytool..."
        xcrun notarytool submit "${FINAL_PKG}" --keychain-profile "${NOTARY_PROFILE}" --wait
        xcrun stapler staple "${FINAL_PKG}"
    fi
fi

# Calculate SHA-256 Checksum
shasum -a 256 "${FINAL_PKG}" > "${CHECKSUM_FILE}"

echo ""
echo "================================================================================"
echo "[✓] Successfully built KENN Mix Assistant Universal Installer!"
echo "Package:  ${FINAL_PKG} ($(du -h "${FINAL_PKG}" | awk '{print $1}'))"
echo "Checksum: $(cat "${CHECKSUM_FILE}")"
echo "================================================================================"
