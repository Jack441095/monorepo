#!/bin/zsh
# Local macOS UI smoke check. Requires Accessibility permission for
# /usr/bin/osascript to control Submit through System Events.
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=$(tr -d '[:space:]' < "$product_dir/VERSION")
app="$product_dir/artifacts/Submit-${version}-macOS.app"
source="$product_dir/real_validation_corpus/public_examples/75589_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf"
results_dir="$product_dir/real_validation_corpus/test_results/app_ui_smoke_current"
input="$results_dir/input.pdf"

[[ -x "$app/Contents/MacOS/NiteSubmit" ]] || {
  echo "Packaged app not found; run ./tools/package_app.sh first." >&2
  exit 1
}
[[ -f "$source" ]] || { echo "Smoke PDF not found: $source" >&2; exit 1; }
if /usr/bin/pgrep -x NiteSubmit >/dev/null 2>&1; then
  echo "Submit is already running; close it before the UI smoke check." >&2
  exit 1
fi

/bin/mkdir -p "$results_dir"
if [[ -L "$input" || -e "$input" ]]; then
  /bin/unlink "$input"
fi
# Only generated outputs from this exact smoke directory are removed. The
# source corpus and every other test-results directory are outside this scope.
/usr/bin/find "$results_dir" -maxdepth 1 -type f -name '75589_*.pdf' -exec /bin/unlink {} +

cleanup() {
  /usr/bin/osascript -e 'tell application id "com.nitedsp.nitesubmit" to quit' >/dev/null 2>&1 || true
  if [[ -L "$input" ]]; then /bin/unlink "$input"; fi
}
trap cleanup EXIT INT TERM

before_hash=$(/usr/bin/shasum -a 256 "$source" | /usr/bin/awk '{print $1}')
/bin/ln -s "$source" "$input"
open -n "$app" --args "$input"
/bin/sleep 3

/usr/bin/osascript <<'APPLESCRIPT'
tell application "System Events"
  tell process "NiteSubmit"
    repeat until (exists window 1)
      delay 0.25
    end repeat
    set frontmost to true
    if exists button "Approve details" of window 1 then
      click button "Approve details" of window 1
      delay 0.5
      click button "Create submission" of window 1
    else if exists button "Approve Details" of scroll area 1 of window 1 then
      click button "Approve Details" of scroll area 1 of window 1
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
[[ "$(basename "$output")" == 75589_*_An_Ecosystem_of_Custom_Laser_Controlled_Devices.pdf ]] || {
  echo "UI smoke filename did not include the saved number and detected title: $output" >&2
  exit 1
}

echo "App UI smoke passed: approval, copy, filename, source hash, and regular output verified."
echo "output=$output"
