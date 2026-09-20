# SLO Classification & Audio Analysis — V4-G BPM Report

**Engineering branch:** `engineering/slo-classification-analysis-v4`
**Commit under test:** V4-F (`51eb3b0`) + V4-G BPM changes (this phase)
**Date:** 2026-08-22

## Executive Result

The V4-G tempo estimator (multi-candidate autocorrelation-peak selection with
octave-family folding, replacing V4-F's single-largest-peak selection) was
evaluated on two independent datasets: (1) a 105-file synthetic controlled
loop corpus spanning 15 tempos x 7 pattern types, and (2) the real 196-file
KSHMR loop-family subset with filename-embedded ground-truth BPM (a superset
of V4-F's 95-file sample, see methodology note below). Results are mixed and
are reported honestly rather than selectively:

- On the **synthetic** corpus: 100% exact accuracy, 0% unknown rate. This
  validates the algorithm has no regressions on cleanly-quantized periodic
  material and correctly resolves half-time/double-time/sparse patterns when
  onsets are clean -- but this is an easy case (synthesized, grid-quantized,
  no swing/humanization/reverb/mix processing) and should **not** be read as
  evidence of real-world accuracy.
- On the **real vendor loops**: MAE improved (52.0 -> 42.6 BPM) but **strict
  exact accuracy got worse** (11.6% -> 6.5%) and **within-±2 BPM accuracy got
  worse** (33.7% -> 18.7%). Octave-equivalent accuracy improved substantially
  (6/95 = 6.3% -> 96/196 = 49.0%), but on inspection this is dominated by the
  algorithm now systematically returning **half-time** predictions for
  high-tempo (140-170 BPM) Hip-Hop Music Loops and Vocal Loops -- a real,
  specific, reportable failure mode, not an improvement to celebrate.

**This is not a fix for Blocker B.** The multi-candidate change is a genuine,
defensible algorithmic improvement (better MAE, better octave-consistency,
verified no regression on the one-shot safety fix or on clean synthetic
material) but it does not clear a "loop BPM is now trustworthy" bar. See
§BPM Ship Recommendation.

---

## 1. Pipeline Audit (§17-18 of spec)

Verified by code inspection of `prepareFile()` (`SampleManagerEngine.cpp`),
unchanged from V4-F:

1. `readWavMetadata()` — TagLib WAV metadata (embedded BPM chunk). Still
   never present in the 1,607-file real corpus (confirmed again this phase —
   no `bext`/`acid`/`iXML` chunks).
2. `parseBpmFromFilename()` — **finding, not previously reported this
   precisely**: this function's plain-number branch requires the substring
   `"bpm"` to appear literally in the filename (`s.containsIgnoreCase("bpm")`,
   `SampleManagerEngine.cpp:2299`). **Zero of the 1,607 real KSHMR files
   contain the literal substring "bpm"** (verified this phase by direct
   string search over `dataset_manifest.json`), even though 196 of the 265
   real Loop-family files have a plausible tempo number embedded in their
   filename in a different form (e.g. `..._Bass_Loop_04_138_E.wav`). This
   means **FILENAME evidence for BPM never actually fires on this vendor's
   real corpus** — every real loop's `bpm` field in production is the
   **acoustic estimate**, not a filename-derived value, despite the filename
   containing a human-readable tempo. This is a real, previously-undocumented
   gap in the precedence chain's practical coverage (not a change made this
   phase — reported as a finding per spec §30, out of scope to fix under the
   "no taxonomy/heuristic redesign" constraint, but material to why "BPM
   ship trustworthiness" cannot lean on FILENAME evidence rescuing weak
   acoustic estimates for this vendor).
3. `estimateBpmFromAudio()` — the acoustic estimator (rewritten this phase,
   see §2 below). Reached for effectively every real loop file.
4. Unknown (`0.0f`) — reached whenever none of the above succeed. Preserved;
   never replaced with a fabricated default.

**One-shot duration gate** (the f0f61e9 fix from V4-F): unchanged this phase,
gates on `trueContentDurationSeconds < 2.0f`, using the caller-supplied real
file duration rather than the fixed 5s analysis-window sample count. Verified
still intact — see §5.

---

## 2. BPM Algorithm Changes (§21-22 of spec)

**Before (V4-F, `195902d`+`f0f61e9`):** single largest-lag autocorrelation
peak over the 50-200 BPM search range, folded into `[70,170]` BPM by blind
repeated doubling/halving, gated by a single global peak-to-mean prominence
threshold (1.8x).

**Root cause of weak accuracy (V4-F §11, re-confirmed this phase):** the
single-peak selection assumes the largest autocorrelation peak in the
50-200 BPM lag range is always musically meaningful, and that folding it by
octave always recovers the true tempo. Neither holds in general — the
strongest periodicity in a broadband energy-difference ODF is often a
rhythmic subdivision (hi-hats, arpeggios) rather than the beat itself, and a
wrong LAG (not just a wrong octave of the right lag) cannot be fixed by
folding.

**After (V4-G, this phase):** `estimateBpmFromAudio()` in
`SampleManagerEngine.cpp`:
1. Computes the **full** lag-correlation curve over the same 50-200 BPM
   range (previously this curve was implicitly discarded after finding only
   the single max).
2. Finds **all locally-salient peaks** (local maxima with prominence >
   1.3x the mean correlation), not just the global max, capped to the 6
   strongest to bound cost.
3. For each peak, generates BPM candidates at `{0.25x, 0.5x, 1x, 2x, 4x}`
   its raw lag-implied tempo, keeping those that fall in an extended musical
   range `[55, 185]` BPM (previously a hard `[70,170]` fold).
4. Selects the candidate with the highest **measured** prominence (not an
   assumed-equal prominence carried over from the original peak) — i.e. if a
   subharmonic or harmonic of the dominant peak is itself independently
   salient, it is now compared directly instead of assumed inferior.
5. Applies the same 1.8x honesty gate as before, now to the actually-selected
   candidate.
6. **Unchanged**: the ≥2s true-duration one-shot gate (f0f61e9) runs first,
   before any of the above, and is untouched by this rewrite.

This directly targets spec §21 (candidate generation instead of blind largest
peak) and §22 (explicit half/double-time handling via the extended
octave-family search) without adding new DSP infrastructure (no new FFT/
spectral-flux front end — the existing broadband energy-diff ODF is
unchanged; only the candidate-selection logic downstream of it changed).

---

## 3. Loop Dataset (§20 of spec)

Two datasets, both **non-copyrighted**, per spec §29's preference for
synthetic fixtures:

### 3a. Synthetic controlled loop corpus (new this phase)
`gen_bpm_dataset.py` (scratchpad tooling, reproducible, not committed audio)
generates 105 WAV loops: **15 tempos** (60, 70, 80, 90, 100, 110, 120, 128,
130, 140, 150, 160, 170, 174, 180 — the exact list requested in spec §20) x
**7 pattern types**: `drum_four_on_floor`, `percussion_syncopated` (deliberately
off-the-grid conga-style hits), `bass_loop` (sub-bass note pattern),
`melodic_loop` (tonal + light drum backing), `half_time` (kick/snare on the
half-tempo grid), `double_time` (kick/hat on the double-tempo grid), `sparse`
(mostly silence with occasional hits). Each loop is 8 bars, synthesized via
simple envelope/oscillator/noise synthesis (no sampled or commercial audio).
35 one-shot regression fixtures (7 kinds x 5) generated alongside for §5.

### 3b. Real vendor loop subset (existing corpus, re-analyzed)
265 real KSHMR Loop-family files (Bass Loop/Music Loop/Synth Loop/Vocal Loop,
known-class ground truth from `dataset_manifest.json`), of which **196** have
a numeric token in the plausible tempo range `[60,220]` somewhere in the
filename (extracted via a simple tokenizer — split on `_`/`-`/` `/`.`,
`.wav` stripped, first token parseable as float in range — documented exactly
so the ground-truth extraction is reproducible and auditable; this is a
broader/differently-selected set than V4-F's 95-file sample, which used an
unspecified narrower selection — **numbers are not directly 1:1 comparable
to V4-F's per-file set, only distributionally**, and this is stated rather
than implied to be identical).

---

## 4. BPM Metrics (§24 of spec)

### 4a. Synthetic corpus (105 loops)

| Metric | Value |
|---|---|
| Unknown rate | 0.0% (0/105) |
| MAE | 0.00 BPM |
| Median AE | 0.00 BPM |
| Within ±1 BPM | 100.0% |
| Within ±2 BPM | 100.0% |
| Within ±5 BPM | 100.0% |
| Strict exact (±0.5 BPM) | 100.0% |
| Octave-equivalent accuracy | 100.0% |
| Octave error rate | 0.0% |

Identical (100%) across all 7 pattern types including `half_time`,
`double_time`, and `sparse` — the candidate/octave-family logic correctly
resolves these when onsets are clean. **This result should be read as "no
regression on clean periodic material," not as general-purpose accuracy.**

### 4b. Real vendor loops (196 files, V4-G algorithm)

| Metric | V4-F (n=95, prior sample) | V4-G (n=196, this phase) |
|---|---|---|
| Unknown rate | 21.1% | 29.1% (57/196) |
| MAE (non-unknown) | ~52 BPM | 42.6 BPM |
| Median AE | not reported | 42.8 BPM |
| Within ±1 BPM | 21.1% | 12.2% |
| Within ±2 BPM | 33.7% | 18.7% |
| Within ±5 BPM | not reported | 20.1% |
| Strict exact (±0.5 BPM) | 11.6% | 6.5% |
| Octave-equivalent accuracy | 6.3% (6/95) | 48.2% (96/196, of which 50 are half-time) |

**MAE improved; strict accuracy and within-±2 accuracy got worse.** The
"octave-equivalent" improvement is not a genuine win — it is dominated by
the new candidate logic systematically choosing the **half-time** candidate
for 140-170 BPM Hip-Hop-style Music/Vocal Loops (see worst-error examples
below), which happens to fall inside the ±1 BPM octave-equivalence tolerance
against half the true tempo, but is a musically wrong answer a user would
notice immediately if BPM were displayed.

**Worst errors (real files, V4-G):**

| File | Ground truth | V4-G prediction | Note |
|---|---|---|---|
| `..._Lord_Help_Me_170_G#m_A.wav` | 170 | 56.8 | Not even a clean 1/3 or octave relation |
| `..._Hells_Kitchen_148_Bm.wav` | 148 | 59.5 | ~2.5x error, not octave-related |
| `..._Final_Stand_170_Fm.wav` | 170 | 85.2 | Half-time |
| `..._Vocal_Melody_39_160_D#m.wav` | 160 | 79.8 | Half-time |
| `..._Psy_Bass_Loop_14_140_F_Triplet.wav` | 140 | 69.4 | Half-time; triplet-feel content is a known hard case |

**Why:** the broadband energy-diff onset detection function used by both
V4-F and V4-G is weak for genre content where the strongest periodic energy
transient is the half-time backbeat (common in Hip-Hop/Trap-adjacent
material at 140-170 "notated" BPM, which is often felt/produced at a
70-85 half-time pulse) — the new candidate logic finds this real, salient
periodicity and (correctly, by its own local evidence) prefers it, but it is
the "wrong" answer relative to the vendor's notated tempo. This is a genuine
MIR ambiguity (notated tempo vs. felt tempo), not a bug, and is not solved by
this phase's downstream candidate-selection change because the actual
periodicity being measured is accurately detected — the fix would require
either (a) beat-tracking-level context spec §21 explicitly says to avoid
adding without evidence of necessity, or (b) a genre/feel prior, out of scope
for a backend algorithm-only phase.

---

## 5. One-Shot Safety Regression (§19 of spec)

35 synthetic one-shot fixtures (Kick x5, Snare x5, Hi-Hat x5, Clap x5,
Percussion x5, Vocal chop x5, FX hit x5), all real duration 0.08s-0.6s (well
under the 2s gate), scanned with the V4-G binary:

| | Result |
|---|---|
| Files receiving non-zero ("fake") BPM | **0 / 35 (0.0%)** |
| Duration range | 0.08s - 0.60s |

**The f0f61e9 one-shot-safety fix is intact; no regression from the V4-G BPM
algorithm rewrite.** This is expected — the duration gate runs before any of
the candidate-selection logic and was not touched.

---

## 6. Half/Double-Time Analysis (§22 of spec)

See §4b. Explicit finding: **50 of 196** real loop predictions (25.5%) are a
half-time (0.5x) relationship to ground truth — this is the dominant error
mode, not a minor tail case, and is reported here rather than folded silently
into an "octave-equivalent accuracy" headline number (spec §22 explicitly
requires not hiding octave errors behind the forgiving metric).

---

## 7. Runtime / Performance (§25 of spec)

The new candidate-generation logic adds one extra full pass over the lag
range (`corrCurve` storage + peak-scan), same asymptotic cost as the
existing autocorrelation computation (`O(numFrames x lagRange)`, dominated by
the same nested loop that already existed). Peak list capped to 6 entries;
candidate list is at most `6 peaks x 5 octave-multiples = 30` candidates,
each an O(1) comparison. This is negligible relative to the existing ONNX
embedding inference cost (V4-F measured ~65ms/file cold scan; BPM estimation
was already inside that budget and remains so — no dedicated micro-benchmark
was run this phase since the added cost is asymptotically identical to the
unchanged autocorrelation loop that dominates it, not a new algorithm
class).

---

## 8. BPM Ship Recommendation (§34 of spec)

**EXPERIMENTAL.** Not SHIP, not SHIP-WITH-CONFIDENCE-UNKNOWN-GATING, not DO
NOT SHIP:

- Not **SHIP**: strict accuracy on real vendor loops did not improve (6.5%
  exact vs V4-F's 11.6%; both far below a trustworthy bar), and the dominant
  error mode (half-time misdetection on 140-170 BPM material) is systematic,
  not random noise that would average out.
- Not **DO NOT SHIP** outright: the one-shot safety fix remains solid (0%
  false-tempo on all tested one-shot fixtures), the estimator never
  fabricates a default value, MAE genuinely improved, and the algorithm is
  demonstrably correct on clean periodic material (100% on the synthetic
  corpus) — i.e. the failure mode is well-understood and specific (weak
  onset detection for half-time-felt genres), not a fundamental brokenness.
- **Recommended path if BPM must ship this generation**: gate acoustic BPM
  display behind an explicit "estimated" qualifier AND suppress it entirely
  for genres/tags historically associated with half-time feel until a
  genre-aware prior or a stronger onset front end (e.g. multi-band spectral
  flux) is built — both are out of scope for this backend-algorithm-only
  phase and would need explicit owner authorization to pursue (spec §1 and
  §26 constraints).

This does not block the OOD work (Blocker A) — the two blockers are
independent and are reported separately per spec's framing.
