# SLO — BETA READINESS V1

**Date:** 2026-09-30
**Verdict:** `NOT READY` for a closed beta
**Prior state:** build reported as both broken and fixed; accuracy figures in conflict; a plugin crash on a small library
**Reviewer:** full code review + repair (`docs/SLO_REVIEW_V1.md`)
**Product root:** `monorepo/products/slo`
**Reviewed HEAD:** `bec0161` (review pass), repairs committed on `main` after it

Every finding below was re-verified by running it. Where something could not be verified on this machine, it says so rather than asserting.

---

## D1 — The two owner questions

### Which V2 run is current: 77.9% / 17.5%, or 71.5% / 39.0%?

**Unresolved, and it cannot be settled from the repository.** Both figures describe the same 5,157-file corpus and both landed in commit `f4a90d2c`.

- `SmartSampleManager/docs/classification/REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md:23-25` records 77.9% full-evidence, 17.5% audio-only, macro-F1 0.528 / **0.073**. The artifact is internally consistent: 4017/5157 = 77.89% with 1140 errors, and its evidence rows sum correctly.
- `OOD_RECALIBRATION_V1_REPORT.md:36,72` records 39.0% audio-only and calls it the *pre-recalibration baseline*, claiming the end-to-end re-run "re-confirmed at exactly" 39.0% / 71.5%. That run explicitly included `MlOverrideGate` and `AbletonTaxonomy::classify()`.

So the two reports are not necessarily measuring the same thing: the OOD run describes the full production path, and a 5.4× gap on audio-only macro-F1 is the shape you get when one run includes the decision gates and the other does not. That is a hypothesis, not a finding.

I could not re-run the benchmark to settle it: `perch_clean.onnx` and the other model blobs are present, but the corpus itself (`sample_pack_testing`) is not on this machine, and neither is the V2 corpus manifest. **The corpus has to be restored before this can be answered, and no figure should be quoted as current until it is.**

Every document that quoted either number now carries an `UNVERIFIED` banner naming both sources, rather than my picking one.

### Scrub the personal paths from git history, or accept the exposure?

**Forward-fixed; history is still exposed and that is your call.** `products/slo/.gitignore` now excludes the benchmark result dumps by content class, and `scripts/check_no_personal_paths.sh` fails the build if a tracked file contains a home-directory or media-library path. Tracked-file occurrences of the volume path: **168,749 → 0**. The remote GPU host root is gone too, replaced by `SLO_TRAIN_DATA` / `SLO_MODEL_OUT` environment variables.

The data is still in four commits, so `git log -p` still yields the owner's real name, commercial library vendors, and folder structure. Rewriting history invalidates every existing clone and SHA, and `SLO_PRODUCT_TRUTH_MANIFEST_V1.json` has just had all five of its phantom SHAs retracted — rewriting would invalidate more. **My recommendation: accept it and move on, unless this repo is ever made public.** The gate prevents recurrence; the exposure is historical.

---

## D2 — Versions and identity

| Constant | Value | Source |
|---|---|---|
| `PRODUCT_NAME` | `SLO` | `CMakeLists.txt:491` |
| `BUNDLE_ID` | `com.nitedsp.smartsamplemanager` | `:481` — **still the pre-rename identity** |
| `PLUGIN_CODE` | `AtSm` | `:489` — **still the pre-rename identity** |
| `FORMATS` | `VST3 AU Standalone` | `:490` |
| `kTaxonomyVersion` | **5** | `AbletonTaxonomy.h:45` |
| `kFeatureAnalysisVersion` | **8** | `SampleManagerEngine.h:134` |

Two audits asserted taxonomy version 2. That is the cache-invalidation gate, so a stale v2 cache reclassifies on load. Corrected in the truth manifest. `kFeatureAnalysisVersion` is still documented nowhere; recorded in the manifest.

The bundle identity is a genuine open owner decision, not an oversight — `docs/FINAL_PRODUCT_IDENTITY.md:210` records a proposal to change it. Two audits said the whole identity was unfixed (wrong: `PRODUCT_NAME` is done) while the roadmap still described it as "formerly Smart Sample Manager" (the master plan had already excluded renames from beta scope). All three now say what is actually true.

## D3 — Build

**The `FAIL` in `slo_test_results_v1.json` is stale. B-012 is genuinely closed.**

```
/opt/homebrew/bin/cmake --preset ssm-release-candidate    Configuring done (179.3s)
/opt/homebrew/bin/cmake --build . -j8                     [100%], 0 errors
```

No `ld: 13044 duplicate symbols`. The object-library shape both reports described (`CMakeLists.txt:706, 746-748, 768`) is still there and links clean.

**Toolchain note worth keeping:** `/usr/local/bin/cmake` on this machine is an **x86_64** binary and cannot configure on this arm64 host — it dies with `libxcrun.dylib … need 'x86_64'`. `/opt/homebrew/bin/cmake` 4.4.3 (arm64) works. Any doc that says `cmake --preset` without qualifying the binary will fail confusingly on Apple Silicon.

### Test inventory, recounted

`ssm_add_engine_test()` × **40** + `add_executable()` × **18** = 58 registered, **55 unique test binaries built**. The corpus claimed 31, and nine different denominators existed across the reports (31, 34, 37, 41, 46/47, 28, 55).

```
55 test binaries: 54 PASS, 1 FAIL
```

The single failure is `TestLicensing`, which requires a live licence key and prints its usage instead. That is the documented owner/environment-blocked case, not a code failure.

Missing from the old inventory, now built and passing: `TestFormatAwareScan`, `TestSortPreviewAndUndo`, `TestReadOnlySafetyQualification`, `TestRtDeadlineStress`, `TestDiagnosticsBundle`, `TestFusionV2`, `TestLoopV2`, `TestUmapEligibility`, `TestPathIndexIntegrity`, `TestInferenceBatchFlush`, `TestBetaDecisionPolicy`, `TestBetaSortGate`, `TestPhysicalAcoustics`, `TestCachedReclassification`, and others.

## D4 — Python suite

```
python3 -m pytest        368 passed in 41.47s
```

Was 358 passing plus 3 collection errors that made a bare `pytest` abort before a single assertion ran. `conftest.py` now excludes the three research scripts named `test_*` that contain no test functions and load a gitignored 100 MB `.npz` at import. New this pass: `TestQuadTreeCoincidentPoints` (7 checks, C++) and 10 Python checks across the adversarial-metric and macro-F1 suites.

## D5 — Local-only promise

No `WebInputStream` or `juce::URL` anywhere in `Source/` except `Licensing/LicenseManager.cpp`. No telemetry symbol in the tree. **Holds.**

Licensing fails closed on URL policy — HTTPS except literal loopback, user-info rejected to block lookalike-host credential smuggling, exercised at `test_licensing_main.cpp:44-50`. But `LicenseManager` is display-only, and three things must be fixed before anything gates on it: the shipped public key is the local mock's, `verifyAndDecode` never checks `product_id` or `tier`, and the default endpoint is `http://localhost:8420`.

## D6 — Read-only safety

Re-proven by the real mechanism, not a proxy: `test_readonly_safety_qualification_main.cpp` does libsodium `crypto_hash_sha256` over raw bytes before and after, and writes a receipt. Passes.

Sort defaults to **copy** — `SampleManagerEngine.h:822` `copyInsteadOfMove = true`, and `PluginEditor.cpp:1839` passes `true` explicitly. Two safety audits said move-by-default. Both were wrong in the direction that *understates* safety, which is worse than overstating it; both now corrected.

## D7 — Secrets and personal data

No credentials, no API keys, no private keys. No non-loopback IPs. `.wav`, `test_cpp_parity_standalone`, and all model blobs correctly ignored. `slo_corrections.db` now ignored (it holds `file_path` and `user_note` for licensed samples; the previous rule covered `*.sqlite3` but not `*.db`).

Gates added, both verified to pass **and** verified to fail on a planted violation:
- `scripts/check_release_truth.sh` → `release-truth-gate=pass reports=78`
- `scripts/check_no_personal_paths.sh` → `personal-path-gate=pass tracked_files=1210`

## D8 — Reports reconciled

- 14 commit references retracted, across 12 documents, with `release-truth-gate` now enforcing it.
- WAV-only retracted in 8 documents, with owner decision D-1 rewritten to the real remaining question (MP3/OGG).
- V2 accuracy figures marked `UNVERIFIED` in 5 documents.
- The scorecard's evidence-source claim corrected: 81.2% is the FILENAME row and 98.5% the FOLDER row; the 77.9% it was paired with is the overall figure.
- `docs/INDEX.md` published.

Still stale, recorded in `docs/SLO_BETA_BLOCKERS_V1.md`: every docs-side line citation for the mutation path points at the wrong lines in a 7,407-line file; `README.md` is 7 lines and names a worktree path that does not exist; `slo_test_results_v1.json` still carries the old `FAIL` and build path (annotated, not rewritten, because the corpus gate could not be re-run to regenerate it); `SLO_BETA_BLOCKER_REGISTER_V2.md` cites two master-plan files that do not exist.

## D9 — Owner decisions, as they now stand

1. **MP3/OGG decode for Beta 1.** AIFF/FLAC already ship; the older "WAV-only vs multi-format" framing is retired.
2. **Restore the V2 benchmark corpus and re-measure.** No accuracy claim is quotable until this is done.
3. **Bundle identity.** Migrate `com.nitedsp.smartsamplemanager` / `AtSm` to the SLO identity, or record that the old one is retained deliberately.
4. **Product version scheme.** `product_version` is still `null` in the truth manifest.
5. **Signing and clean-machine qualification.** Never executed; no Developer ID certificate on this machine.
6. **History scrub for the personal paths.** Recommendation is to accept; see D1.

---

## Sign-off checklist

- [x] Clean Release build from HEAD, 0 errors
- [x] Test suite green — 54/55 C++ binaries, 1 environment-blocked; 368 Python
- [x] No network in scan/classify/sort, verified in source
- [x] No committed secrets; personal paths removed from the tree and gated
- [x] Third-party model blobs correctly ignored
- [x] Read-only safety re-proven with real SHA-256
- [x] Every cited commit reference resolves or is explicitly retracted
- [x] Every load-bearing doc claim re-verified against source
- [ ] **V2 accuracy re-measured** — corpus missing, both figures unresolvable
- [ ] **Plugin crash on a small library fixed and covered** — fixed and covered; needs a soak on a real library
- [ ] **Licence public key is not the mock's** — required before licensing gates anything
- [ ] **Bundle identity decision recorded**
- [ ] **Signed and clean-machine qualified** — no Developer ID certificate available

## Verdict

`NOT READY`. The two P0 classes from the review are fixed and tested: the plugin no longer crashes on a library without embeddings, and the audio callback no longer frees a file handle or races the message thread. Documentation that lied about the product no longer does, and gates now stop it lying again.

What blocks a beta is narrow and mostly not code. One benchmark corpus has to be restored so the accuracy numbers can be measured rather than argued about. The licence public key must be replaced with the real one before licensing gates anything. The bundle identity needs a decision. And signing has never been attempted, because there is no Developer ID certificate on this machine — that one has been open since at least the 2026-08-20 session status report.
