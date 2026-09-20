# SLO Classification — Vocal Loop / Vocal Phrase Filename-Evidence Fix

Phase B-E forensics and fix record for the V4-H-diagnosed Vocal Loop <->
Vocal Phrase filename-evidence defect (V4 Final Engineering Closeout spec).
Scope: this fix ONLY. Does not touch the frozen V4-H ML/OOD architecture.

## 1. Reproduction / Forensics (Phase B)

### 1.1 Where the decision actually lives

Two, not one, filename-evidence steps exist in the pipeline:

1. **Category detection** (`SampleManagerEngine::prepareFile`, the
   `matchType` lambda, ~line 2990): tokenizes the filename and parent
   folder, checks a fixed, ordered list of token-buckets, first match wins.
   The `Vocal` bucket (`voc, vocal, vocals, sing, singing, singer, chant,
   vox, adlib, ad-lib, acapella, acap, choir, speech, spoken, phrase`) is
   checked **before** the `Synth` bucket (which includes `lead`) and before
   the generic `Loop` bucket (`loop, loops, stem, stems, ...`). This step
   was already correct: `lead_vocal_loop.wav`, `vocal_lead_loop.wav`, and
   similar filenames already resolved to instrumentType `Vocal`, not
   `Synth` or generic `Loop`, prior to this fix. Verified, not assumed
   (adversarial tests below).

2. **Subcategory decision** (`AbletonTaxonomy::classify`, called once
   `existingInstrumentType == "Vocal"` is already known): looked up a
   `BaseMapping` of `{"Vocals", "Vocal Phrase", "Vocal Loop", 0.7f}` and
   then picked between the two **using `detectLoopVsOneShot()` only** — a
   DSP-only signal (`durationSeconds > 1.5s` AND `decayTimeSeconds /
   durationSeconds > 0.6`). `AbletonTaxonomy.h`'s own doc comment on
   `ClassificationInput::existingInstrumentType` stated explicitly:
   "filename matching is NOT re-done here." **This is the actual defect**:
   once FILENAME evidence has already resolved category to `Vocal`, the
   evidence hierarchy (`EMBEDDED_METADATA > FILENAME > FOLDER > DSP`, per
   V4-H's report) means ML is never consulted to override it, and the
   *subcategory* choice within "Vocal" was made by a DSP proxy that
   silently discards whatever the filename itself says about loop-ness.

### 1.2 Per-sample diagnostic table (real corpus)

Built from `SmartSampleManager/tools/classification_benchmark/dataset_manifest.json`
(the 1,607-file real-vendor corpus used by V4-F/G/H) and direct `afinfo`
duration checks against `fixtures/scan_subset/`. Full Vocal-family
population: 153 (53 Vocal Loop, 100 Vocal Phrase ground truth).

| Ground truth | n | Filename contains literal "loop" word | Filename contains literal "phrase"/"chop"/"oneshot" word | Filename has adjacent BPM+musical-key suffix (e.g. `..._128_D.wav`) |
|---|---|---|---|---|
| Vocal Loop | 53 | 0 (0%) | 0 (0%) | 52 (98%) |
| Vocal Phrase | 100 | 0 (0%) | 0 (0%) | 0 (0%) |

Representative filenames:
- Vocal Loop: `0760_KSHMR_Vocal_Energy_Booster_01_Ahh_128_D.wav`,
  `0767_KSHMR_Vocal_Melody_01_88_C#m.wav`, `0806_KSHMR_Whistle_01_Fm.wav`
  (the one Vocal Loop sample with *no* BPM+key adjacency — its filename has
  only a bare index number `01`, not a tempo, next to the key `Fm`).
- Vocal Phrase: `0813_KSHMR_Numbers_123_Cmon_115.wav`,
  `0819_KSHMR_Numbers_321_Deep_Voice.wav`.

**Key forensics finding, and a correction to the naive assumption**: the
real vendor corpus filenames used for V4-F/G/H qualification essentially
never spell out the words "loop" or "phrase" at all. The actual,
near-perfectly-separating (52/53 = 98%, 0/100 false-positive) filename
signal distinguishing the two classes in this corpus is a **BPM+musical-key
filename suffix** — an industry-standard sample-library naming convention
for a tempo/pitch-locked musical loop (Splice, Loopmasters, and most
commercial packs use it), as opposed to a one-shot/spoken phrase, which
carries no musical key because it isn't tempo-synced content. Duration
alone does not separate the classes (`0813_..._Cmon_115.wav` is 2.09s,
`0819_..._Deep_Voice.wav` is 1.65s — both exceed the 1.5s "longEnough"
threshold that `detectLoopVsOneShot()` uses, same as several genuine Vocal
Loop samples), which is consistent with V4-H's finding that this is a
taxonomy/heuristic-ambiguity root cause (bucket G), not a DSP-signal-only
problem, and consistent with V4-H's report language that "both classes
contain the token 'Vocal'" (i.e., the *category*-level FILENAME evidence
is what locks in before ML/DSP ever run — see §1.1).

### 1.3 Root cause, stated precisely

> Once `existingInstrumentType == "Vocal"` and `winningEvidence ==
> FILENAME` (or `FOLDER`/`EMBEDDED_METADATA`), the Vocal Loop-vs-Phrase
> *subcategory* was decided exclusively by a DSP-only duration/decay proxy
> that never consulted any of: the literal words "loop"/"phrase" in the
> filename, or (the dominant real-corpus signal) a BPM+musical-key filename
> suffix — despite both being reliable, already-partially-parsed evidence
> elsewhere in the same file (`parseBpmFromFilename`/`parseKeyFromFilename`
> exist but use a different, stricter parsing rule not applicable here —
> see §3).

This matches V4-H's own §"Vocal Loop Root Cause" classification: cause
**G (taxonomy/heuristic ambiguity) via evidence-hierarchy precedence**, not
A-D (OOD threshold/geometry), confirmed independently by real DSP-signal
forensics above (duration doesn't separate the classes; the ML gate is
never reached for these samples because FILENAME evidence already won).

## 2. Proposed Rule (Phase C)

**CURRENT**: `AbletonTaxonomy::classify()` decides Vocal Loop vs Vocal
Phrase using `detectLoopVsOneShot(durationSeconds, decayTimeSeconds)` only,
regardless of any filename/folder evidence.

**FAILURE**: A real vocal-loop sample whose DSP envelope isn't cleanly
"sustained" by the crude decay/duration>0.6 proxy (vocal content has
per-word onset/decay envelopes, not a synth-pad-like sustain) gets
defaulted to the one-shot label (`Vocal Phrase`) even when the filename
carries strong, unambiguous evidence it's a loop.

**PROPOSED RULE**: domain-specific multi-token filename/folder evidence for
loop-vs-one-shot, scoped to `existingInstrumentType == "Vocal"` only, beats
the generic DSP-only heuristic when unambiguous:
- Loop evidence: literal word token `loop`/`loops`, OR an adjacent
  BPM-number (40-220) + musical-key-token pair anywhere in the filename
  (either order).
- One-shot evidence: literal word token `phrase`/`phrases`/`chop`/`chops`/
  `oneshot`.
- If both sides have evidence, or neither does, fall through unchanged to
  the existing DSP-only `detectLoopVsOneShot()` path — ambiguity is
  reported honestly, not resolved by guessing.

**EXPECTED EFFECT**: recovers the 52/53 (98%) of real-corpus Vocal Loop
ground truth that carries the BPM+key signal, without affecting any of the
100 Vocal Phrase ground-truth samples (0/100 false-positive on the
adjacency check) or any non-Vocal instrumentType.

**REGRESSION RISK**: Assessed and mitigated as follows.
- *Scope leakage into other classes*: mitigated by gating the entire rule
  on `existingInstrumentType == "Vocal"` — Kick/Snare/Bass/Synth/etc.
  subcategory decisions are provably untouched (adversarial tests below;
  the override block is unreachable for any other instrumentType).
- *False positives from generic tokens*: mitigated by using only
  `loop`/`phrase`/`chop`/`oneshot` word tokens (domain-specific once
  category is already Vocal) and a narrow numeric-range + real-key-token
  adjacency check, not any bare number or generic word.
- *Ambiguous filenames* (e.g. a hypothetical `vocal_phrase_loop.wav`, or a
  BPM+key suffix co-occurring with an explicit "phrase" word): both-sided
  evidence is treated as ambiguous and deliberately falls through to the
  unchanged DSP path, matching pre-fix behavior exactly for that specific
  input rather than guessing.
- *Cache correctness*: `AbletonTaxonomy::kTaxonomyVersion` bumped 1 -> 2 so
  every previously-cached row is selectively reclassified (taxonomy only,
  not embedding/DSP features) on next scan via the existing
  `lightReanalyzeFile` path — both call sites updated identically.
- *ML/OOD architecture*: entirely untouched — this fix only changes what
  `AbletonTaxonomy::classify()` produces as the FILENAME/FOLDER/
  EMBEDDED_METADATA-evidence-tier answer; the evidence hierarchy itself
  (which decides whether ML ever gets a chance to override it) and the ML
  classifier/OOD gate are not modified.

## 3. Why not reuse `parseBpmFromFilename`/`parseKeyFromFilename` directly

`parseBpmFromFilename()` requires the literal substring `"bpm"` to appear
in the filename (or a token ending in `"bpm"`) before it will accept a bare
number as tempo — by design, since a bare number in a sample filename is
usually NOT a tempo (it is far more often a pack index, like the `01` in
`KSHMR_Vocal_Melody_01_88_C#m.wav`). That existing function is correct for
its own purpose (populating `SampleItem::bpm`) and was deliberately left
unmodified. The new BPM+key-adjacency check added here is a different,
narrower signal — "a number in the plausible tempo range immediately next
to a real musical-key token" — used only as loop-vs-one-shot evidence, not
as a tempo value, and is implemented as its own pure function
(`hasAdjacentTempoKeyPair`) in `AbletonTaxonomy.cpp` rather than by
loosening `parseBpmFromFilename()`'s semantics (which other call sites
depend on staying strict).

## 4. Implementation (Phase E)

- `SmartSampleManager/Source/AbletonTaxonomy.h`: `FilenameSubcategoryEvidence`
  struct (`hasLoopToken`, `hasOneShotToken`, `hasTempoKeySuffix`),
  `detectFilenameSubcategoryEvidence()` pure function declaration,
  `ClassificationInput::filenameEvidence` field, `kTaxonomyVersion` 1 -> 2.
- `SmartSampleManager/Source/AbletonTaxonomy.cpp`: `detectFilenameSubcategoryEvidence()`
  implementation (`containsAnyOf`, `isMusicalKeyToken`, `isPlausibleBpmToken`,
  `hasAdjacentTempoKeyPair` helpers), and the Vocal-scoped override block in
  `classify()` inserted immediately before the existing
  `detectLoopVsOneShot()` call, falling through unchanged when evidence is
  ambiguous or absent.
- `SmartSampleManager/Source/SampleManagerEngine.cpp`: `rawUnderscoreSplitLowercase()`
  helper (digit-preserving `"_ -"` split, mirroring
  `parseKeyFromFilename`/`parseBpmFromFilename`'s own tokenization); both
  `prepareFile()` and `lightReanalyzeFile()` now compute filename/folder
  word tokens (via the pre-existing `tokenizeString`) and raw segments, and
  pass them into `taxInput.filenameEvidence`. Computed unconditionally
  (not only inside the `instrumentType == "Unknown"` branch), since the
  loop/phrase filename signal is independent of how category was decided
  (FILENAME, FOLDER, or EMBEDDED_METADATA).
- No ML/OOD/embedding/centroid/ONNX code touched. No acoustic BPM code
  touched (the new BPM-adjacency check is a filename-string heuristic
  entirely separate from `estimateBpmFromAudio`/the acoustic tempo
  estimator).

## 5. Adversarial Test Set (Phase D)

Added to `SmartSampleManager/Source/test_taxonomy_main.cpp`, exercising the
actual production `detectFilenameSubcategoryEvidence()` + `classify()`
functions (not a re-implementation). Positive, negative, ambiguous, and
non-Vocal-scope-leakage cases, per spec §Phase D's filename list, plus
real-corpus-representative BPM+key cases:

- Positive (-> Vocal Loop): `vocal_loop_01.wav`, `vox_loop_174.wav`,
  `female_vocal_loop.wav`, `acapella_loop.wav`, `choir_loop.wav`,
  `lead_vocal_loop.wav`, `vocal_lead_loop.wav`, plus real-corpus
  `KSHMR_Vocal_Energy_Booster_..._128_D` / `KSHMR_Vocal_Melody_..._88_C#m`
  patterns (BPM+key suffix, no "loop" word at all).
- Negative (-> Vocal Phrase, must NOT flip to Loop): `vocal_phrase.wav`
  (given a deliberately loop-shaped DSP signal, to prove filename evidence
  decides), `spoken_phrase.wav`, `vox_phrase.wav`, `vocal_chop.wav`,
  `vocal_one_shot.wav` (proves "one"/"shot" are deliberately NOT treated as
  evidence -- falls through to DSP, unchanged), real-corpus
  `KSHMR_Numbers_..._Cmon_115` pattern (bare number, no key -> no false
  trigger).
- Ambiguous (-> falls through to unchanged DSP path):
  `vocal_phrase_loop.wav` (both word tokens present).
- Scope-leakage checks (fix must NOT affect these): `bass_loop.wav`
  (Bass-scoped, DSP-only preserved), `drum_loop.wav`/`fx_loop.wav`
  (resolve to the separate generic-`Loop`-bucket branch, untouched),
  `synth_lead.wav`/`lead_synth.wav` (Synth, never reaches Vocal branch),
  a Synth-instrumentType sample with a BPM+key-suffixed filename (BPM+key
  evidence must not leak outside Vocal).
- BPM-adjacency edge cases: bare index number with no key neighbor (must
  not fire), BPM number with no key neighbor at all (must not fire),
  key-then-BPM order (must fire, same as BPM-then-key).

Result: **all tests pass** (`build-test/TestTaxonomy`, pure-logic, no
JUCE/ONNX/audio-decode dependency, exit code 0).

## 6. Real-corpus impact estimate (pre-build-and-scan simulation)

Independent Python re-implementation of the exact tokenization/adjacency
rules (not the production C++, but a faithful mirror of it), run directly
against the full 1,607-entry `dataset_manifest.json`:

| | Count |
|---|---|
| Vocal-family ground truth (Vocal Loop + Vocal Phrase) | 153 |
| Rule fires with unambiguous evidence | 52 |
| ...of which correct | 52 (100%) |
| ...of which wrong (would need investigation before shipping) | 0 |
| Ambiguous (both signals present) | 0 |
| No evidence at all (unchanged DSP-fallback behavior) | 101 |

This is a simulation for forensics/design purposes, not a substitute for
the real end-to-end C++ rescan (Phase F, in the closeout report) — but it
strongly indicates the fix should recover the majority of real Vocal Loop
ground truth without introducing new Vocal Phrase errors, once the actual
rescan is run against the rebuilt binary. See
`SLO_CLASSIFICATION_V4_FINAL_CLOSEOUT_REPORT.md` for the real, built-binary
measurement.
