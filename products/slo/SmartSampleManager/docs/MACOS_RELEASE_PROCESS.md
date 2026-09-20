# SmartSampleManager — macOS Release Process

Phase 2, Sections 36-39. Defines the end-to-end macOS release process. **Signing/notarization/
clean-machine steps are documented but not executed this pass** — all require credentials or a
physical/VM clean machine flagged in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`.

## Process

```text
1. Tag a release version (e.g. v1.0.0) in git
    ↓
2. Release CI workflow triggers (see docs/INSTALLER_ARCHITECTURE.md's CI-boundary section --
   not yet built)
    ↓
3. Build Release configuration -- NOT Debug (docs/PERFORMANCE_BASELINE_RELEASE.md already
   established Release vs Debug perf/behavior differences worth knowing about, e.g. the
   full-scan-cost anomaly noted there -- ship what's actually been measured)
    ↓
4. Verify runtime dependencies are bundled per docs/RUNTIME_DEPENDENCY_STRATEGY.md
   (not yet implemented -- release gate, not yet passable)
    ↓
5. codesign every bundle (VST3/AU/Standalone) -- Developer ID Application cert
    ↓
6. Build .pkg installer (docs/INSTALLER_ARCHITECTURE.md)
    ↓
7. productsign the .pkg -- Developer ID Installer cert
    ↓
8. notarytool submit --wait
    ↓
9. stapler staple
    ↓
10. Clean-machine test (docs/HUMAN_COMMERCIAL_REQUIREMENTS.md) -- must pass before any public
    distribution
    ↓
11. Publish
```

## Release gates (must all pass before step 11)

- [ ] Release build (not Debug) — confirmed via `CMAKE_BUILD_TYPE=Release`
- [ ] All 9 regression tests pass (`docs/TEST_COVERAGE_AUDIT.md`)
- [ ] Runtime dependencies bundled, no Homebrew requirement (`docs/RUNTIME_DEPENDENCY_STRATEGY.md`)
- [ ] Every bundle codesigned with a valid Developer ID
- [ ] `.pkg` notarized and stapled
- [ ] Clean-machine install → scan → AU validate → VST3 load → Standalone launch → embedding
      generation all succeed, on a machine that has never had Homebrew/CMake/ONNX
      Runtime/TagLib/libsodium installed
- [ ] Release manifest assertion (no sibling-plugin artifact in the output — see
      `docs/RELEASE_MANIFEST.md`)

## What's actually been verified so far (this session)

- Debug build: all 9 regression tests pass (`docs/TEST_COVERAGE_AUDIT.md`).
- Release build: `BenchmarkScan` built and run successfully at multiple tiers
  (`docs/PERFORMANCE_BASELINE_RELEASE.md`, `docs/MEMORY_PROFILE.md`) — confirms the Release
  configuration itself builds and runs correctly, though the full regression suite wasn't
  re-run under Release this pass (the 9 tests were all run under Debug).
- Nothing beyond that — no signing, no notarization, no installer, no clean-machine test have
  been attempted, since all require credentials/hardware this development environment doesn't
  have (see `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`).

## Recommended next step once credentials exist

Re-run the full 9-test regression suite under a Release build (not yet done — only Debug has the
complete regression-suite confirmation) before attempting the first real signed release, so
"Release build works" isn't resting solely on the benchmark harness having run correctly.
