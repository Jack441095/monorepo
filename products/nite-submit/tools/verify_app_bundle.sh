#!/bin/zsh
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/Submit.app" >&2
  exit 2
fi

app_path="$1"
plist_path="$app_path/Contents/Info.plist"
binary_path="$app_path/Contents/MacOS/NiteSubmit"
cli_path="$app_path/Contents/MacOS/nitesubmit-cli"
resources_path="$app_path/Contents/Resources"

[[ -d "$app_path" ]] || { echo "App bundle not found: $app_path" >&2; exit 1; }
[[ -f "$plist_path" ]] || { echo "Info.plist missing" >&2; exit 1; }
[[ -x "$binary_path" ]] || { echo "App executable missing or not executable" >&2; exit 1; }
[[ -x "$cli_path" ]] || { echo "Bundled CLI missing or not executable" >&2; exit 1; }

for required_path in \
  "$resources_path/AppIcon.icns" \
  "$resources_path/THIRD_PARTY_NOTICES.md" \
  "$resources_path/bin/7za" \
  "$resources_path/bin/qpdf" \
  "$resources_path/bin/7za-LICENSE-LGPL-2.1.txt" \
  "$resources_path/bin/qpdf-LICENSE-Apache-2.0.txt" \
  "$resources_path/lib/libqpdf.30.dylib" \
  "$resources_path/lib/libjpeg.8.dylib" \
  "$resources_path/lib/libcrypto.3.dylib"; do
  [[ -f "$required_path" ]] || {
    echo "Required bundled resource missing: $required_path" >&2
    exit 1
  }
done

bundle_id=$(plutil -extract CFBundleIdentifier raw -o - "$plist_path")
[[ "$bundle_id" == "com.nitedsp.nitesubmit" ]] || {
  echo "Unexpected bundle identifier: $bundle_id" >&2
  exit 1
}

bundle_name=$(plutil -extract CFBundleName raw -o - "$plist_path")
display_name=$(plutil -extract CFBundleDisplayName raw -o - "$plist_path")
executable_name=$(plutil -extract CFBundleExecutable raw -o - "$plist_path")
[[ "$bundle_name" == "Submit" && "$display_name" == "Submit" ]] || {
  echo "User-facing app name must be Submit (bundle=$bundle_name display=$display_name)" >&2
  exit 1
}
[[ "$executable_name" == "NiteSubmit" ]] || {
  echo "Internal executable name changed unexpectedly: $executable_name" >&2
  exit 1
}

document_type=$(plutil -extract CFBundleDocumentTypes.0.LSItemContentTypes.0 raw -o - "$plist_path")
[[ "$document_type" == "com.adobe.pdf" ]] || {
  echo "PDF document association missing" >&2
  exit 1
}

version=$(tr -d '[:space:]' < "$(dirname "$0")/../VERSION")
bundle_version=$(plutil -extract CFBundleShortVersionString raw -o - "$plist_path")
[[ "$bundle_version" == "$version" ]] || {
  echo "Bundle version $bundle_version does not match VERSION $version" >&2
  exit 1
}

for executable in "$binary_path" "$cli_path" "$resources_path/bin/7za" "$resources_path/bin/qpdf"; do
  file "$executable" | grep -q 'arm64' || {
    echo "Bundled executable is not arm64: $executable" >&2
    exit 1
  }
done

codesign --verify --deep --strict "$app_path"
echo "Bundle verification passed: $app_path"
