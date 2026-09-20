#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
archive="$product_dir/artifacts/Submit-${version}-macOS.zip"
[[ -f "$archive" ]] || {
  echo "Archive not found: $archive" >&2
  exit 1
}

"$product_dir/tools/package_beta_zip.sh" >/dev/null
first_hash=$(shasum -a 256 "$archive" | awk '{print $1}')
"$product_dir/tools/package_beta_zip.sh" >/dev/null
second_hash=$(shasum -a 256 "$archive" | awk '{print $1}')

[[ "$first_hash" == "$second_hash" ]] || {
  echo "Archive checksum changed for identical inputs: $first_hash -> $second_hash" >&2
  exit 1
}

echo "Deterministic archive check passed: $first_hash"
