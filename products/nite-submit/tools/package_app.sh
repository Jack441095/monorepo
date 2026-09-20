#!/bin/zsh
# Build Submit.app (unsigned development build) into artifacts/.
set -e
cd "$(dirname "$0")/.."
APP_NAME="Submit"
# Single source of truth for the version (RELEASE FACTORY V1): the VERSION
# file at repo root. Scripts must read it, never hardcode it.
VERSION="$(<./VERSION | tr -d '[:space:]')"
[[ -n "$VERSION" ]] || { echo "ERROR: VERSION file missing/empty" >&2; exit 1; }
BUNDLE_ID="com.nitedsp.nitesubmit"
BUILD_DIR=".build/release"
OUT="artifacts/${APP_NAME// /}-${VERSION}-macOS"

echo "== swift build (release) =="
swift build -c release --product NiteSubmitApp
swift build -c release --product nitesubmit-cli

rm -rf "$OUT.app" "$OUT-cli"
mkdir -p "$OUT.app/Contents/MacOS" "$OUT.app/Contents/Resources/bin" "$OUT.app/Contents/Resources/lib"

cp "$BUILD_DIR/NiteSubmitApp" "$OUT.app/Contents/MacOS/NiteSubmit"
cp "$BUILD_DIR/nitesubmit-cli" "$OUT.app/Contents/MacOS/nitesubmit-cli"

# Bundled 7za (arm64, LGPL 2.1, from the p7zip project) gives every user real LZMA2 7z
# compression out of the box, without depending on them having separately installed
# anything — see tools/bin/7za-LICENSE-LGPL-2.1.txt for license text, bundled alongside it
# per LGPL redistribution terms.
cp "$PWD/tools/bin/7za" "$OUT.app/Contents/Resources/bin/7za"
chmod +x "$OUT.app/Contents/Resources/bin/7za"
cp "$PWD/tools/bin/7za-LICENSE-LGPL-2.1.txt" "$OUT.app/Contents/Resources/bin/7za-LICENSE-LGPL-2.1.txt"

# Bundled qpdf (arm64, Apache-2.0) gives lossless PDF size optimization out of the box.
# Its shared libraries (libqpdf, libjpeg, libcrypto) are bundled alongside it with their
# load paths already rewritten to @loader_path/@executable_path (see PDFOptimizer.swift's
# bundledQPDFPath()) — this tool never depends on Homebrew or any system-installed copy.
cp "$PWD/tools/bin/qpdf" "$OUT.app/Contents/Resources/bin/qpdf"
chmod +x "$OUT.app/Contents/Resources/bin/qpdf"
cp "$PWD/tools/lib/libqpdf.30.dylib" "$OUT.app/Contents/Resources/lib/libqpdf.30.dylib"
cp "$PWD/tools/lib/libjpeg.8.dylib" "$OUT.app/Contents/Resources/lib/libjpeg.8.dylib"
cp "$PWD/tools/lib/libcrypto.3.dylib" "$OUT.app/Contents/Resources/lib/libcrypto.3.dylib"
cp "$PWD/tools/lib/qpdf-LICENSE-Apache-2.0.txt" "$OUT.app/Contents/Resources/bin/qpdf-LICENSE-Apache-2.0.txt"
cp "$PWD/THIRD_PARTY_NOTICES.md" "$OUT.app/Contents/Resources/THIRD_PARTY_NOTICES.md"

cat > "$OUT.app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key><string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
    <key>CFBundleVersion</key><string>${VERSION}</string>
    <key>CFBundleShortVersionString</key><string>${VERSION}</string>
    <key>CFBundleExecutable</key><string>NiteSubmit</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSPrincipalClass</key><string>NSApplication</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key><string>Portable Document Format</string>
            <key>CFBundleTypeRole</key><string>Viewer</string>
            <key>LSHandlerRank</key><string>Alternate</string>
            <key>LSItemContentTypes</key>
            <array><string>com.adobe.pdf</string></array>
            <key>CFBundleTypeExtensions</key>
            <array><string>pdf</string></array>
        </dict>
    </array>
</dict>
</plist>
PLIST

cp "$PWD/tools/AppIcon.icns" "$OUT.app/Contents/Resources/AppIcon.icns"

codesign --force --deep -s - "$OUT.app" 2>/dev/null || echo "(ad-hoc sign skipped)"
"$PWD/tools/verify_app_bundle.sh" "$OUT.app"
"$PWD/tools/cleanup_old_release_artifacts.sh" "$VERSION"

echo "== artifact =="
du -sh "$OUT.app"
shasum -a 256 "$OUT.app/Contents/MacOS/NiteSubmit"
