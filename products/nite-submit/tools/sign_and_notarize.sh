#!/bin/zsh
# Automated Developer ID Signing & Apple Notarisation Helper for NITE Submit
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"

VERSION="$(<./VERSION | tr -d '[:space:]')"
APP_PATH="artifacts/Submit-${VERSION}-macOS.app"
ZIP_PATH="artifacts/Submit-${VERSION}-macOS.zip"
DMG_PATH="artifacts/Submit-${VERSION}-macOS.dmg"

SIGNING_IDENTITY=""
NOTARY_PROFILE="NITE_SUBMIT"

usage() {
  echo "Usage: $0 --identity \"Developer ID Application: Your Name (ID)\" [--profile NITE_SUBMIT]"
  echo ""
  echo "Options:"
  echo "  --identity NAME   Exact Developer ID Application signing identity string"
  echo "  --profile PROFILE Keychain profile for xcrun notarytool (default: NITE_SUBMIT)"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --identity)
      [[ $# -ge 2 ]] || usage
      SIGNING_IDENTITY="$2"; shift 2 ;;
    --profile)
      [[ $# -ge 2 ]] || usage
      NOTARY_PROFILE="$2"; shift 2 ;;
    -h|--help)
      usage ;;
    *)
      echo "Unknown argument: $1" >&2; usage ;;
  esac
done

if [[ -z "$SIGNING_IDENTITY" ]]; then
  echo "ERROR: --identity is required." >&2
  echo "Available Developer ID identities on this Mac:" >&2
  security find-identity -v -p codesigning | grep 'Developer ID Application:' || echo "  (None found)" >&2
  exit 1
fi

echo "======================================================="
echo " NITE Submit Automated Signing & Notarisation Pipeline"
echo " Version:  ${VERSION}"
echo " Identity: ${SIGNING_IDENTITY}"
echo " Profile:  ${NOTARY_PROFILE}"
echo "======================================================="

# 1. Package fresh app
echo "\n[1/6] Packaging fresh application..."
./tools/package_app.sh

# 2. Code sign with Hardened Runtime (inside-out: embedded binaries first)
echo "\n[2/6] Code signing app bundle with Developer ID..."
for embedded in "$APP_PATH"/Contents/Resources/bin/*; do
  [[ -x "$embedded" && ! -d "$embedded" ]] || continue
  echo "  Signing embedded binary: $(basename "$embedded")"
  codesign --force --options runtime --timestamp \
    --sign "$SIGNING_IDENTITY" "$embedded"
done
codesign --force --options runtime --timestamp \
  --sign "$SIGNING_IDENTITY" \
  "$APP_PATH"

echo "Verifying code signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
spctl --assess --type execute --verbose "$APP_PATH" || true

# 3. Create ZIP and DMG artifacts
echo "\n[3/6] Packaging signed ZIP and DMG installer..."
rm -f "$ZIP_PATH"
(cd artifacts && zip -r "Submit-${VERSION}-macOS.zip" "Submit-${VERSION}-macOS.app")
./tools/create_release_dmg.sh --app-ready

# Code sign the DMG installer as well
echo "Signing DMG installer..."
codesign --force --timestamp --sign "$SIGNING_IDENTITY" "$DMG_PATH"

# 4. Submit for Notarization
echo "\n[4/6] Submitting DMG to Apple Notary Service..."
xcrun notarytool submit "$DMG_PATH" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait

# 5. Staple Ticket
echo "\n[5/6] Stapling notarisation ticket to app and DMG..."
xcrun stapler staple "$APP_PATH"
xcrun stapler staple "$DMG_PATH"

echo "Validating stapled ticket..."
xcrun stapler validate "$APP_PATH"
xcrun stapler validate "$DMG_PATH"

# Rebuild the customer ZIP from the stapled app, then verify every artifact.
./tools/package_beta_zip.sh
./tools/verify_release_artifacts.sh

# 6. Re-verify distribution readiness
echo "\n[6/6] Re-checking distribution readiness..."
./tools/check_distribution_readiness.sh --profile "$NOTARY_PROFILE" --require-ready
./tools/write_release_manifest.sh

echo "\n======================================================="
echo " SUCCESS: NITE Submit ${VERSION} is fully signed, notarised, and ready for public distribution!"
echo " Artifacts:"
echo "   - App: $APP_PATH"
echo "   - DMG: $DMG_PATH"
echo "   - ZIP: $ZIP_PATH"
echo "======================================================="
