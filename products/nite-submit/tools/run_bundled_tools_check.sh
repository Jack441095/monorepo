#!/bin/zsh
set -euo pipefail
product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=$(tr -d '[:space:]' < "$product_dir/VERSION")
cli="${NITE_SUBMIT_CLI:-$product_dir/artifacts/Submit-${version}-macOS.app/Contents/MacOS/nitesubmit-cli}"
resources="$(dirname "$cli")/../Resources"
work_dir=$(mktemp -d /tmp/nite-submit-bundled-tools.XXXXXX)
trap 'rm -R -- "$work_dir"' EXIT
source="$product_dir/Sources/NiteSubmitTests/Fixtures/corpus/pdf/clear_000.pdf"
before=$(shasum -a 256 "$source" | awk '{print $1}')
mkdir "$work_dir/input"
cp "$source" "$work_dir/input/音楽 résumé.pdf"
# The packaged CLI resolves 7za/qpdf relative to itself, with no Homebrew PATH.
for format in 7z zip tar.gz; do
  PATH=/usr/bin:/bin "$cli" pack "$work_dir/input" --out "$work_dir/output.$format" --format "$format" >/dev/null
  mkdir "$work_dir/extracted-$format"
  case "$format" in
    7z) "$resources/bin/7za" x "$work_dir/output.7z" "-o$work_dir/extracted-7z" -y >/dev/null ;;
    zip) unzip -q "$work_dir/output.zip" -d "$work_dir/extracted-zip" ;;
    tar.gz) tar -xzf "$work_dir/output.tar.gz" -C "$work_dir/extracted-tar.gz" ;;
  esac
  # ditto preserves resource forks as AppleDouble sidecars; those are metadata,
  # not extra PDFs. Compare the single document, including Unicode normalization.
  extracted=$(find "$work_dir/extracted-$format" -type f -name '*.pdf' ! -name '._*')
  [[ -n "$extracted" ]]
  cmp -s "$source" "$extracted"
done
# Use a public test password only; both advertised formats must actually
# reject the wrong password and round-trip with the bundled AES-capable tool.
for format in 7z zip; do
  PATH=/usr/bin:/bin "$cli" pack "$work_dir/input" --out "$work_dir/encrypted.$format" --format "$format" --password 'Submit-test-only' >/dev/null
  if "$resources/bin/7za" t "$work_dir/encrypted.$format" -pwrong-test-password >/dev/null 2>&1; then
    echo 'Encrypted archive accepted an incorrect password.' >&2
    exit 1
  fi
  "$resources/bin/7za" l -slt "$work_dir/encrypted.$format" -pSubmit-test-only | grep -q 'AES'
  "$resources/bin/7za" x "$work_dir/encrypted.$format" -pSubmit-test-only "-o$work_dir/encrypted-$format" -y >/dev/null
  extracted=$(find "$work_dir/encrypted-$format" -type f -name '*.pdf' ! -name '._*')
  cmp -s "$source" "$extracted"
done
# 26 MiB exceeds the smallest supported 25 MiB volume. Seeded random bytes
# prevent LZMA2 from shrinking the payload below the volume boundary.
python3 - "$work_dir/volume.bin" <<'PY'
from pathlib import Path
import random
import sys
Path(sys.argv[1]).write_bytes(random.Random(42).randbytes(26 * 1024 * 1024))
PY
PATH=/usr/bin:/bin "$cli" pack "$work_dir/volume.bin" --out "$work_dir/split.7z" --level store --volume-split-mb 25 >/dev/null
[[ -f "$work_dir/split.7z.001" && -f "$work_dir/split.7z.002" ]]
"$resources/bin/7za" x "$work_dir/split.7z.001" "-o$work_dir/split-output" -y >/dev/null
cmp -s "$work_dir/volume.bin" "$work_dir/split-output/volume.bin"
PATH=/usr/bin:/bin "$cli" optimize "$source" --out "$work_dir/optimized.pdf" >/dev/null
"$resources/bin/qpdf" --check "$work_dir/optimized.pdf" >/dev/null
[[ "$("$resources/bin/qpdf" --show-npages "$source")" == "$("$resources/bin/qpdf" --show-npages "$work_dir/optimized.pdf")" ]]
[[ "$before" == "$(shasum -a 256 "$source" | awk '{print $1}')" ]]
echo 'Bundled tools passed: Unicode 7z/ZIP/tar.gz, AES passwords, 25 MiB volumes, qpdf optimization and unchanged source.'
