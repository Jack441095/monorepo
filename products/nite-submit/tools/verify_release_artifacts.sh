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
zip_dir=$(mktemp -d /tmp/nite-submit-zip-verify.XXXXXX)
cleanup() {
  hdiutil detach "$mount_dir" >/dev/null 2>&1 || true
  rmdir "$mount_dir" >/dev/null 2>&1 || true
  rm -R -- "$zip_dir"
}
trap cleanup EXIT

hdiutil attach -readonly -nobrowse -noautoopen -mountpoint "$mount_dir" "$dmg" >/dev/null
mounted_app="$mount_dir/Submit.app"
./tools/verify_app_bundle.sh "$mounted_app"
unzip -q "$zip" -d "$zip_dir"
extracted_app="$zip_dir/Submit-${version}-macOS.app"
./tools/verify_app_bundle.sh "$extracted_app"

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

# Resources, notices, metadata and signature tickets matter as much as binaries.
python3 - "$app" "$mounted_app" "$extracted_app" <<'PY'
import hashlib
from pathlib import Path
import sys
def inventory(root):
    return {str(p.relative_to(root)): (p.stat().st_mode & 0o777, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_file()}
expected = inventory(Path(sys.argv[1]))
for root in map(Path, sys.argv[2:]):
    if inventory(root) != expected:
        raise SystemExit('Complete bundle contents or permissions differ between artifacts')
print('Complete ZIP/DMG bundle parity passed')
PY
# Both delivery formats must work without borrowing helpers from the source app.
for delivered_app in "$extracted_app" "$mounted_app"; do
  NITE_SUBMIT_CLI="$delivered_app/Contents/MacOS/nitesubmit-cli" ./tools/run_pdf_matrix_check.sh
  NITE_SUBMIT_CLI="$delivered_app/Contents/MacOS/nitesubmit-cli" ./tools/run_bundled_tools_check.sh
  python3 tools/check_rebuilt_corpus.py --cli "$delivered_app/Contents/MacOS/nitesubmit-cli"
done

hdiutil detach "$mount_dir" >/dev/null
rmdir "$mount_dir"
rm -R -- "$zip_dir"
trap - EXIT
echo "Release artifact parity passed for Submit ${version}."
