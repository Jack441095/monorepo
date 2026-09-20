#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_ROOT="${KENN_PLUGIN_BUILD_ROOT:-${REPO_ROOT}/build/plugins/kenn-vst3-au/KENNMixAssistant_artefacts/Release}"
VST3_SOURCE="${BUILD_ROOT}/VST3/KENN Mix Assistant.vst3"
AU_SOURCE="${BUILD_ROOT}/AU/KENN Mix Assistant.component"
OUTPUT_DIR="${KENN_PLUGIN_OUTPUT_DIR:-${REPO_ROOT}/dist}"
SIGNING_IDENTITY="${KENN_CODESIGN_IDENTITY:-}"
NOTARY_PROFILE="${KENN_NOTARY_PROFILE:-}"
VERSION="0.1.0"
PREFLIGHT_ONLY=0

usage() {
    cat <<'EOF'
Usage: tooling/scripts/package_macos_plugins.sh [options]

Create a Developer ID signed, notarized, stapled macOS plug-in archive.
The command fails closed: ad-hoc or unnotarized release archives are not
supported by this script.

Options:
  --identity NAME         Developer ID Application identity
  --notary-profile NAME   notarytool keychain profile
  --output-dir PATH       Output directory (default: repo dist/)
  --version VERSION       Archive version label (default: 0.1.0)
  --preflight             Validate prerequisites without changing files
  -h, --help              Show this help

The identity and profile may instead be set with KENN_CODESIGN_IDENTITY and
KENN_NOTARY_PROFILE. Create the notary profile separately with Apple's
`xcrun notarytool store-credentials`; this script never accepts secrets on its
command line.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity)
            SIGNING_IDENTITY="${2:?--identity requires a value}"
            shift 2
            ;;
        --notary-profile)
            NOTARY_PROFILE="${2:?--notary-profile requires a value}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:?--output-dir requires a value}"
            shift 2
            ;;
        --version)
            VERSION="${2:?--version requires a value}"
            shift 2
            ;;
        --preflight)
            PREFLIGHT_ONLY=1
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

missing=0
for command_name in cmake codesign ditto security shasum spctl xcrun; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        echo "Missing required command: ${command_name}" >&2
        missing=1
    fi
done
if [[ ! -d "${VST3_SOURCE}" ]]; then
    echo "Missing VST3 build artifact: ${VST3_SOURCE}" >&2
    missing=1
fi
if [[ ! -d "${AU_SOURCE}" ]]; then
    echo "Missing AU build artifact: ${AU_SOURCE}" >&2
    missing=1
fi
if [[ -z "${SIGNING_IDENTITY}" ]]; then
    echo "Missing Developer ID identity: set KENN_CODESIGN_IDENTITY or use --identity." >&2
    missing=1
elif ! security find-identity -v -p codesigning | grep -F "${SIGNING_IDENTITY}" >/dev/null; then
    echo "The requested code-signing identity is not available: ${SIGNING_IDENTITY}" >&2
    missing=1
fi
if [[ -z "${NOTARY_PROFILE}" ]]; then
    echo "Missing notary profile: set KENN_NOTARY_PROFILE or use --notary-profile." >&2
    missing=1
elif ! xcrun notarytool history --keychain-profile "${NOTARY_PROFILE}" >/dev/null 2>&1; then
    echo "The requested notarytool keychain profile is unavailable or invalid: ${NOTARY_PROFILE}" >&2
    missing=1
fi
if ! xcrun --find notarytool >/dev/null 2>&1; then
    echo "Apple notarytool is unavailable; install current Xcode command-line tools." >&2
    missing=1
fi

if [[ "${missing}" -ne 0 ]]; then
    echo "KENN macOS plug-in packaging preflight failed; no release archive was created." >&2
    exit 2
fi

echo "Packaging preflight passed for KENN Mix Assistant ${VERSION}."
if [[ "${PREFLIGHT_ONLY}" -eq 1 ]]; then
    exit 0
fi

cmake --build "${REPO_ROOT}/build/plugins/kenn-vst3-au" --config Release --parallel "${KENN_BUILD_JOBS:-2}"

STAGING_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/kenn-plugin-package.XXXXXX")"
cleanup() {
    rm -rf "${STAGING_ROOT}"
}
trap cleanup EXIT

PACKAGE_ROOT="${STAGING_ROOT}/KENN Mix Assistant ${VERSION}"
mkdir -p "${PACKAGE_ROOT}/VST3" "${PACKAGE_ROOT}/Components"
ditto "${VST3_SOURCE}" "${PACKAGE_ROOT}/VST3/KENN Mix Assistant.vst3"
ditto "${AU_SOURCE}" "${PACKAGE_ROOT}/Components/KENN Mix Assistant.component"

for bundle in \
    "${PACKAGE_ROOT}/VST3/KENN Mix Assistant.vst3" \
    "${PACKAGE_ROOT}/Components/KENN Mix Assistant.component"; do
    codesign --force --options runtime --timestamp --sign "${SIGNING_IDENTITY}" "${bundle}"
    codesign --verify --strict --verbose=2 "${bundle}"
done

ARCHIVE_NAME="KENN-Mix-Assistant-${VERSION}-macOS.zip"
ARCHIVE_PATH="${OUTPUT_DIR}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"
SUBMISSION_ARCHIVE="${STAGING_ROOT}/submission-${ARCHIVE_NAME}"
FINAL_ARCHIVE="${STAGING_ROOT}/${ARCHIVE_NAME}"
if [[ -e "${ARCHIVE_PATH}" || -e "${CHECKSUM_PATH}" ]]; then
    echo "Refusing to overwrite an existing release artifact: ${ARCHIVE_PATH}" >&2
    exit 2
fi
ditto -c -k --sequesterRsrc --keepParent "${PACKAGE_ROOT}" "${SUBMISSION_ARCHIVE}"

xcrun notarytool submit "${SUBMISSION_ARCHIVE}" --keychain-profile "${NOTARY_PROFILE}" --wait
xcrun stapler staple "${PACKAGE_ROOT}/VST3/KENN Mix Assistant.vst3"
xcrun stapler staple "${PACKAGE_ROOT}/Components/KENN Mix Assistant.component"

# Create the distributable only after both bundles carry stapled tickets.
ditto -c -k --sequesterRsrc --keepParent "${PACKAGE_ROOT}" "${FINAL_ARCHIVE}"
spctl -a -vv -t install "${PACKAGE_ROOT}/VST3/KENN Mix Assistant.vst3"
spctl -a -vv -t install "${PACKAGE_ROOT}/Components/KENN Mix Assistant.component"
mkdir -p "${OUTPUT_DIR}"
mv "${FINAL_ARCHIVE}" "${ARCHIVE_PATH}"
shasum -a 256 "${ARCHIVE_PATH}" > "${CHECKSUM_PATH}"

echo "Created notarized release archive: ${ARCHIVE_PATH}"
echo "Checksum: ${CHECKSUM_PATH}"
