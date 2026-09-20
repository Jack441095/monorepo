#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"

version="$(tr -d '[:space:]' < VERSION)"
app="artifacts/Submit-${version}-macOS.app"
zip="artifacts/Submit-${version}-macOS.zip"
dmg="artifacts/Submit-${version}-macOS.dmg"

for required_artifact in "$app" "$zip" "$dmg"; do
  [[ -e "$required_artifact" ]] || { echo "Missing release artifact: $required_artifact" >&2; exit 1; }
done

./tools/verify_app_bundle.sh "$app"
unzip -tq "$zip"

mount_dir=$(mktemp -d /tmp/nite-submit-dmg-verify.XXXXXX)
cleanup() {
  hdiutil detach "$mount_dir" >/dev/null 2>&1 || true
  rmdir "$mount_dir" >/dev/null 2>&1 || true
}
trap cleanup EXIT

hdiutil attach -readonly -nobrowse -noautoopen -mountpoint "$mount_dir" "$dmg" >/dev/null
mounted_app="$mount_dir/Submit.app"
./tools/verify_app_bundle.sh "$mounted_app"

sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
for relative_path in \
  Contents/MacOS/NiteSubmit \
  Contents/MacOS/nitesubmit-cli \
  Contents/Resources/bin/7za \
  Contents/Resources/bin/qpdf \
  Contents/Resources/lib/libqpdf.30.dylib \
  Contents/Resources/lib/libjpeg.8.dylib \
  Contents/Resources/lib/libcrypto.3.dylib; do
  source_hash=$(sha256 "$app/$relative_path")
  dmg_hash=$(sha256 "$mounted_app/$relative_path")
  [[ "$source_hash" == "$dmg_hash" ]] || {
    echo "DMG mismatch for $relative_path" >&2
    exit 1
  }
done

hdiutil detach "$mount_dir" >/dev/null
rmdir "$mount_dir"
trap - EXIT
echo "Release artifact parity passed for Submit ${version}."
