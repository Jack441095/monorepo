# SLO Beta Execution Status — 2026-09-15

This is the live evidence companion to `SLO_BETA_EXECUTION_MASTER_PLAN_V1.md`.
It records what was actually verified in the current working tree; it is not a
release receipt and does not make the dirty tree distributable.

## Decision

**Engineering validation is progressing; external beta remains NO-GO.**

The current build has broad local test coverage and two newly closed
file-safety gaps. Distribution is still blocked by source consolidation,
immutable Release-candidate qualification, Developer ID signing/notarisation,
production licensing, clean-Mac installation, and Ableton host acceptance.

## Changes completed

### Qualification harness is read-only

- CLI qualification scan no longer invokes `reorganizeSamples()`.
- The write-capable integration journey copies `test_kick.wav` into a unique
  temporary directory before XMP and TagLib assertions.
- Temporary audio and sidecars are removed when the test ends.
- Verification: the checked-in fixture SHA-256 remained
  `71b1dbbcc8a2a1e9989527df30f8620de2525da0d18ec62ea1ac7f63f2af5a51`
  before and after the integration test.
- Verification: CLI scan of a disposable directory left the audio hash
  unchanged and left exactly one directory entry—the original copied WAV.

### Disconnected external drives no longer look deleted

- Missing records under an absent macOS `/Volumes/<name>` root are preserved.
- Cold-start cache hydration also restores those unavailable-volume records,
  including their embedding, DSP evidence, taxonomy, and map coordinates,
  without raw audio reads or model inference.
- Missing local files, and missing descendants of a currently mounted volume,
  remain eligible for manual pruning.
- The Remove Missing Files dialog reports how many records were preserved
  because external storage is unavailable.
- Regression coverage proves disconnected, local-missing, mounted-volume,
  cold-restart hydration, ordinary prune, second-prune no-op, disk
  non-mutation, and post-prune HNSW consistency behavior.

### Audio-feature qualification is deterministic

- Quick-win fixtures now use a unique disposable root with a stable neutral
  parent folder, so stale files and random UUID tokens cannot contaminate
  filename/folder classification.
- Synthetic click/noise buffers are fully initialized and random noise uses
  fixed seeds.
- The unaccented 120 BPM click fixture now accepts the acoustically equivalent
  60 BPM interpretation, matching the programme's explicit octave-aware tempo
  metric instead of asserting a downbeat the waveform does not contain.
- `TestAudioFeatures` passed 10 consecutive post-fix runs before the final
  complete sweep.
- A proposed 180 ms onset-refractory change improved the synthetic half-time
  case but regressed the existing 104-reference corpus: accepted estimates
  fell from 52 to 47 and MAE worsened from 24.42 to 27.90 BPM. The production
  change was rejected and reverted. Its receipt is retained at
  `_artifacts/slo_tempo_real_fixture_eval_v5_20260915.json` as negative
  evidence (SHA-256
  `06bb30cd49faff519204cc8e8b525c8374e0c7d5095d81eb00f4b8c990abcfb1`);
  acoustic tempo remains review-only.

## Local qualification evidence

- `TestSampleEngine`: pass; disposable metadata round-trip and unchanged source
  fixture.
- Read-only CLI mode: pass; unchanged fixture and no created metadata.
- `TestPruneMissing`: pass after the external-volume policy change.
- Fast regression group: 15/15 pass.
- Cache/resilience/concurrency group: 9/9 pass.
- Similarity intelligence group: 6/6 pass.
- UI/state/RT group: 6/6 pass, with `TestLicensing --url-policy` as its intended
  policy-test invocation.
- Classification/tagging tests: 11/11 pass.
- Additional beta decision, beta sort-gate, and physical-acoustics tests: 3/3
  pass.
- After rebuilding the grouped suites from the final source state, all 47
  compiled `Test*` executables passed in one complete sweep (0 failures).
- Arm64 Standalone build: pass.
- Ad-hoc signature verification: valid on disk and satisfies its designated
  requirement.

These passes are engineering evidence only. They must be rerun from a clean,
immutable Release candidate before distribution.

## Research result

The controlled GPU-0 encoder comparison is complete. On the same 21,793 rows,
seed, five stratified out-of-fold splits, and 90 epochs per fold,
CLAP-music+DSP improved accuracy from 73.86% to 82.20% (+8.34 pp) and macro-F1
from 69.98% to 79.27% (+9.29 pp). Every class improved in this experiment.

This is a strong research signal, not a Beta 1 promotion decision. The split is
not vendor/pack-held-out, the checkpoint is roughly 744 MB, and production C++
parity, latency, memory, packaging, OOD calibration, license review, and blind
evaluation remain open. See `SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md` and
the hash-pinned receipt at
`_artifacts/slo_encoder_quality_detailed_20260915.json`.

## Blocked or pending evidence

- GUI screenshot and interaction acceptance: Mac was locked when the rebuilt
  Standalone app was launched; rerun after manual unlock.
- Full AU and VST3 build/validation for the immutable candidate.
- Clean-machine install/uninstall and Gatekeeper assessment.
- Ableton Live scan, instantiate, preview, drag, save/reopen, and missing-drive
  workflow.
- Production HTTPS activation, offline grace, expiry, revocation, and outage
  drills.
- Dirty-tree inventory and release-lineage separation.
- Apple Developer ID signing and notarisation.
- Internal pilot and external cohort evidence.

## Dirty-tree inventory preflight

The expanded file-level status currently contains 109 tracked modifications
and 709 untracked files. The largest concentrations are:

- `SmartSampleManager/tools`: 35 tracked modifications and 490 untracked files;
  the untracked set alone includes 198 JSON, 183 Python, 49 JSONL, 25 CSV, and
  18 NPZ files, so research code and generated evidence must be separated.
- `SmartSampleManager/Source`: 43 tracked modifications and 18 untracked files;
  this is the primary shipping-code review surface.
- `SmartSampleManager/docs`: 12 tracked modifications and 31 untracked files.
- `_artifacts`: 123 untracked files, including 75 under the strict blind-class
  gate directory.
- `nitedsp`: 15 tracked modifications and 7 untracked files, requiring an
  explicit decision on whether those changes belong to this SLO release.

Nothing was deleted, reset, or moved during this preflight. The inventory
confirms that a clean candidate must be assembled by positive inclusion and
review, never by bulk-cleaning this working tree.

## Next execution order

1. Keep the encoder change outside Beta 1; next research is a duplicate-safe,
   vendor/pack-grouped blind evaluation followed by deployment-cost gates.
2. Inventory the dirty tree into shipping, test, evidence, generated, research,
   and unrelated buckets without discarding existing work.
3. Create a reviewable beta lineage and reproduce the build from a clean
   worktree.
4. Run full format, package, clean-Mac, licensing, and Ableton acceptance on the
   exact candidate.
5. Conduct the 2–3 person internal pilot before inviting external testers.
