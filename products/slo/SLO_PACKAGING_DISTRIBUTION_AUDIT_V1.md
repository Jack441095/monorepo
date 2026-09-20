# SLO Packaging and Distribution Audit V1

## Current bundle checks

- AU and VST3 installed bundles are arm64.
- Release manifests account for 95 AU files and 96 VST3 files.
- Bundled ONNX, TagLib, ONNX Runtime, and libsodium dependencies are present; no forbidden Homebrew dependency paths were found.
- Deep/strict codesign verification passes only as ad-hoc verification; `TeamIdentifier` is not set.
- Plugin auto-install is disabled by default in CMake.

## Blockers

No Developer ID identity, notarization ticket, signed installer/update flow, or clean-machine installation evidence was available. The build machine uses Command Line Tools rather than full Xcode. A bundle that validates locally is not yet a distributable release.

## Decision

Packaging is **PASS WITH LIMITATIONS** for local engineering artifacts and **BLOCKED** for external beta distribution.
