#!/bin/zsh
# Optional local UI smoke check for a Mac whose owner already enabled
# System Events automation. Never grant permission automatically; use a
# disposable test licence supplied via NITE_SUBMIT_TEST_LICENSE_PATH.
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=$(tr -d '[:space:]' < "$product_dir/VERSION")
app="$product_dir/artifacts/Submit-${version}-macOS.app"
source="$product_dir/real_validation_corpus/dissertations/whiterose_18613_long_phd_sheffield.pdf"
license_path="${NITE_SUBMIT_TEST_LICENSE_PATH:-}"
[[ -f "$license_path" ]] || { echo "Set NITE_SUBMIT_TEST_LICENSE_PATH to a disposable test licence." >&2; exit 2; }
evidence_root="$product_dir/artifacts/shipping-$(date -u +%Y-%m-%d)"
mkdir -p "$evidence_root"
results_dir=$(mktemp -d "$evidence_root/app-ui.XXXXXX")
input="$results_dir/input.pdf"
test_home="$results_dir/disposable-home"

[[ -x "$app/Contents/MacOS/NiteSubmit" ]] || {
  echo "Packaged app not found; run ./tools/package_app.sh first." >&2
  exit 1
}
[[ -f "$source" ]] || { echo "Smoke PDF not found: $source" >&2; exit 1; }
if /usr/bin/pgrep -x NiteSubmit >/dev/null 2>&1; then
  echo "Submit is already running; close it before the UI smoke check." >&2
  exit 1
fi

# Keep both settings and activation out of the producer's actual home.
mkdir -p "$test_home/Library/Application Support/NiteSubmit"
cp "$license_path" "$test_home/Library/Application Support/NiteSubmit/license.key"
chmod 600 "$test_home/Library/Application Support/NiteSubmit/license.key"
# This smoke starts after onboarding. First-launch activation and the number
# prompt are separate native checks, so neither may stall this copy scenario.
printf '%s\n' '{"defaultStudentId":"75589","hasPromptedForDefaultStudentId":true}' \
  > "$test_home/Library/Application Support/NiteSubmit/settings.json"
chmod 700 "$test_home/Library/Application Support/NiteSubmit"
chmod 600 "$test_home/Library/Application Support/NiteSubmit/settings.json"
app_pid=""
cleanup() {
  if [[ -n "$app_pid" ]]; then kill "$app_pid" >/dev/null 2>&1 || true; fi
  rm -R -- "$test_home"
}
trap cleanup EXIT INT TERM

before_hash=$(/usr/bin/shasum -a 256 "$source" | /usr/bin/awk '{print $1}')
cp "$source" "$input"
CFFIXED_USER_HOME="$test_home" "$app/Contents/MacOS/NiteSubmit" "$input" >/dev/null 2>&1 &
app_pid=$!
/bin/sleep 3

/usr/bin/osascript <<'APPLESCRIPT'
tell application "System Events"
  tell process "NiteSubmit"
    repeat 60 times
      if exists window 1 then
        if exists button "Approve details" of window 1 then exit repeat
        if exists button "Approve details" of scroll area 1 of window 1 then exit repeat
      end if
      delay 0.25
    end repeat
    set frontmost to true
    if exists button "Approve details" of window 1 then
      click button "Approve details" of window 1
      delay 0.5
      click button "Create submission" of window 1
    else if exists button "Approve details" of scroll area 1 of window 1 then
      click button "Approve details" of scroll area 1 of window 1
      delay 0.5
      if exists button "Create submission" of scroll area 1 of window 1 then
        click button "Create submission" of scroll area 1 of window 1
      else
        click button "Approve & Create Renamed Copy" of scroll area 1 of window 1
      end if
    end if
  end tell
end tell
APPLESCRIPT

/bin/sleep 2
output=$(/usr/bin/find "$results_dir" -maxdepth 1 -type f -name '75589_*.pdf' -print | /usr/bin/head -1)
[[ -n "$output" ]] || { echo "UI smoke produced no regular PDF output." >&2; exit 1; }
[[ ! -L "$output" ]] || { echo "UI smoke output is unexpectedly a symlink." >&2; exit 1; }
/usr/bin/cmp -s "$source" "$output" || {
  echo "UI smoke output is not byte-identical to the source." >&2
  exit 1
}
after_hash=$(/usr/bin/shasum -a 256 "$source" | /usr/bin/awk '{print $1}')
[[ "$before_hash" == "$after_hash" ]] || {
  echo "UI smoke changed the source hash." >&2
  exit 1
}
[[ "$(basename "$output")" == 75589_*Zero-shot_Image_Classification.pdf ]] || {
  echo "UI smoke filename did not include the saved number and detected title: $output" >&2
  exit 1
}

echo "App UI smoke passed: approval, copy, filename, source hash, and regular output verified."
echo "output=$output"
