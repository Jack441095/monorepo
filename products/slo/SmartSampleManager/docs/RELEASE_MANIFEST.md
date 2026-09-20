# SLO — Release Manifest

Phase 1, Section 3. Deterministic definition of what ships in a commercial release. Anything not listed here must not be packaged, uploaded, or referenced from the website's download page.

**Phase 3 note**: unchanged this phase — Phase 3 was commercial-architecture design work only, no
build/release code changed. `docs/NITE_DSP_DATABASE_SCHEMA.md`'s `releases` table now formally
tracks each shipped artifact's `checksum_sha256`/`storage_key`/immutability rule, which this
manifest's build-output definition feeds into once a real release pipeline exists
(`docs/DOWNLOAD_ARCHITECTURE.md`).

## Build identity (from CMakeLists.txt)

**Current identity** — SLO display name applied; legacy project and host identifiers retained for
compatibility (`docs/FINAL_PRODUCT_IDENTITY.md`):

```text
project(SmartSampleManager VERSION 1.0.0 LANGUAGES C CXX)
COMPANY_NAME            "NITE DSP"
COMPANY_COPYRIGHT        "Copyright (c) 2026 NITE DSP. All rights reserved."
PRODUCT_NAME             "SLO"
BUNDLE_ID                com.nitedsp.smartsamplemanager
PLUGIN_MANUFACTURER_CODE NDSP
PLUGIN_CODE               AtSm
FORMATS                   VST3 AU Standalone
```

These four-character codes (`NDSP`, `AtSm`) and the bundle ID are load-bearing for host plugin identification, now applied and treated as permanently immutable per `docs/PRODUCT_IDENTITY_DECISIONS.md` and enforced automatically by `scripts/verify_identity_manifest.py` against `docs/APPROVED_IDENTITY_MANIFEST.json`.

## Shipped binary artefacts (one per platform build)

```text
SLO.vst3                         VST3 bundle   — qualification/release size varies by configuration;
                                                    a Release build will be smaller, not yet measured)
SLO.component                   AU bundle
SLO.app                         Standalone
```

Each bundle currently embeds its own full copy of `panns_cnn10_embedding.onnx` + `.onnx.data` (confirmed via `find` — each `Contents/Resources/` directory installs both files independently). This is JUCE's default resource-copy behavior. At current model size (~24 MB `.onnx.data` + ~84 KB `.onnx`) this triples on-disk footprint across VST3+AU+Standalone but is not a functional problem — noting it here since a future optimization (shared resource location) is a P3, not a blocker.

## Required resources (per-bundle, already embedded by the build)

```text
panns_cnn10_embedding.onnx          PANNs Cnn10 model graph
panns_cnn10_embedding.onnx.data     PANNs Cnn10 weights (external data file)
Icon.icns / AppIcon-1024.png        app/plugin icon
moduleinfo.json                     VST3-format metadata (VST3 bundle only)
THIRD_PARTY_NOTICES.txt             real license texts for every dependency that ships
                                     inside the bundle (Phase 2 addition — see
                                     docs/RUNTIME_DEPENDENCY_STRATEGY.md's "Attribution
                                     Requirement" column; assembled directly from each
                                     dependency's own vendored LICENSE file, not
                                     hand-transcribed, to guarantee accuracy)
```

## Required runtime libraries (bundled — Phase 2 update)

```text
Contents/Frameworks/libtag.dylib           TagLib
Contents/Frameworks/libonnxruntime.dylib   ONNX Runtime
Contents/Frameworks/libsodium.dylib        libsodium
```

**No longer a Homebrew-time-only dependency.** These three are still resolved via Homebrew
`find_library`/`find_path` at *build* time (still unpinned versions — see
`docs/THIRD_PARTY_LICENSES.md`), but a `cmake/BundleAppleDeps.cmake` `POST_BUILD` step now copies
each into every format's `Contents/Frameworks/` and rewrites the bundle's executable to load them
via `@rpath` instead of the Homebrew-time absolute path. Verified locally by hiding this
development machine's own Homebrew install paths and confirming the built app still launches and
initializes ONNX Runtime + CoreML correctly using only the bundled copies — see
`docs/RUNTIME_DEPENDENCY_STRATEGY.md` for the full implementation detail and the caveat that this
is a strong local proxy, not the real clean-machine test still required before beta
(`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`). No longer flagged as P0 in
`docs/COMMERCIAL_RELEASE_BLOCKERS.md` — the implementation itself is done; only the real
clean-machine verification and codesigning/notarization remain.

## Explicitly excluded from any release build

```text
build/_deps/                        FetchContent source checkouts (JUCE, umappp, hnswlib, dr_libs, etc.)
                                     — build-time only, never packaged
licensing_server/                   dev/test backend — never ships inside the client
licensing_server/.venv/             dev Python environment
licensing_server/licensing.db*      dev SQLite database
licensing_server/keys/              dev Ed25519 keypair — must never leave the (eventual) production
                                     server, let alone ship in a client build
model_export/                       PyTorch→ONNX export tooling, not needed at runtime
generate_dummy_model.py             untrained placeholder-model generator — superseded by the real
                                     trained model, must not end up in a shipped bundle
*.wav test fixtures (real_kick_a.wav, real_kick_b.wav, real_sustained_noise.wav,
    test_kick.wav, test_unique.wav)                          test fixtures, not product assets
Test* executables (TestSampleEngine, TestPathTraversal, etc.)  CI/dev tooling only
docs/                                                          internal audit/planning docs (also
                                                                 gitignore'd repo-wide by policy)
```

## Sibling-project exclusion (structural, not just documentary)

Because SmartSampleManager is `add_subdirectory()`'d from the umbrella `vst3_plugins/CMakeLists.txt` alongside `AudioToo_Reverb`, `KENNMixAssistant`, and `MidiGenerator`, a release pipeline must invoke:

```bash
cmake --build build --target SmartSampleManager_VST3 SmartSampleManager_AU SmartSampleManager_Standalone
```

from within `SmartSampleManager/build/` (exactly as CI already does — see `.github/workflows/smart-sample-manager.yml`), never a bare `cmake --build .` from the umbrella `vst3_plugins/` directory, which would also build the unrelated sibling plugins.

**Phase 2 update — this is now an automated, enforced check, not just a documented rule.**
`scripts/verify_release_manifest.py` walks every file inside a built bundle and compares it
against an explicit per-format allowlist (built from the actual, real file listing of a working
build — not guessed), failing loudly (`RELEASE FAILS`, nonzero exit) if anything unexpected
appears, with an explicit forbidden-pattern list catching sibling-plugin artifacts
(`AudioToo_Reverb`, `KENNMixAssistant`, `MidiGenerator`, `KENN`, `AutoMix`, `AudioGen`) by name.
Wired into `.github/workflows/smart-sample-manager.yml` as a `Verify release manifest` step
immediately after the build step, run against all three built formats. Tested against both the
real, passing case (all three current bundles) and a deliberately-corrupted copy (injected fake
`KENNMixAssistant_leftover.txt`, a random unexpected file, and a missing required file) —
correctly caught all three violation types with a clear, itemized failure message.

## What this manifest does not yet cover

Code signing, notarisation, and installer packaging (macOS `.pkg`, Windows `.exe`/`.msi`) are not
built yet — see `docs/COMMERCIAL_RELEASE_BLOCKERS.md`. This manifest defines *build output*, not
*distribution artefact*. **Phase 2 update**: the target distribution architecture for all of this
is now fully designed (not built) — see `docs/INSTALLER_ARCHITECTURE.md` (macOS `.pkg` via
`pkgbuild`/`productbuild`), `docs/RUNTIME_DEPENDENCY_STRATEGY.md` (per-dependency bundling plan
for TagLib/ONNX Runtime/libsodium), and `docs/MACOS_RELEASE_PROCESS.md` (the full signing →
notarizing → clean-machine-testing pipeline). None of it is implemented — all of it requires
either the clean-machine test environment or Apple Developer credentials flagged in
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`.

**Phase 2 test-suite update**: a 10th regression target, `TestResilience`, was added this session
(`docs/TEST_COVERAGE_AUDIT.md`) — like the other 9, it's CI/dev tooling only, never shipped in a
release build, and is already excluded by this manifest's existing `Test* executables` rule
above without needing a new line item.

**Phase 5 update**: two things. First, re-verifying this manifest against the actual
`build-release/` bundles this phase caught a real regression — the directory was stale (built
before Phase 2's dependency-bundling step existed), so all three formats were missing required
files. Fixed by rebuilding; all three now pass again. Second, a companion check was added:
`scripts/verify_identity_manifest.py` against `docs/APPROVED_IDENTITY_MANIFEST.json`, wired into
CI right after the existing manifest check. This manifest governs *file contents*; the new check
governs plugin *identity* (COMPANY_NAME/BUNDLE_ID/PLUGIN_MANUFACTURER_CODE/PLUGIN_CODE/
PRODUCT_NAME) — together they cover both halves of "what actually ships" (docs/PHASE_5_PLAN.md).

**Phase 5.5 update**: `Frameworks/` now legitimately contains ~85 additional dylibs beyond the
original three (`libtag`/`libonnxruntime`/`libsodium`) — ONNX Runtime's own transitive Homebrew
dependencies (abseil/protobuf/re2/utf8_range/utf8_validity), previously unbundled entirely (a
real gap found and fixed this phase, see `docs/PHASE_5_5_FINAL_SYNTHESIS.md`). Listing each by
exact versioned filename would be fragile against a routine Homebrew upgrade, so
`scripts/verify_release_manifest.py` now allows any `Frameworks/*.dylib` via a glob pattern
(`ALLOWED_PATTERNS`) rather than requiring an exact-name entry for each — the `FORBIDDEN_PATTERNS`
check (sibling-plugin names, dev tooling, `.db`/`.py` files) still applies to everything,
including `Frameworks/`, so this loosening does not weaken the actual protection this manifest
exists for. Verified: all three formats pass with the expanded file count (96/95/95).
`cmake/BundleAppleDeps.cmake` is deleted, replaced by `scripts/bundle_apple_deps.py` (Python,
walks the full transitive dependency graph via `otool -L` instead of only handling the three
top-level libs).
