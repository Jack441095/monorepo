#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$product_dir"

require_ready=false
profile="NITE_SUBMIT"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-ready) require_ready=true; shift ;;
    --profile)
      [[ $# -ge 2 ]] || { echo "Missing value for --profile" >&2; exit 2; }
      profile="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
app="artifacts/Submit-${version}-macOS.app"
dmg="artifacts/Submit-${version}-macOS.dmg"
report="artifacts/Submit-${version}-distribution-readiness.json"

identity_output=$(/usr/bin/security find-identity -v -p codesigning 2>/dev/null || true)
developer_id_identity=$(/usr/bin/printf '%s\n' "$identity_output" | /usr/bin/grep -c 'Developer ID Application:' || true)
notarytool_path=$(/usr/bin/xcrun --find notarytool 2>/dev/null || true)
notarytool_available=$([[ -n "$notarytool_path" ]] && echo true || echo false)

profile_check=1
if /usr/bin/xcrun notarytool history --keychain-profile "$profile" \
  --output-format json >/dev/null 2>&1; then
  profile_check=0
fi
notary_profile_configured=$([[ "$profile_check" == "0" ]] && echo true || echo false)
developer_id_ready=$([[ "$developer_id_identity" -gt 0 ]] && echo true || echo false)
app_signed_for_distribution=false
if [[ -d "$app" ]]; then
  if /usr/bin/codesign -dvv "$app" 2>&1 | /usr/bin/grep -q 'Authority=Developer ID Application:'; then
    app_signed_for_distribution=true
  fi
fi
app_notarised=false
dmg_notarised=false
if [[ -d "$app" ]] && /usr/bin/xcrun stapler validate "$app" >/dev/null 2>&1; then
  app_notarised=true
fi
if [[ -f "$dmg" ]] && /usr/bin/xcrun stapler validate "$dmg" >/dev/null 2>&1; then
  dmg_notarised=true
fi

ready=$([[ "$developer_id_ready" == true && "$notarytool_available" == true && \
           "$notary_profile_configured" == true && "$app_signed_for_distribution" == true && \
           "$app_notarised" == true && "$dmg_notarised" == true ]] &&
        echo true || echo false)

/usr/bin/jq -n \
  --arg created "$(/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --arg profile "$profile" \
  --arg version "$version" \
  --argjson developerIDIdentityCount "$developer_id_identity" \
  --argjson developerIDReady "$developer_id_ready" \
  --argjson notarytoolAvailable "$notarytool_available" \
  --argjson notaryProfileConfigured "$notary_profile_configured" \
  --argjson appSignedForDistribution "$app_signed_for_distribution" \
  --argjson appNotarised "$app_notarised" \
  --argjson dmgNotarised "$dmg_notarised" \
  --argjson ready "$ready" \
  '{
    manifest_version: "NITE_SUBMIT_DISTRIBUTION_READINESS_V1",
    created_utc: $created,
    product: "NITE Submit",
    version: $version,
    notary_profile: $profile,
    checks: {
      developer_id_identity_count: $developerIDIdentityCount,
      developer_id_identity_available: $developerIDReady,
      notarytool_available: $notarytoolAvailable,
      notary_profile_configured: $notaryProfileConfigured,
      current_app_developer_id_signed: $appSignedForDistribution,
      current_app_notarised: $appNotarised,
      current_dmg_notarised: $dmgNotarised
    },
    ready_for_public_distribution: $ready
  }' > "$report"

echo "Distribution readiness report: $report"
/bin/cat "$report"

if [[ "$require_ready" == true && "$ready" != true ]]; then
  echo "Distribution readiness failed: Developer ID signing/notarisation prerequisites are incomplete." >&2
  exit 1
fi
