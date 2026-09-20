#!/bin/zsh
# NITE Submit Installer — student-friendly one-liner
# Usage: curl -fsSL https://releases.nitedsp.co.uk/submit/install.sh | zsh
set -euo pipefail

VERSION="1.0.0"
DOWNLOAD_URL="https://releases.nitedsp.co.uk/submit/Submit-${VERSION}-macOS.zip"
EXPECTED_SHA256="f07d1367290ed7f4cb7c59b095e9193de0c785bb5b54d6b4c7c65a6ccd5be3a7"

info()  { printf '\n  \033[1;34m→\033[0m %s\n' "$1"; }
ok()    { printf '  \033[1;32m✓\033[0m %s\n' "$1"; }
fail()  { printf '\n  \033[1;31m✗\033[0m %s\n\n' "$1" >&2; exit 1; }

echo ""
echo "  ╭───────────────────────────────────╮"
echo "  │   NITE Submit ${VERSION} Installer     │"
echo "  ╰───────────────────────────────────╯"

[[ "$(uname -m)" == "arm64" ]] || fail "Requires Apple Silicon (this Mac is $(uname -m))."
[[ "${$(sw_vers -productVersion)%%.*}" -ge 13 ]] || fail "Requires macOS 13+."

TMPDIR_INSTALL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_INSTALL"' EXIT

info "Downloading..."
curl -fSL --progress-bar -o "$TMPDIR_INSTALL/submit.zip" "$DOWNLOAD_URL"

ACTUAL="$(shasum -a 256 "$TMPDIR_INSTALL/submit.zip" | awk '{print $1}')"
[[ "$ACTUAL" == "$EXPECTED_SHA256" ]] || fail "Download integrity check failed. Try again."
ok "Download verified"

info "Installing to /Applications..."
ditto -xk "$TMPDIR_INSTALL/submit.zip" "$TMPDIR_INSTALL"
APP="$(find "$TMPDIR_INSTALL" -maxdepth 2 -name '*.app' -type d | head -1)"
[[ -d "$APP" ]] || fail "Could not find app in archive."
xattr -cr "$APP"
[[ -d "/Applications/Submit.app" ]] && rm -rf "/Applications/Submit.app"
mv "$APP" "/Applications/Submit.app"
ok "Installed"

info "Launching NITE Submit..."
open -a Submit

echo ""
echo "  Done! Paste your licence key when prompted."
echo "  Purchased at nitedsp.co.uk/pricing"
echo ""
