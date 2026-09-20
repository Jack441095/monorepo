#!/bin/zsh
# Build Submit.dmg installer into artifacts/.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(<./VERSION | tr -d '[:space:]')"
[[ -n "$VERSION" ]] || { echo "ERROR: VERSION file missing/empty" >&2; exit 1; }

APP_PATH="artifacts/Submit-${VERSION}-macOS.app"
DMG_PATH="artifacts/Submit-${VERSION}-macOS.dmg"

use_existing_app=false
if [[ "${1:-}" == "--app-ready" ]]; then
    use_existing_app=true
elif [[ $# -gt 0 ]]; then
    echo "Usage: $0 [--app-ready]" >&2
    exit 2
fi

# A stale app bundle previously produced a DMG whose binaries and bundled
# resources did not match the release ZIP. Default to a fresh package. The
# signing pipeline passes --app-ready only after it has signed that exact app.
if [[ "$use_existing_app" == false ]]; then
    ./tools/package_app.sh
fi

[[ -d "$APP_PATH" ]] || { echo "App bundle missing: $APP_PATH" >&2; exit 1; }
./tools/verify_app_bundle.sh "$APP_PATH"

echo "== creating release DMG =="
STAGING_DIR="$(mktemp -d /tmp/nite-submit-dmg.XXXXXX)"
trap 'rm -rf "$STAGING_DIR"' EXIT

cp -R "$APP_PATH" "$STAGING_DIR/Submit.app"
ln -s /Applications "$STAGING_DIR/Applications"

rm -f "$DMG_PATH"
hdiutil create -volname "NITE Submit ${VERSION}" \
    -srcfolder "$STAGING_DIR" \
    -ov -format UDZO \
    "$DMG_PATH"

echo "== DMG created =="
du -sh "$DMG_PATH"
shasum -a 256 "$DMG_PATH"
echo "DMG output verified: $DMG_PATH"
