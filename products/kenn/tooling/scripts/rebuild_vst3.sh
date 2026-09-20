#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:$PATH"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="${REPO_ROOT}/build/plugins/kenn-vst3-au"
ARTEFACT="${BUILD_DIR}/KENNMixAssistant_artefacts/VST3/KENN Mix Assistant.vst3"
if [[ ! -d "${ARTEFACT}" ]]; then
    ARTEFACT="${BUILD_DIR}/KENNMixAssistant_artefacts/Release/VST3/KENN Mix Assistant.vst3"
fi
INSTALL_DIR="${KENN_VST3_INSTALL_DIR:-${HOME}/Library/Audio/Plug-Ins/VST3}"
INSTALL_PATH="${INSTALL_DIR}/KENN Mix Assistant.vst3"

ARTEFACT_AU="${BUILD_DIR}/KENNMixAssistant_artefacts/AU/KENN Mix Assistant.component"
if [[ ! -d "${ARTEFACT_AU}" ]]; then
    ARTEFACT_AU="${BUILD_DIR}/KENNMixAssistant_artefacts/Release/AU/KENN Mix Assistant.component"
fi
INSTALL_DIR_AU="${KENN_AU_INSTALL_DIR:-${HOME}/Library/Audio/Plug-Ins/Components}"
INSTALL_PATH_AU="${INSTALL_DIR_AU}/KENN Mix Assistant.component"

cmake --build "${BUILD_DIR}" --config Release --parallel "${KENN_BUILD_JOBS:-4}"

if [[ ! -d "${ARTEFACT}" ]]; then
    echo "Build completed, but the VST3 artefact was not found: ${ARTEFACT}" >&2
    exit 1
fi

mkdir -p "${INSTALL_DIR}"
ditto "${ARTEFACT}" "${INSTALL_PATH}"
codesign --force --deep --sign - "${INSTALL_PATH}" >/dev/null

if [[ -d "${ARTEFACT_AU}" ]]; then
    mkdir -p "${INSTALL_DIR_AU}"
    ditto "${ARTEFACT_AU}" "${INSTALL_PATH_AU}"
    codesign --force --deep --sign - "${INSTALL_PATH_AU}" >/dev/null
    echo "Installed AU: ${INSTALL_PATH_AU}"
fi

echo "Installed VST3: ${INSTALL_PATH}"
echo "Next: fully quit and reopen Ableton Live before testing."
echo "Reopening only the plug-in editor may keep the previous binary loaded."
