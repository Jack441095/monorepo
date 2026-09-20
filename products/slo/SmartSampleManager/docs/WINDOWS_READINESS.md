# SmartSampleManager — Windows Readiness

Phase 2, Section 40. **Status: UNVERIFIED — not BLOCKED, not SUPPORTED.** This development
session ran entirely on macOS (Apple Silicon). No Windows build, test run, or even a skim-level
CMake compatibility check specific to Windows was performed this pass, beyond what Phase 1
already noted.

## What Phase 1 established (carried forward, not re-verified)

`docs/PRODUCT_READINESS_AUDIT.md`: "the CMakeLists.txt has no obvious macOS-only blockers on a
skim, but nothing was actually built or tested on Windows." That remains true — this phase did
not change that finding.

## Known macOS-specific code paths (identified by reading, not built/tested against Windows)

- `SampleManagerEngine::init()` unconditionally attempts to enable the CoreML execution provider
  (`Source/SampleManagerEngine.cpp`, `coreml_provider_factory.h`) inside a `try`/`catch` that
  already falls back to CPU-only ONNX Runtime on failure — this should degrade gracefully on
  Windows (CoreML simply isn't available, the catch block handles it), but "should" is not
  "verified." A Windows build would exercise this fallback path for the first time.
- `${ACCELERATE_FRAMEWORK}` (Apple's Accelerate framework) is linked conditionally on
  `if(APPLE)` in `CMakeLists.txt` — this guard already exists, so it shouldn't need changes for a
  Windows build, but the DSP code paths that use Accelerate-provided functions (if any beyond
  what a quick read confirms) haven't been audited for a Windows-equivalent math library
  requirement in this pass.
- `getSpecialLocation(juce::File::userApplicationDataDirectory)` (used for the SQLite cache path
  in `openCacheDb()`) is a JUCE cross-platform API — should resolve correctly to
  `%APPDATA%`-equivalent on Windows without code changes, per JUCE's own documented behavior, but
  not tested.
- Unicode path handling — the master prompt specifically calls this out (Section 40) as a thing
  to verify. Not tested this pass; `juce::File` is documented as UTF-8/UTF-16-safe cross-platform,
  but a real test with non-ASCII sample library paths hasn't been run on any platform, Windows or
  macOS.

## What would be required to move from UNVERIFIED to VERIFIED

1. A Windows x64 build machine (flagged in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` as "REQUIRED
   BEFORE WINDOWS RELEASE").
2. `cmake -B build -S . -DCMAKE_BUILD_TYPE=Release` (or Debug first, matching this session's
   macOS approach of validating Debug before attempting Release) on that machine — first checks
   whether the existing `CMakeLists.txt` even configures cleanly under MSVC/Windows without
   changes.
3. Resolve Windows-specific dependency acquisition for TagLib/ONNX Runtime/libsodium — the
   current `find_path`/`find_library` Homebrew-path search (`/usr/local/include`,
   `/opt/homebrew/include`) has no Windows equivalent paths configured at all; this would need
   `vcpkg`, Windows binary distributions of each library, or the same `FetchContent`-based
   approach recommended for libsodium in `docs/RUNTIME_DEPENDENCY_STRATEGY.md`, generalized to
   Windows.
4. Run the full 9-test regression suite (`docs/TEST_COVERAGE_AUDIT.md`) on Windows — a clean
   pass there is the actual bar for "Windows build works," not just "it compiles."
5. Only after 1-4 succeed: choose a Windows installer tool (Inno Setup/WiX/NSIS — not evaluated
   this pass, premature before a working build exists) and a Windows code-signing certificate
   (flagged in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`).

## Explicit non-claim

**No Windows compatibility claim should appear anywhere public** (website, product listing,
marketing copy) until step 4 above has actually run and passed. `docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`
already reflects this — the homepage's compatibility section is written to mark Windows as
unverified rather than silently listing it as supported.
