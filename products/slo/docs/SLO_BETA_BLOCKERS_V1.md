# SLO — BETA BLOCKERS V1

**Date:** 2026-09-30
**Status:** 4 open, 11 closed this pass. Three of the four are owner actions, not code.

Full evidence in `docs/SLO_REVIEW_V1.md`; gate verdict in `docs/SLO_BETA_READINESS_V1.md`.

---

## Open

### P0 — Owner: restore the V2 benchmark corpus and re-measure

**Evidence.** Two incompatible results for the same 5,157 files, both in commit `f4a90d2c`:
`REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md:23-25` says 77.9% / 17.5%, macro-F1 0.528 / **0.073**; `OOD_RECALIBRATION_V1_REPORT.md:36,72` says 39.0% audio-only and calls it the re-confirmed baseline of a run that included `MlOverrideGate` and `AbletonTaxonomy::classify()`. Seven documents quoted the latter. The macro-F1 gap is 5.4×.

**Cannot be resolved from the repository.** The model blobs are present but the corpus (`sample_pack_testing`) and the V2 manifest are not on this machine.

**Fix steps.**
1. Restore the corpus and `real_corpus_v2_manifest.json`.
2. Re-run `run_real_corpus_v2_benchmark.py` and record which code path it exercises.
3. Publish one figure set, with both axes reported together as the artifact instructs at `:26-27`, and retire the other with a pointer.
4. Remove the `UNVERIFIED` banners this pass added to five documents.

Until then, no SLO accuracy number is quotable to a customer or an investor.

### P0 — Owner: replace the licence public key

**Evidence.** `SmartSampleManager/Source/Licensing/LicensePublicKey.h:3-13` ships the local mock server's public key; the private half is in `licensing_server/`, so anyone with the repository can mint valid tokens for the real binary. No `#if DEBUG` guard, no build-config switch. `LicenseManager.cpp:78` defaults to `http://localhost:8420`. `verifyAndDecode:200-209` never checks `product_id` or `tier`, so a token for a different product signed by the same key would validate.

**Currently harmless** — `LicenseManager` is display-only (`PreferencesWindow.cpp:105-124`) and nothing gates on `Status`. That is exactly why it must be fixed before it does.

**Fix steps:** generate a real release keypair, keep the private half offline, ship only the public half, and add the `product_id`/`tier` check plus a nil-object guard at `:297,345,368`.

### P0 — Owner: Developer ID certificate, signing, clean-machine qualification

**Evidence.** Never executed, and reported as such since at least `docs/SLO_SESSION_STATUS_2026-08-20.md`. No certificate is installed on this machine. `SLO_PRODUCT_TRUTH_MANIFEST_V1.json` `release_authority.signing` is `not executed`.

**Fix steps:** install a Developer ID Application certificate, sign and notarize, then run the plugin in a real DAW on a clean machine and record the result. This is the only item on the list that requires a purchase.

### P1 — Owner: decide the bundle identity

`BUNDLE_ID "com.nitedsp.smartsamplemanager"` (`CMakeLists.txt:481`) and `PLUGIN_CODE AtSm` (`:489`) are still the pre-rename identity while `PRODUCT_NAME` is `SLO` (`:491`). `docs/FINAL_PRODUCT_IDENTITY.md:210` records a proposal; nobody has ruled on it. Also open: `product_version` is `null` in the truth manifest.

---

## Closed — 2026-09-30

Each with a regression test where the change was behavioural.

| ID | Was | Fix |
|----|-----|-----|
| B1 | 14 commit references across 12 reports resolved nowhere, including the truth manifest's rollback target | Retracted with reasons; `scripts/check_release_truth.sh` gates it |
| B2 | V2 accuracy 5.4× overstated on audio-only macro-F1 in 7 documents | Marked `UNVERIFIED` with both sources named; the scorecard's separate evidence-source error corrected. Re-measurement is the P0 above |
| B3 | "WAV-only" asserted as critical in 8 documents; the code is format-aware | Retracted in place with the code that contradicts it; owner decision D-1 rewritten to MP3/OGG |
| B4 | `fusion_adversarial_accuracy` unpacked the filename and never used it, so the published 88.29% was accuracy above a confidence threshold | Builds a real adversarial filename; reports override rate and override precision alongside fidelity; 6 new tests |
| B5 | 168,749 personal-path occurrences across 216 tracked files | `.gitignore` keyed to content class, `scripts/check_no_personal_paths.sh` added; tracked occurrences now 0 |
| B6 | `processBlock` move-assigned `readerSource`, freeing a `BufferingAudioReader` and closing a file descriptor on the audio thread | Retired readers published to a wait-free ring and freed on the message thread; destructor drains last |
| B7 | `transportSource` touched from three threads; `stopSample` read it mid-render | Transport is audio-thread-only; `stopSample` sets a flag; `playSample` publishes even when stopped |
| B8 | `QuadTree` recursed forever on 33+ coincident points, crashing the editor on open | Refuses to split a sub-pixel node or a single-coordinate leaf; `TestQuadTreeCoincidentPoints` (7 checks, verified to fail without the guard) |
| B9 | Sort held `dbLock` across every file move, freezing the 60 Hz timer | Three-phase snapshot/sort/publish, matching `runFullUMAP`; publish re-checks the snapshotted path before writing |
| B10 | `slo_corrections.db` not gitignored; holds licensed sample paths and user notes | Ignored, and covered by the personal-path gate |
| C11 | Global `FileLogger` put locked file I/O on the audio callback | No longer installed as the JUCE current logger |
| C12 | Foley tag emitted on one path of five | Applied once after the subcategory resolves |
| C13 | Bare substring match capped every file under Ableton's `Snapshots` folder at `Suggest` | Token-boundary match |
| C15 | Cosine remap squashed the discriminative range; unrelated pairs read ~50% similar; `isValid()` skipped the flag consumers gate on | Both fixed |
| C16 | Macro F1 divided by the full taxonomy, so every absent class scored 0.0 | Averaged over present classes in all three scripts; 4 new tests |
| C17 | 3 research scripts named `test_*` aborted `pytest` collection before any assertion ran | `conftest.py` excludes them; bare `pytest` now passes |
| C18 | Remote GPU host path and conda path committed | `SLO_TRAIN_DATA` / `SLO_MODEL_OUT` environment variables |
| C3 | `dbLock` reentrancy was load-bearing and undocumented | Contract documented on the member, with the deadlock it would cause |

---

## Open, not blocking the beta

- **`size_t`→`int` narrowing** on the resample buffer, `SampleManagerEngine.cpp:6022-6023`. Upsampling a long field recording wraps negative and walks before the buffer. Real, but needs a >2.1e9-sample fixture to demonstrate.
- **WAV header validation decodes the whole file** into a `std::vector<float>` and throws it away, then decodes again, `:5937`. Large per-file allocation churn on the scan thread; `channels` is unvalidated.
- **WAV metadata rewritten in place** with TagLib, no backup, `:6415-6458`. `AbletonXmpWriter.cpp:104-112` does back up; this path does not.
- **XMP sidecar truncated in place**, `AbletonXmpWriter.cpp:157`, and the backup is overwritten on the next write.
- **`PrecisionBrowser.cpp:675` comparator inversion** breaks the irreflexivity `std::sort` requires, so descending order is undefined behaviour.
- **`getSamples()` deep-copies all embeddings** on every version bump; `runInferenceBatch` bumps per batch.
- **`getSampleBpm` is a linear scan** under `dbLock` on every audition click; `pathToIndex` already exists.
- **`clearCache()` bulk DELETE** on the message thread inside a modal.
- **Silent `continue` skips** in the benchmark scripts shrink the evaluation denominator with no counter.
- **`run_research_v3.py:675-681`** records an unmapped factorized prediction as `class_to_idx[0]`, biasing the "Factorized 81.8%" figure.
- **`MlOverrideGate.h:25-34`** has two comment blocks spliced mid-sentence, naming constants that do not exist.
- **`docs/INDEX.md` lists the rest** with a status for each report.
