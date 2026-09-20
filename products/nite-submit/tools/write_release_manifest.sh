#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"

version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
checks="not-recorded"
batch_summary="not-recorded"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --checks)
      [[ $# -ge 2 ]] || { echo "Missing value for --checks" >&2; exit 2; }
      checks="$2"; shift 2 ;;
    --batch-summary)
      [[ $# -ge 2 ]] || { echo "Missing value for --batch-summary" >&2; exit 2; }
      batch_summary="$2"; shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

app="artifacts/Submit-${version}-macOS.app"
zip="artifacts/Submit-${version}-macOS.zip"
dmg="artifacts/Submit-${version}-macOS.dmg"
app_binary="$app/Contents/MacOS/NiteSubmit"
cli_binary="$app/Contents/MacOS/nitesubmit-cli"
for required_input in "$app" "$zip" "$dmg" "$app_binary" "$cli_binary"; do
  [[ -e "$required_input" ]] || { echo "Release input missing: $required_input" >&2; exit 1; }
done

sha256() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
git_bin="$(command -v git)"
source_sha=$($git_bin -C "$product_dir" rev-parse HEAD 2>/dev/null || echo "unavailable")
branch=$($git_bin -C "$product_dir" branch --show-current 2>/dev/null || echo "unavailable")
# Release outputs and generated validation reports do not describe source
# provenance. Everything else must be clean for a public release.
dirty_paths=$($git_bin -C "$product_dir" status --porcelain -- . \
  ':(exclude)artifacts' ':(exclude)real_validation_corpus/test_results' 2>/dev/null \
  | /usr/bin/wc -l | /usr/bin/tr -d ' ')
working_tree_dirty=$([[ "$dirty_paths" != "0" ]] && echo true || echo false)
manifest="artifacts/Submit-${version}-release-manifest.json"

signing_mode="ad_hoc"
if /usr/bin/codesign -dvv "$app" 2>&1 | /usr/bin/grep -q 'Authority=Developer ID Application:'; then
  signing_mode="developer_id"
fi
notarised=false
if /usr/bin/xcrun stapler validate "$dmg" >/dev/null 2>&1; then
  notarised=true
fi

/usr/bin/jq -n \
  --arg version "$version" \
  --arg created "$(/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --arg sourceSha "$source_sha" \
  --arg branch "$branch" \
  --arg checks "$checks" \
  --arg batchSummary "$batch_summary" \
  --arg appHash "$(sha256 "$app_binary")" \
  --arg cliHash "$(sha256 "$cli_binary")" \
  --arg archiveHash "$(sha256 "$zip")" \
  --arg dmgHash "$(sha256 "$dmg")" \
  --arg signingMode "$signing_mode" \
  --argjson notarised "$notarised" \
  --argjson dmgSize "$(stat -f%z "$dmg")" \
  --argjson dirty "$working_tree_dirty" \
  --argjson dirtyPaths "$dirty_paths" \
  '{
    manifest_version: "NITE_SUBMIT_RELEASE_MANIFEST_V1",
    product: "NITE Submit",
    version: $version,
    architecture: "arm64",
    minimum_macos: "13.0",
    created_utc: $created,
    source: {
      git_sha: $sourceSha,
      branch: $branch,
      working_tree_dirty: $dirty,
      uncommitted_path_count: $dirtyPaths
    },
    verification: {
      deterministic_checks: $checks,
      batch_summary: $batchSummary,
      release_check: "pass"
    },
    artifacts: {
      app_binary_sha256: $appHash,
      cli_binary_sha256: $cliHash,
      archive_sha256: $archiveHash,
      dmg_sha256: $dmgHash,
      dmg_size_bytes: $dmgSize
    },
    signing: {
      mode: $signingMode,
      notarised: $notarised
    }
  }' > "$manifest"

echo "Release manifest: $manifest"
/bin/cat "$manifest"
