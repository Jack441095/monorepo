#!/bin/sh
# DiskSweep packaging: universal scanner+helper, versioned stage dir, DMG + checksums.
# Usage: sh packaging/package.sh 1.0.0
# Signing/notarization run only when APPLE_TEAM_ID is set; otherwise ad-hoc.
set -eu
VER="${1:-0.1.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$ROOT/dist/DiskSweep-$VER"
BIN="$STAGE/DiskSweep.app/Contents/MacOS"
RES="$STAGE/DiskSweep.app/Contents/Resources"
mkdir -p "$BIN" "$RES"
/usr/bin/clang++ -std=c++17 -O2 -Wall -Wextra -arch arm64 -arch x86_64 \
  "$ROOT/scanner/main.cpp" -o "$BIN/disksweep-scanner"
/usr/bin/clang++ -std=c++17 -O2 -Wall -Wextra -arch arm64 -arch x86_64 \
  -I "$ROOT/scanner" "$ROOT/privileged-helper/helper.cpp" -o "$BIN/disksweep-helper"
cp -R "$ROOT/sidecar" "$RES/sidecar"
cp "$ROOT/contracts/scan_item.schema.json" "$ROOT/contracts/verdict.schema.json" "$RES/"
if [ -n "${APPLE_TEAM_ID:-}" ]; then
  codesign --deep --force --options runtime --sign "$APPLE_TEAM_ID" "$STAGE/DiskSweep.app"
fi
hdiutil create -volname "DiskSweep $VER" -srcfolder "$STAGE" -ov -format UDZO \
  "$ROOT/dist/DiskSweep-$VER.dmg"
(cd "$ROOT/dist" && shasum -a 256 "DiskSweep-$VER.dmg" > "DiskSweep-$VER.sha256")
echo "OK dist/DiskSweep-$VER.dmg"
