# SLO Beta 1 Candidate Assembly Receipt — Main Lineage (`dc855be`)

**Date:** 2026-09-17  
**Executed by:** Antigravity (Lead Audio DSP & ML Systems Engineer)  
**Target Candidate Worktree:** `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/workspace/worktrees/slo/beta-1-main`  
**Candidate Commit:** `dc855bee2e7f0cb8e66973df28c229f9542ec480` (`main`)  
**Status:** Clean worktree, 0 dirty files.

---

## 1. Candidate Identity & Provenance

| Item | Value | Verification Source |
|---|---|---|
| Git HEAD (candidate) | `dc855bee2e7f0cb8e66973df28c229f9542ec480` | `git rev-parse HEAD` in `beta-1-main` |
| Embedding Model ONNX | `panns_cnn10_embedding.onnx` (84,379 B) | SHA-256: `cbc3653cf2ef3cc35f6be48c4863b6d735b0ff85af3b3e9607706a0f467ffad2` |
| Embedding Model Data | `panns_cnn10_embedding.onnx.data` (24,248,320 B) | SHA-256: `8e2b47834248ba6ba0e0993bedcac8babd01666e82a5faf77aaeaca69fa086a8` |
| Classifier Head | `AcousticClassifierWeights.h` | `modelVersion = 6` |
| Classifier Centroids | `AcousticClassifierCentroids.h` | 16 centroids, thresholds `0.7062` to `0.8500` (calibrated training export v6) |
| Taxonomy Version | `AbletonTaxonomy.h` | `kTaxonomyVersion = 5` |
| P0 Tensor Validator Fix | `SampleManagerEngine.cpp` | `hasExpectedEmbeddingOutput()` & `hasSafeEmbeddingBuffer()` validate `pannsDim = 512` |
| QA-15 Gate Assertion | `TestAcousticClassifierParity.cpp` | Enforced in suite: requires ≥ 80.0% acceptance on known references |

---

## 2. Test Suite Qualification (49 Binaries)

Full sweep executed in Release qualification build (`_build/ssm-qualification`):
**TOTAL: 49 passed, 0 failed.**

- `TestAcousticClassifierInputSafety`: PASS
- `TestAcousticClassifierParity`: PASS (Max Logit Error: 3.81e-5, Max Prob Error: 8.58e-6)
- `TestAcousticClassifierParity` QA-15: **46/50 (92.0% accepted, required ≥ 80.0%)**
- `TestAudioEvidence`: PASS
- `TestAudioFeatures`: PASS
- `TestAudioSimilarity`: PASS
- `TestAutoTagging`: PASS
- `TestBassTimbre`: PASS (808 vs Reese separability verified)
- `TestBetaDecisionPolicy`: PASS
- `TestBetaSortGate`: PASS
- `TestCacheIntegrity`: PASS
- `TestCacheVersionEnforcement`: PASS (selective invalidation & user favorites preserved)
- `TestCachedReclassification`: PASS
- `TestClassificationPresentation`: PASS
- `TestCorrectionLog`: PASS
- `TestDuplicateDetection`: PASS
- `TestEmbeddingQuality`: PASS
- `TestFavorites`: PASS
- `TestFindSimilar`: PASS
- `TestFindSimilarWeighted`: PASS
- `TestFormatAwareScan`: PASS
- `TestHiHatType`: PASS (Open vs Closed separability verified)
- `TestHistory`: PASS
- `TestInferenceBatchFlush`: PASS
- `TestKickLength`: PASS (Long vs Short kick verified)
- `TestLabelFreeEvidencePacket`: PASS
- `TestLicensing (--url-policy)`: PASS (Offline security URL policy verified)
- `TestMalformedAudio`: PASS
- `TestMapClusters`: PASS
- `TestMultiInstance`: PASS
- `TestNearDuplicates`: PASS
- `TestPathIndexIntegrity`: PASS
- `TestPathTraversal`: PASS
- `TestPersistedCacheHydration`: PASS
- `TestPhysicalAcoustics`: PASS
- `TestPrecisionBrowserSorting`: PASS
- `TestPruneMissing`: PASS
- `TestReadOnlySafetyQualification`: PASS (Read-only scanning safety verified via SHA-256 pre/post hashes)
- `TestReferenceSearch`: PASS
- `TestResilience`: PASS
- `TestRtDeadlineStress`: PASS (0 audio-thread deadline misses, 0 allocations)
- `TestSafetyRegression`: PASS
- `TestSampleEngine`: PASS
- `TestSearchLexicon`: PASS
- `TestSmartCollections`: PASS
- `TestSortLibraryAsync`: PASS
- `TestSortPreviewAndUndo`: PASS
- `TestTaxonomy`: PASS
- `TestTimbreRefinement`: PASS
- `TestXmpWriter`: PASS

---

## 3. Fresh Real Corpus V2 Audio-Only Benchmark Results

Executed via `ClassificationBenchmark scan` on `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/tools/classification_benchmark/fixtures/real_corpus_v2/audio_only` (5,177 samples across 15 real commercial sample vendors):

```
scan entries          : 5177
matched to manifest   : 5177
unmatched filenames   : 0
Unknown (rejected)    : 324/5177 = 6.3%
Known (classified)    : 4853/5177 = 93.7%

AUDIO-ONLY ACCURACY    : 50.94%  (2637/5177)   [Unknown = wrong]
PRECISION WHEN KNOWN   : 54.34%  (2637/4853)

16-class subset        : 4861 files
  accuracy             : 54.25%
  macro-F1             : 0.5440

centroid cosine        : min=-2.0000 p05=0.7576 median=0.9046 max=0.9572
ML evaluated           : 5157/5177
flagged OOD            : 203/5177
```

### Per-Class Recall Table (Audio-Only)

| Class | Recall | Support | Notes |
|---|---|---|---|
| **Vocal Phrase** | **90.5%** | 360/398 | High performance |
| **Vocal Loop** | **77.4%** | 41/53 | **Recovered** (historic 4.5% cross-vendor recall resolved) |
| **Hi-Hat** | **75.5%** | 321/425 | Strong separation |
| **Kick** | **74.6%** | 323/433 | Strong separation |
| **Synth** | **70.0%** | 35/50 | Good performance |
| **Clap** | **65.8%** | 144/219 | Solid |
| **Music Loop** | **64.0%** | 48/75 | Solid |
| **Bass Loop** | **63.0%** | 17/27 | Moderate support |
| **Bass One-Shot** | **60.0%** | 508/846 | Main confusion with Synth (173) |
| **Impact** | **53.9%** | 41/76 | Solid |
| **Riser** | **48.0%** | 12/25 | Moderate support |
| **Snare** | **46.7%** | 225/482 | Confusions with Clap (66) and Hi-Hat (43) |
| **Synth Loop** | **42.9%** | 33/77 | Moderate support |
| **Foley** | **35.4%** | 137/387 | Ambient overlap |
| **Percussion** | **30.9%** | 386/1251 | Largest class; confusions with Hi-Hat (266) & Foley (256) |
| **FX** | **16.2%** | 6/37 | Broad acoustic variance |
| **Atmosphere** | **0.0%** | 0/316 | Not in 16-class acoustic head (expected; mapped to Synth/FX) |

---

## 4. Key Takeaways & Beta Gate Status

1. **Audio-Only Accuracy Gate QA-2**: Target was ≥ 45.0%. **Achieved: 50.94% (54.25% on 16-class subset, Macro-F1 0.5440). PASS.**
2. **Vocal Loop Recovery (B-008)**: Recovered from 4.5% to **77.4%**. Suppression of claim can be lifted for Beta 1.
3. **Subtype Preservation (QA-6)**: 808 vs Reese bass, open vs closed hi-hat, long vs short kick all 100% passing.
4. **Safety & Realtime (B-010, B-011, B-013)**: 0 audio-thread deadline misses, 0 allocations, bit-identical pre/post file integrity on read-only scanning.
5. **Open Blockers Remaining**: B-001 (Apple signing/notarization), B-002 (Clean Mac Gatekeeper), B-003 (Production HTTPS licensing server), B-004 (Live Ableton matrix). All four require owner interaction/credentials.

