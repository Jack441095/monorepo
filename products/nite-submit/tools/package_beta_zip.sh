#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
app_path="$product_dir/artifacts/Submit-${version}-macOS.app"
archive_path="${1:-$product_dir/artifacts/Submit-${version}-macOS.zip}"

[[ -d "$app_path" ]] || {
  echo "App bundle not found; run ./tools/package_app.sh first." >&2
  exit 1
}

"$product_dir/tools/verify_app_bundle.sh" "$app_path"
rm -f "$archive_path"
archive_dir=$(dirname "$archive_path")
mkdir -p "$archive_dir"

staging_dir=$(mktemp -d /tmp/nite-submit-zip-staging.XXXXXX)
trap 'rm -R -- "$staging_dir"' EXIT
staged_app="$staging_dir/$(basename "$app_path")"
cp -R "$app_path" "$staged_app"
# The bundle contents are unchanged; normalising filesystem timestamps in the
# temporary copy makes identical builds produce an identical ZIP checksum.
find "$staged_app" -exec touch -t 198001010000 {} +
(cd "$staging_dir" && zip -X -qry "$archive_path" "$(basename "$staged_app")")
unzip -tq "$archive_path"
"$product_dir/tools/cleanup_old_release_artifacts.sh" "$version"
echo "Beta archive: $archive_path"
du -h "$archive_path"
shasum -a 256 "$archive_path"
