#!/bin/zsh
# Remove stale, versioned NITE Submit release outputs while retaining the
# version that was just built. Build caches, test evidence, and non-release
# metadata are intentionally outside this cleanup scope.
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
artifacts_dir="${NITE_SUBMIT_ARTIFACTS_DIR:-$product_dir/artifacts}"
current_version="${1:?usage: cleanup_old_release_artifacts.sh VERSION}"

case "$current_version" in
  ''|*[!0-9.]*)
    echo "Invalid release version: $current_version" >&2
    exit 2
    ;;
esac

current_app="$artifacts_dir/Submit-${current_version}-macOS.app"
current_archive="$artifacts_dir/Submit-${current_version}-macOS.zip"
legacy_manifest="$artifacts_dir/NITESubmit-${current_version}-release-manifest.json"
legacy_readiness="$artifacts_dir/NITESubmit-${current_version}-distribution-readiness.json"

[[ -d "$artifacts_dir" ]] || exit 0

# The public-facing artifact prefix changed from NITESubmit to Submit. Remove
# only the exact legacy metadata files for this release; unrelated reports are
# retained.
for legacy_metadata in "$legacy_manifest" "$legacy_readiness"; do
  if [[ -e "$legacy_metadata" ]]; then
    echo "Removing legacy release metadata: $legacy_metadata"
    rm -f -- "$legacy_metadata"
  fi
done

for item in "$artifacts_dir"/Submit-*-macOS.app(N) \
           "$artifacts_dir"/Submit-*-macOS.zip(N) \
           "$artifacts_dir"/NITESubmit-*-macOS.app(N) \
           "$artifacts_dir"/NITESubmit-*-macOS.zip(N); do
  [[ -e "$item" || -L "$item" ]] || continue
  [[ "$item" == "$current_app" || "$item" == "$current_archive" ]] && continue

  name="${item##*/}"
  [[ "$name" =~ '^(Submit|NITESubmit)-[0-9]+\.[0-9]+\.[0-9]+-macOS\.(app|zip)$' ]] || continue

  echo "Removing stale release artifact: $item"
  if [[ "$item" == *.app ]]; then
    rm -rf -- "$item"
  else
    rm -f -- "$item"
  fi
done
