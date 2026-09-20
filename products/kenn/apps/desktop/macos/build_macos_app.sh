#!/bin/zsh
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
app_dir="$script_dir/dist/KENN Desktop Companion.app"
macos_dir="$app_dir/Contents/MacOS"

rm -rf "$app_dir"
mkdir -p "$macos_dir"
cp "$script_dir/Info.plist" "$app_dir/Contents/Info.plist"

swiftc "$script_dir/KENNDesktopCompanion.swift" \
  -o "$macos_dir/KENNDesktopCompanion" \
  -framework Cocoa -framework WebKit
codesign --force --deep --sign - "$app_dir" >/dev/null
echo "$app_dir"
