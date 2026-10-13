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

# Check owner credentials before replacing a verified private-beta artifact.
if ! security find-identity -v -p codesigning | fgrep -F -- "\"$SIGNING_IDENTITY\"" >/dev/null; then
  echo "Requested signing identity is unavailable; existing artifacts were retained." >&2
  exit 1
fi
if ! xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" --output-format json >/dev/null; then
  echo "Notarisation profile is unavailable; existing artifacts were retained." >&2
  exit 1
fi

echo "======================================================="
echo " NITE Submit Automated Signing & Notarisation Pipeline"
echo " Version:  ${VERSION}"
echo " Identity: ${SIGNING_IDENTITY}"
echo " Profile:  ${NOTARY_PROFILE}"
echo "======================================================="

# Run the same release gate before signing; a previous beta manifest may refer
# to different source. Its measured counts follow this app through notarisation.
echo "\n[1/6] Verifying fresh release artifacts..."
./tools/run_release_checks.sh
release_manifest="artifacts/Submit-${VERSION}-release-manifest.json"
checks=$(jq -er '.verification.deterministic_checks' "$release_manifest")
batch_summary=$(jq -er '.verification.batch_summary' "$release_manifest")
jq -e '.verification.release_check == "pass"' "$release_manifest" >/dev/null
# Signing changes the certified bytes. A rejection or interruption must not
# leave the pre-signing pass beside partially signed artifacts; the final
# writer recreates it only after notarisation and delivery checks succeed.
rm -f -- "$release_manifest"

# 2. Code sign with Hardened Runtime (inside-out: embedded binaries first)
# Apple's rule is strictly innermost first: a dylib has to be signed before the
# executable that loads it, and the executable before the bundle that holds it.
# `--deep` on the bundle alone does not cover Resources/lib/*.dylib
# (libqpdf, libjpeg, libcrypto), so a notarised build can be rejected for an
# unsigned nested library even though the outer signature verifies.
echo "\n[2/6] Code signing app bundle with Developer ID..."
for dylib in "$APP_PATH"/Contents/Resources/lib/*.dylib; do
  [[ -f "$dylib" ]] || continue
  echo "  Signing dylib: $(basename "$dylib")"
  codesign --force --options runtime --timestamp \
    --sign "$SIGNING_IDENTITY" "$dylib"
done
for embedded in "$APP_PATH"/Contents/Resources/bin/*; do
  [[ -x "$embedded" && ! -d "$embedded" ]] || continue
  echo "  Signing embedded binary: $(basename "$embedded")"
  codesign --force --options runtime --timestamp \
    --sign "$SIGNING_IDENTITY" "$embedded"
done
for executable in "$APP_PATH"/Contents/MacOS/*; do
  [[ -f "$executable" ]] || continue
  echo "  Signing executable: $(basename "$executable")"
  codesign --force --options runtime --timestamp \
    --sign "$SIGNING_IDENTITY" "$executable"
done
codesign --force --options runtime --timestamp \
  --sign "$SIGNING_IDENTITY" \
  "$APP_PATH"

echo "Verifying code signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
# Gatekeeper requires the notarisation ticket. Assess only after stapling;
# a correctly signed but unnotarised app is expected to be rejected here.

# The first ZIP is only the notarisation submission. Rebuild both customer
# containers after stapling, otherwise their app would lack the ticket.
echo "\n[3/6] Packaging signed app for notarisation..."
./tools/package_beta_zip.sh

# Notarise the app first so both customer containers include its stapled ticket.
xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
./tools/package_beta_zip.sh
./tools/create_release_dmg.sh --app-ready
codesign --force --timestamp --sign "$SIGNING_IDENTITY" "$DMG_PATH"
xcrun notarytool submit "$DMG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$DMG_PATH"
xcrun stapler validate "$DMG_PATH"
spctl --assess --type execute --verbose=4 "$APP_PATH"
./tools/verify_release_artifacts.sh

# 6. Re-verify distribution readiness
echo "\n[6/6] Re-checking distribution readiness..."
./tools/check_distribution_readiness.sh --profile "$NOTARY_PROFILE" --require-ready
./tools/write_release_manifest.sh --checks "$checks" --batch-summary "$batch_summary"

echo "\n======================================================="
echo " SUCCESS: NITE Submit ${VERSION} passed signing and notarisation; complete the owner shipping decision before publication."
echo " Artifacts:"
echo "   - App: $APP_PATH"
echo "   - DMG: $DMG_PATH"
echo "   - ZIP: $ZIP_PATH"
echo "======================================================="
