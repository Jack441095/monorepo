# SLO Classification — V4 Remediation & Measurement Session

**Date:** 2026-09-09
**Scope:** `products/slo/SmartSampleManager`
**Status:** IN PROGRESS — ablation, C++ integration and CLAP audit complete;
encoder comparison running. See §9 for a correction to §4.4.
**Related:** `SLO_V4_DSP_FEATURE_PARITY_SPEC.md` (canonical feature spec + addenda),
`SLO_CLASSIFICATION_V4_FINAL_CLOSEOUT_REPORT.md` (prior, still DRAFT),
`SLO_CLASSIFICATION_V5_RESEARCH_BASELINE.md`

---

## 1. Starting position

The session opened with V4 Hybrid (520-D) reported as trained, exported to C++
headers, and "parity verified", with a choice of next steps (re-index a library,
run a release build, or start V5 research).

Investigation found that none of those were safe to start, for reasons below.
The headline claim was not wrong so much as narrower than it read: the parity
test validated the matrix arithmetic, not the vector being fed into it.

---

## 2. What was wrong

### 2.1 The parity evidence was partly hollow

`tools/classification_benchmark/verify_cpp_parity.py` prints
`"Evaluating C++ forward pass logic against PyTorch reference targets"` but
never invokes any C++. It re-softmaxes `expected_logits` from the JSON and
compares against `expected_probs` in the same JSON — a self-consistency check
that passes unconditionally.

`test_cpp_parity_standalone.cpp` *is* a real test (it calls
`AcousticClassifier::computeLogits` and diffs against PyTorch), but it feeds
embeddings in from JSON. It therefore validates the head, not the 520-D input
the engine actually constructs.

### 2.2 Train/serve skew in the 8 DSP dims

Only 1 of 8 dimensions matched between `build_hybrid_v4_dataset.py` (training)
and `SampleManagerEngine.cpp` `runInferenceBatch` (production).

| Dim | Python (trained on) | C++ (production) | Match |
|-----|---------------------|------------------|-------|
| 0 | `duration/10` | `durationSeconds/10` | yes |
| 1 | `centroid / (native_sr/2)` | `centroid / 16000` | no — divisor |
| 2 | spectral flatness (geo/arith) | `1 - crestFactor/20` | no — unrelated quantity |
| 3 | ZCR over first 0.5s | ZCR over whole file | no — window |
| 4 | RMS over first 0.5s | RMS over whole file | no — window |
| 5 | `norm_duration` **duplicate of dim 0** | `decayTime/3` | no — trainer bug |
| 6 | energy fraction < 250 Hz | `1 - rolloff/20000` | no — unrelated quantity |
| 7 | energy fraction > 4000 Hz | `rolloff/20000` | no — unrelated quantity |

Dim 5 was a copy-paste bug: the trainer wrote `norm_duration` twice, so the
model never received a decay feature at all.

### 2.3 The V4 result was a regression, not an improvement

Honest cross-validated numbers from the checkpoints as they stood:

- V3 (512-D, pure PANNs): OOF **70.03%**
- V4 Hybrid (520-D, skewed features): OOF **68.31%**

### 2.4 The evaluation protocol was not comparable

V4's fold loop evaluated every epoch and kept the predictions from whichever
epoch scored best *on the validation fold*, then reported that as OOF accuracy.
That is model selection on the evaluation set. V3 trained its full schedule and
evaluated the final model once.

So V4's 68.31% was measured under a *favourable* protocol and still lost to
V3's honest 70.03% — the real gap was wider than it appeared.

### 2.5 A larger skew in the 512 PANNs dims

Training embeddings come from a 10s window (`target_len = 32000*10`);
production feeds 5s (`sampleLen = 160000`). Measured with
`measure_panns_train_serve_skew.py`, cosine similarity of production embedding
to training embedding:

| Cause | Mean cosine | Min |
|-------|-------------|-----|
| Resampler (soxr_hq → C++ linear, no anti-alias) | 0.9995 | 0.9965 |
| Input window (10s → 5s) | 0.9365 | 0.8690 |

The resampler was suspected to matter and **does not** — that concern is closed.
The window does, with a cliff exactly at 5s where production starts discarding
audio. **31.0% of the corpus (6,762 files) is longer than 5s.**

### 2.6 Four C++ integration defects

All caused by appending the 8 DSP dims onto the persisted embedding vector.

| # | Defect | Effect |
|---|--------|--------|
| A | Cache read guard `blobBytes == 512*4`, code writes 520 | Every cached embedding rejected on read; full re-inference each launch |
| B | `hasSafeEmbeddingBuffer` requires `embeddingDim` (520), hydration yields 512 | Cache-hydrated rows silently never classified |
| C | `decayTimeSeconds` never persisted | Fresh row uses real decay, hydrated row falls back to duration — **same file classified differently depending on cache state** |
| D | `isValidEmbedding` loops to 520 over a 512-float buffer | 8-float out-of-bounds read |

C was the most dangerous: silent non-determinism rather than an obvious failure.

---

## 3. What was done

### 3.1 Feature spec realigned to production

`build_hybrid_v4_dataset.py` rewritten to reproduce the C++ path exactly:
whole file at native rate, 2048-point Hann / 512-hop STFT averaged across
frames, and a faithful port of `computeEnvelopeDecayTimeSeconds`. Canonical
spec table lives in `SLO_V4_DSP_FEATURE_PARITY_SPEC.md`.

The first implementation used literal Python loops and ran at ~0.26 files/s.
It was vectorised (`scipy.signal.lfilter` for the IIR envelope,
`sliding_window_view` + batched `rfft` for the STFT, `cumsum`+`argmax` for the
rolloff search) and **validated bit-identical** against the loop transcription
across 15 files spanning mono/stereo, 44.1/48 kHz, 0.04–10.3s:
`validate_dsp_parity.py`, **max error 0.000e+00 on all 8 dims**.

Parallel extraction (`--workers`) added with a `--self-check` mode proving the
parallel path is bit-identical to serial. Full corpus: 21,793 files in 18.7 min.

### 3.2 Protocol fixed and an ablation added

- Fold loop now trains the full schedule and evaluates the final model once,
  matching V3. The old best-epoch-on-val behaviour is documented in-code as
  something not to reintroduce.
- Epochs/LR matched to V3 (90/fold, 130 final, 1.2e-3 folds).
- `--input-dims {512,520}` added with a fixed seed so the two arms differ *only*
  in whether the DSP block is present.

### 3.3 C++ integration refactor

`item.embedding` is once again the **512-D PANNs vector** — persisted, indexed,
similarity-searched, all unchanged. The 520-D classifier input is assembled on
demand by a single new function, `buildAcousticClassifierInput()`, used by both
the fresh-inference and cache-hydration paths so they cannot drift apart.

- `AcousticClassifier::pannsDim` / `dspFeatureDim` added, with a `static_assert`
  tying them to `AcousticWeights::embeddingDim`.
- `isValidEmbedding` bound corrected to `pannsDim`.
- `hasSafeEmbeddingBuffer` checks `pannsDim`.
- Embedding-dimension literals replaced with the named constant at the three
  contract points (cache guard, cache read, ONNX read).
- `decay_time_seconds` column added (ALTER, backward-compatible), bound on
  write, read back on hydration; `kFeatureAnalysisVersion` 3 → 4 so stale rows
  re-analyse.

**Verification:** compiles clean; `test_cpp_parity_standalone` 10/10, max logit
error 3.24e-05; `TestAcousticClassifierParity` all V4-H regression checks pass;
`TestCachedReclassification` passes at 95.8 files/sec.

---

## 4. Results

### 4.1 Ablation — do the 8 DSP features earn their place?

Identical architecture, seed and folds; only the DSP block differs.

| Model | OOF accuracy |
|-------|--------------|
| 520-D hybrid (PANNs + 8 DSP) | **73.51%** |
| 512-D control (PANNs only) | 71.56% |
| V3 baseline (different architecture) | 70.03% |

**Isolated DSP contribution +1.95 pp** (95% CI +1.06 to +2.84), 5/5 folds,
paired t = 6.10, **p = 0.0037**.

Of the +3.48 pp over V3, ~+1.95 pp is the corrected features and ~+1.53 pp is
the architecture. Without the control arm the whole +3.48 would have been
credited to the features. Fixing the spec turned a 1.7 pp regression into a
1.95 pp gain — a ~3.6 pp swing.

Caveat: the 8 dims are only ~6 independent signals. `low_r`/`high_r` correlate
at **−1.0000** (complements by construction) and both correlate with `centroid`
at ±0.9625.

### 4.2 The deployment population — measured for the first time

Training labels come from filename/folder keyword matching
(`classify_relpath_and_name`). Production's evidence hierarchy is
`EMBEDDED_METADATA > FILENAME > FOLDER > DSP` and ML only overrides
`DSP`/`FOLDER`/empty. **The model is trained only on files where the keyword
matcher succeeded, and only consulted on files where it failed.**

Coverage (pack-relative paths, matching how training labels were derived):

| Collection | Labelled | No evidence |
|------------|----------|-------------|
| `sample_pack_testing` | 21,793 (76.9%) | 6,537 (23.1%) |
| `Samples 2021 ->` | 35,042 (83.5%) | 6,806 (16.5%) |
| **Total no-evidence population** | | **13,343** |

Model trained on 80% of the labelled data, then scored on two unseen sets:

| Metric | A: held-out labelled | B: no-evidence (served) |
|--------|----------------------|-------------------------|
| held-out accuracy | 73.89% | **unknown — needs hand labels** |
| max softmax confidence | 0.7857 | 0.7714 |
| centroid cosine (OOD score) | 0.9828 | 0.9634 |
| centroid cosine p5 | 0.9481 | 0.8913 |
| **flagged unknown by OOD gate** | **9.0%** | **30.8%** |

The confidence gap is negligible (0.014) — the model is *as confident* on the
served population as on the trained one. Only the centroid/OOD gate detects the
shift. **That gate is the sole mechanism preventing silent mass mis-tagging and
must not be loosened.**

Predicted class mix diverges sharply:

| Class | A held-out | B served | Ratio |
|-------|-----------|----------|-------|
| Music Loop | 0.3% | 2.8% | 9.3× |
| Bass Loop | 0.4% | 3.3% | 8.3× |
| Synth Loop | 0.6% | 3.5% | 5.8× |
| Hi-Hat | 8.8% | 3.7% | 0.42× |
| Snare | 5.7% | 2.3% | 0.40× |

**Root cause of the 30.8%:** the four rarest training classes (Music Loop 92,
Vocal Loop 102, Bass Loop 117, Synth Loop 138 — under 2% of training data)
constitute ~10% of the served population. Vendor drum one-shots almost always
carry a filename keyword, so ML never sees them; what is left is loop-heavy
user content. This is a training-distribution problem, not a modelling one.

### 4.3 Where the errors actually are

Top 8 confusion pairs account for **46% of all errors**, and `Percussion` is in
five of them:

| Pair | Share of errors |
|------|-----------------|
| Foley ↔ Percussion | 10.8% |
| Hi-Hat ↔ Percussion | 8.7% |
| Bass One-Shot ↔ Synth | 5.4% |
| Kick ↔ Percussion | 5.3% |
| Percussion ↔ Snare | 4.3% |

The labeller makes `Percussion` a semantic catch-all — anything matching
`drum`/`beat`/`perc` lands there, and `"kick loop"` → Percussion while
`"kick"` → Kick. Those are near-identical acoustically. Weakest classes:
Music Loop 16.7% recall / 23.1% precision (18 held-out examples); Impact 48.6%;
FX 53.8%.

Split by whether a fundamental frequency is even defined:

| Error type | Share |
|------------|-------|
| unpitched ↔ unpitched | **60.7%** |
| pitched ↔ unpitched | 28.8% |
| pitched ↔ pitched | 10.5% |

### 4.4 The ceiling is label noise

Regrouping the *existing* predictions (no retraining):

| Taxonomy | Classes | Accuracy | Δ |
|----------|---------|----------|---|
| baseline | 16 | 73.89% | — |
| merge Foley+FX | 15 | 74.74% | +0.85 |
| collapse loop/one-shot split | 12 | 74.72% | +0.83 |
| merge tonal family | 12 | 76.07% | +2.18 |
| **merge drum family** | 12 | **81.05%** | **+7.16** |
| **coarse 4-way** (Drum/Tonal/Texture/Vocal) | 4 | **84.90%** | **+11.01** |

The last row is the important one. Distinguishing a kick from a synth pad from
a vocal should be near-trivial; a competent model should exceed 95%. Reaching
only 84.9% implies **roughly 15% of labels are effectively wrong**.

Corroborating: held-out errors stratified by model confidence —

| Confidence | n | Error rate |
|-----------|---|-----------|
| 0.00–0.50 | 465 | 61.5% |
| 0.50–0.80 | 1424 | 33.1% |
| 0.80–0.95 | 1458 | 15.8% |
| **0.95–1.00** | 1012 | **14.7%** |

The error rate stops falling at high confidence. 149 predictions are >0.95
confident yet disagree with the label (`FX→Synth`, `Foley→Vocal Phrase`,
`Music Loop→Synth`). That is the label-noise signature.

**Consequence: 90% on the current 16-class keyword-labelled task is not
achievable.** No architecture or data volume passes a noise floor. 90% on a
cleaned, merged taxonomy is achievable.

---

## 5. Open items

1. **PANNs window skew unresolved.** Production truncates at 5s, training used
   10s, affecting 31% of files. Options: re-extract training embeddings through
   the production pipeline (~25h, no latency change, recommended), or widen the
   C++ window to 10s (better information, ~2× inference cost). The two pipelines
   must agree; today they do not.
2. **Real-world accuracy is still unmeasured.** Everything above is
   keyword-agreement or confidence. ~250 hand-labelled no-evidence files,
   stratified toward the loop classes, would establish it.
3. **Taxonomy decision.** The drum-family merge is worth +7.16 pp but changes
   what users see. Product call.
4. **Dims 6/7 are redundant** (r = −1.0000). Replacing one with a genuinely
   independent band-energy ratio is likely free headroom.
5. **CLAP zero-shot label audit — running.** 4,359 held-out clips at 48 kHz on
   GPU 1. CLAP never saw this corpus or the filenames, so it is an independent
   opinion. Files where CLAP *and* the supervised model agree with each other
   but both disagree with the keyword label are near-certain mislabels and form
   a relabelling queue.

---

## 6. Ranked next steps

| Lever | Est. gain | Basis | Cost |
|-------|-----------|-------|------|
| Merge drum family | +7.2 pp | measured | product decision |
| Better encoder (CLAP/BEATs, or fine-tune PANNs) | +3–6 pp | CNN10 is 2019, 5M params, frozen | GPU hours |
| Label cleanup (confident-disagreement review) | +3–5 pp | 14.7% err at >0.95 conf | human review, 500–1500 files |
| Harmonic/temporal feature block | +1.5–3 pp | 28.8% of errors are pitched↔unpitched | ~40 min extraction + train |
| Library data (loop/rare classes) | +1–2 pp | rare classes 4–6× | 17h unattended extraction |
| Fix PANNs window skew | unknown | 31% of files | ~25h re-extraction |

Levers 1 and 3 attack the *ceiling*; 2, 4 and 5 attack the *gap to the ceiling*.
Since the ceiling is the binding constraint, the ceiling work has the leverage —
which inverts the intuitive "get a better model" instinct.

### Open-source options surveyed

- **FSD50K** (CC-BY) — 51,197 human-verified clips on the AudioSet ontology,
  including real `Snare drum`/`Bass drum`/`Hi-hat` labels. Directly attacks the
  noise floor and would provide a genuine evaluation set.
- **LAION-CLAP** (Apache-2.0, verify checkpoint terms) — zero-shot from text
  prompts; sidesteps the label problem entirely.
- **BEATs / PaSST / AST / MERT** — stronger encoders than CNN10.
- **basic-pitch** (Spotify, Apache-2.0) — polyphonic transcription (chords).
- **CREPE** (MIT) — monophonic pitch.
- **cleanlab** — confident learning; check licence (believed AGPL).
- **Licensing cautions for a commercial plugin:** Essentia is AGPL-3.0, aubio is
  GPL-3.0, madmom has commercial/patent restrictions. Verify before any ships.

---

## 7. Files

### Added
- `tools/classification_benchmark/validate_dsp_parity.py`
- `tools/classification_benchmark/inspect_hybrid_dataset.py`
- `tools/classification_benchmark/measure_panns_train_serve_skew.py`
- `tools/classification_benchmark/build_no_evidence_evalset.py`
- `tools/classification_benchmark/compare_deployment_distribution.py`
- `tools/classification_benchmark/prep_clap_audio.py`
- `tools/classification_benchmark/clap_zeroshot_audit.py`
- `tools/classification_benchmark/retrain_v4_pipeline.sh`
- `docs/classification/SLO_V4_DSP_FEATURE_PARITY_SPEC.md`
- this document

### Modified
- `tools/classification_benchmark/build_hybrid_v4_dataset.py` — rewritten to the
  C++-matched spec, vectorised, parallelised
- `tools/classification_benchmark/train_gpu_classifier_v4.py` — OOF protocol
  fixed, V3-matched schedule, `--input-dims` ablation
- `Source/AcousticClassifier.h` — `pannsDim`/`dspFeatureDim`, `isValidEmbedding`
  bound corrected
- `Source/SampleManagerEngine.cpp` — `buildAcousticClassifierInput()`, append
  removed, dim literals named, decay persisted
- `Source/SampleManagerEngine.h` — `kFeatureAnalysisVersion` 3 → 4

### Should be deleted or renamed
- `tools/classification_benchmark/verify_cpp_parity.py` — does not test C++
  despite its name and output; passes unconditionally.

---

## 8. Numbers worth not misquoting

- **73.51%** — 520-D hybrid OOF. This is *keyword-agreement*, not real-world
  accuracy. A model scoring 100% here would be a perfect reimplementation of the
  keyword matcher, which production already runs first.
- **+1.95 pp** — the DSP block's isolated contribution, p = 0.0037.
- **30.8%** — OOD-flag rate on the population ML actually serves, vs 9.0% on the
  trained population.
- **~15%** — implied label noise floor, from the 84.9% four-class ceiling.
- Real-world accuracy on the served population: **not yet measured.**

---

## 9. CLAP zero-shot audit — result and correction (2026-09-09, later)

### What was run

4,359 held-out clips converted to 48kHz FLAC (574MB at true length vs ~1.9GB
padded to CLAP's 10s window), scored on GPU 1 against `laion/clap-htsat-unfused`.
The GPU box has no HuggingFace access (`Errno 101 Network is unreachable`), so
the model was shipped from the local HF cache as a flat directory and loaded
offline. API note: transformers 5.x returns `BaseModelOutputWithPooling` from
`get_audio_features`/`get_text_features`; `.pooler_output` is the 512-D joint
projection. Verified by a semantic spot check before the full run (Kick, Snare,
Hi-Hat, Synth, Clap each ranked their own prompt first).

### Result

| Prompt set | Agreement with keyword labels |
|-----------|-------------------------------|
| v1 (production-role wording) | 34.02% |
| v2 (concrete acoustic wording) | 34.14% |

Rewriting the prompts changed nothing, which **rules out prompt quality** as the
explanation.

Per class (v2): Vocal Loop 85.0%, Snare 80.9%, Kick 66.9%, Music Loop 66.7%,
Hi-Hat 63.1%, Synth 61.6% — versus Foley **1.9%**, Bass One-Shot 9.8%,
Vocal Phrase 10.2%, Percussion 11.7%.

### CORRECTION to section 4.4

Section 4.4 described a "~15% label noise floor", implying the labels are
*wrong*. That framing is inaccurate. The labels are not wrong; several class
boundaries **are not acoustic boundaries at all**.

Evidence — where the failing classes actually go:

| Keyword label | CLAP hears | The boundary encodes |
|---------------|-----------|----------------------|
| Foley | Percussion 20%, Kick 18%, Snare 15%, Clap 11% | provenance (recorded object vs sampled drum) |
| Percussion | Snare 27%, Kick 16%, Hi-Hat 11% | the catch-all; contains real snares/kicks/hats |
| Vocal Phrase | Vocal Loop 38%, Vocal Phrase 10% | temporal form (48% correctly vocal, split fails) |
| Bass One-Shot | Kick 38%, Synth 19% | genuine acoustic overlap |

Files labelled Foley include `MGF_PHYS2_PERC_25.wav`, `MGF_PHYS1_PERC_35.wav`,
`Aluminium Can.wav`, `HOUSEHOLD_357.wav`, `Hit 073.wav` — percussive hits on
physical objects, several with `PERC` in the filename. The labeller tests the
Foley branch (`foley|found sound|field|nature|organic`) before the Percussion
branch, so folder evidence overrides the filename. CLAP calling these
Percussion/Kick/Snare is **acoustically correct**.

**Consequence:** no audio model can recover a distinction that is not present in
the audio. This explains the 84.9% four-class ceiling, the prompt rewrite having
no effect, and why 90% on this taxonomy is unreachable in principle rather than
for want of model capacity. It also lowers the expected value of an encoder
upgrade — if the constraint is non-acoustic labels, a better encoder cannot fix
it.

### Three independent lines now agree

1. Merging the drum family measures **+7.16 pp**
2. CLAP independently refuses to separate Foley from Percussion
3. Vocal Phrase/Vocal Loop failure is the temporal axis, which global-pooled
   embeddings discard by construction

### Revised plan

Predict **source** acoustically (where signal exists); derive **temporal form**
(one-shot vs loop) from duration/periodicity/BPM, where DSP beats ML. Fold Foley
into Percussion unless provenance can come from folder/vendor metadata — if that
distinction matters to users it must come from metadata, never the classifier.

Factorising also fixes the rare-class starvation structurally:

| Flat class | Now | As source x is_loop | Gain |
|-----------|-----|---------------------|------|
| Bass Loop | 117 | Bass = 2,204 | 19x |
| Synth Loop | 138 | Synth = 3,664 | 27x |
| Vocal Loop | 102 | Vocal = 1,134 | 11x |

Those are the classes making up ~10% of the served population while being under
2% of training data.

### Other candidate plans (not yet run)

- **Semi-supervised** self-training on the 13,343 unlabelled files, which *are*
  the deployment distribution.
- **Active learning**: route OOD-flagged files to a user-correction queue; the
  design already exists in `SLO_VOCAL_ACTIVE_LEARNING_AND_UX_DESIGN.md` and is
  unimplemented. Converts the 30.8% from a defect into a label source.
- **Calibration** (temperature scaling / conformal) — the model is equally
  confident on served and trained data (0.771 vs 0.786), which is a calibration
  failure; and **coarse-to-fine** answers ("Drum" at 84.9% beats "Kick" at 65%).
- **DSP where DSP is better**: duration/periodicity for loop detection rather
  than asking a global-pooled embedding to infer it.

---

## 10. Encoder comparison — a correction to section 9

### Pilot result

Same 4,359 clips, same folds, same architecture, only the embedding differs:

| Encoder | OOF | Fold range |
|---------|-----|-----------|
| PANNs CNN10 (512-D) | 63.34% | 62.73–63.76 |
| **CLAP (512-D)** | **73.57%** | 71.41–77.06 |
| delta | **+10.23 pp** | no overlap |

Section 9 predicted this would be "near zero", on the reasoning that
non-acoustic label boundaries were the binding constraint. **That prediction
was wrong by 10 points**, and the fold ranges do not overlap, so it is not
noise.

For scale: CLAP on 4,359 clips (73.57%) matches PANNs+DSP trained on all
21,793 (73.51%). A better encoder was worth roughly 5x the training data here.

### Reconciling with the 34% zero-shot result

Two different things were conflated. CLAP's **audio encoder** is much stronger
than CNN10. CLAP's **text space** does not align with producer jargon —
"Foley" and "Percussion" are not describable as prompts. Only the zero-shot
path depended on the text side; the embedding path does not.

### What survives from section 9, and what does not

Still true: Foley vs Percussion is a provenance distinction; Vocal Phrase vs
Vocal Loop is temporal. Those remain absent from the audio.

No longer supported: the claim that a better encoder "cannot fix it". The
~15% label-noise ceiling in section 4.4 was computed from a **PANNs-based**
model, so it was measuring CNN10's representational limits as much as the
labels'. The true ceiling is higher than stated and must be re-derived on the
better encoder.

### Full-corpus bake-off (running)

All 21,793 files, identical folds, seed 42. Arms: PANNs-512, PANNs+DSP-520
(shipping), CLAP-unfused-512, CLAP-unfused+DSP, CLAP-music-512,
CLAP-music+DSP. Two questions beyond the headline: does the DSP block still
contribute +1.95 pp once the encoder is stronger (it may be redundant), and
does the 84.9% four-class ceiling move?

Note on scope: BEATs was planned as a second arm but its weights are not on
HuggingFace and it needs the bespoke `unilm` codebase, which is impractical
on a box with no internet access. `laion/larger_clap_music_and_speech` was
substituted — drop-in with the same code, and music-specific, which suits a
sample library. BEATs remains open if the CLAP arms plateau.

### Two bugs caught, both silent rather than loud

1. **multiprocessing/spawn**: `global OUT_DIR` reassigned inside `main()` is
   not visible to Pool workers on macOS, so all 21,793 converted files landed
   in the held-out directory. Detected because the target directory was 1.8MB
   instead of 2.9GB. Fixed by passing the destination in the task tuple.
2. **Misread timing**: an 8-second `sleep` in the launch command was mistaken
   for the job's runtime, nearly causing a genuine +10.23 pp result to be
   dismissed as impossible. Reading the full log resolved it.

### AudioCraft — evaluated and rejected

Meta's AudioCraft is a **generation** stack (MusicGen/AudioGen/EnCodec), not a
classifier. EnCodec embeddings are reconstruction-optimised rather than
semantically organised, so they generally underperform contrastive/SSL models
on classification. Separately, the code is MIT but MusicGen **weights are
CC-BY-NC** — non-commercial, and therefore disqualifying for a shipped plugin.

---

## 11. Full bake-off + taxonomy ceiling on CLAP (2026-09-09, later)

### Encoder bake-off, full corpus (21,793 files, identical folds, seed 42)

| Arm | OOF | vs shipping |
|-----|-----|-------------|
| CLAP-music + DSP | **82.47%** | +8.91 |
| CLAP-unfused + DSP | 82.20% | +8.64 |
| CLAP-music | 82.16% | +8.60 |
| CLAP-unfused | 81.84% | +8.28 |
| PANNs + DSP (ships today) | 73.56% | 0.00 |
| PANNs only | 71.39% | -2.17 |

The DSP block was largely compensating for a weak encoder: worth +2.17 pp on
PANNs but only +0.31 pp on CLAP-music. Still positive, keep it, but the
+1.95 pp recovered earlier is mostly absorbed once the representation is good.

### Taxonomy ceiling re-derived on CLAP features

Regrouping CLAP-music+DSP OOF predictions (16-class base 82.42%):

| Taxonomy | Classes | Accuracy | vs 16-class |
|----------|---------|----------|-------------|
| **drum family + Foley merged** | 11 | **90.93%** | +8.51 |
| coarse 4-way | 4 | 90.23% | +7.81 |
| merge drum family | 12 | 87.52% | +5.10 |
| merge Foley+Percussion | 15 | 84.69% | +2.27 |
| collapse loop/one-shot | 12 | 82.92% | +0.50 |

**90% is reached on an 11-class taxonomy** (drum family + Foley as one group),
not only a trivial collapse. This corrects the earlier claim that 90% was
unreachable -- that was true only on PANNs features with the flat 16-class
taxonomy.

The taxonomy merge STACKS with the encoder gain: drum merge was +7.16 pp on
PANNs and is +5.10 pp on top of CLAP's already-higher base.

Note "collapse loop/one-shot" gains only +0.50 pp -- CLAP is NOT confusing
loops with one-shots. The temporal-axis concern from section 4.3 was a PANNs
limitation; CLAP largely handles it.

### Residual errors are the non-acoustic boundaries

Top residual confusion pairs (16-class): Foley<->Percussion 12.9%,
Hi-Hat<->Percussion 11.9%, Percussion<->Snare 5.6%, Kick<->Percussion 5.5%.
Percussion (the semantic catch-all) is in four of the top five pairs, 36% of
all errors between them. This is exactly what the drum+Foley merge absorbs,
which is why it reaches 90.93%.

64.4% of errors are made at >0.90 confidence -- the signature of
taxonomy/label-boundary conflicts (Foley vs Percussion is provenance, not
sound) rather than model capacity. The remaining headroom is a taxonomy
decision, not a modelling problem.

### Per-class recall (CLAP-music+DSP, 16-class)

Healthy across the board, including formerly-starved classes: Kick 86.6%,
Synth 90.0%, Vocal Phrase 89.7%, Riser 91.8%, Bass Loop 84.6%, Percussion
83.0%, Foley 81.2%. Weak spots are small and/or genuinely ambiguous classes:
Music Loop 56.5% (n=92), Impact 60.5% (n=185), FX 64.0%, Vocal Loop 67.6%
(n=102).

### The shipping blocker

CLAP is 589-744 MB vs PANNs' 23 MB (~26-32x). Before the +8.91 pp is real for
users: export CLAP's audio tower to ONNX (text tower unused at inference),
int8 quantise, and measure size/accuracy/CPU inference cost. This is the next
engineering task and gates everything.

### Still unmeasured

Real-world accuracy on the ~13,343 no-evidence files ML actually decides.
All figures remain agreement with filename keywords.

---

## 12. Dedicated atonal-hit (drum one-shot) detector (2026-09-09)

A separate, tractable track from the general classifier. Drum one-shots are
acoustically well-separated; the confusion in the main model came from the
Percussion catch-all and folder-derived labels, not from the sounds.

### Fundamental-frequency validation (owner domain knowledge)

Measured f0 from the attack window (dominant spectral peak 30-600Hz, first
120ms) on 300 files/class:

| Class | median f0 | expected | 
|-------|-----------|----------|
| Kick | 67 Hz (54-93) | 50-120 |
| Snare | 214 Hz (167-334) | 180-350 |
| Hi-Hat | 346 Hz, wide spread | noise, no stable f0 |
| Clap | 507 Hz | broadband |

A single f0 threshold at 150Hz separates kick from snare at 79%. f0 is NOT
in the existing 8 DSP features -- genuinely new, independent information.

### Feature progression (4 drum classes, 5-fold CV, no neural embedding)

| Feature set | Accuracy |
|-------------|----------|
| 8 coarse DSP features | 71.5% |
| + 3 f0/salience/low-band | 80.1% |
| + envelope(attack/decay/sustain) + onset density + 20 MFCC | 84.2% |

Kick reaches 96.8% recall (pitched low fundamental is decisive). Residual is
Snare<->Clap (the hand-transient pair; onset density helps, does not fully
resolve).

### Confidence-gated auto-rename (the shipping-relevant metric)

| conf threshold | coverage | precision |
|----------------|----------|-----------|
| >= 0.8 | 45% | 97.1% |
| >= 0.9 | 27% | 98.5% |

Per-class @>=0.8: Kick 95.8%, Snare 98.7%, Hi-Hat 97.3%, Clap 97.9%. A
gated renamer tags ~half the drum one-shots at ~97% precision and defers the
rest. Model is a few-KB RandomForest, instant on CPU, no CLAP dependency.

### Foley is the deliberate exception

Foley is defined by provenance (a recorded real object), not acoustic
content -- a struck can and a conga are the same signal. f0/sustain analysis
cannot recover provenance. Recommendation: detect the acoustic thing
(percussive hit) and keep "Foley" as a folder/metadata tag, not a classifier
target.

### Tooling added
- drum_detector_features.py -- enriched 28-feature extractor (f0 block,
  temporal envelope, onset density, MFCCs)
- test_f0_drums.py, test_f0_gain.py -- f0 validation harnesses

---

## 13. Evidence-fusion classifier + by-ear ground truth (2026-09-09)

### By-ear labelling

Built label_tool.py (stdlib local web labeller) and hand-labelled 649 files
across an 18-class drum/loop taxonomy the owner defined (Kick, Snare, Rimshot,
Hi-Hat, Crash, Clap, Percussion, Foley, and Kick/Snare/Drum/Top/Hi-Hat/
Percussion/Bass/Foley/Chord/generic Loop, plus Other and Misc/Review). This is
the first ground truth in the project; every prior figure was keyword agreement.

### Keyword labeller measured against ear

The existing keyword labeller is **71.9% accurate on drum one-shots** (287/399):
Kick 64%, Snare 76%, Hi-Hat 60%, Clap 88%. ~28% of keyword-tagged drums are
something else. This is why "84% vs keyword labels" understated the model -- it
was penalised for disagreeing with wrong keywords.

### Filename synonym detector (name_detect.py)

Word-boundary synonym dictionary, separators normalised so 808_kick and
Drum_Loop match. Validated: 82% coverage, 81% precision vs ear. Trustworthy
tokens: Kick 97%, Hi-Hat 94%, Snare 92%, Clap 90%, Crash 89%, Percussion Loop
100%. Must-defer: bare loop/bpm 0% (unqualified drum loops), Foley 53%.

### Duration and onset density (loop vs one-shot)

One-shots median 0.74s, loops 5.58s. But duration alone mis-flags long-decay
one-shots: a crash rings 3.2s and got upgraded to Drum Loop. The real signal is
rhythmic repetition -- full-file onset count: loops median 22, crash 7. Rule
`duration>=2.5s AND onsets>=8` = 93.8% loop detection and keeps crashes as
one-shots. (Sustain-as-energy-near-peak was tested and is worse: crashes
sustain 0.49 > loops 0.21, because a decay tail stays above threshold.)

### Fusion (fusion_classify.py)

Filename family -> duration/onset sets loop vs one-shot -> acoustic RF when the
name is silent -> melodic gate (high f0 + salience + loop-length -> Chord).

| Method | Coverage | Precision | Overall |
|--------|----------|-----------|---------|
| filename-only | 82% | 81% | 66.3% |
| acoustic-only | 92% | 61% | 56.1% |
| **FUSION** | **100%** | **71.8%** | **71.8%** |

Fusion per-class recall (viable classes): Kick 98.6%, Clap 96.7%, Snare 91.8%,
Rimshot 90.9%, Hi-Hat 82.0%, Percussion 80.9%. Confidence-gated (retrain_on_ear)
the drum one-shots reach ~95% at >=0.7 -- the shippable renamer operating point.

Weak frontier: loop sub-classification (Drum Loop 49%, Percussion Loop 36%,
Hi-Hat Loop 38%, Foley Loop 15%) -- acoustically subtle and filename-sparse --
and Other/none 33% (grab-bag, expected). These need either more labels or the
harmonic/temporal feature block (still unbuilt) to improve.

### Net

One-shot drum detection is effectively solved for renaming (95% gated). Loop
type and the non-acoustic categories (Foley provenance) remain the open work.

---

## 14. Two-stage loops: full-file spectral features (2026-09-09)

The loop frontier (Drum/Percussion/Hi-Hat Loop, 36-49%) was weak because the
detector used attack-focused features (f0 of the first 120ms, single-hit MFCC)
that are blind to a loop's spectral profile. loop_features.py adds full-file
band-energy features. Measured profiles are cleanly distinct:

| Loop type | sub<100 | low | mid | high | vhigh | centroid |
|-----------|---------|-----|-----|------|-------|----------|
| Drum Loop | 0.13 | 0.17 | 0.23 | 0.37 | 0.10 | 0.27 |
| Percussion Loop | 0.07 | 0.11 | 0.29 | 0.43 | 0.11 | 0.30 |
| Hi-Hat Loop | 0.00 | 0.01 | 0.10 | 0.62 | 0.28 | 0.55 |
| Foley Loop | 0.07 | 0.07 | 0.39 | 0.40 | 0.06 | 0.25 |

The kick (sub/low energy) separates Drum from Percussion loops; the absent low
end + high centroid make Hi-Hat loops near-trivial. Drum vs Percussion Loop =
86.8% on these features alone (vs 36-49% before).

Wired as a two-stage classifier: a rhythmic loop with no explicit loop-token
goes to the loop model. Fusion overall 71.8% -> 76.1%. Per-class:

| Loop class | before | after |
|------------|--------|-------|
| Drum Loop | 48.8% | 90.2% |
| Percussion Loop | 35.7% | 57.1% |
| Foley Loop | 15.4% | 30.8% |

Drum Loop is now as reliable as the one-shots. Foley Loop remains weak
(provenance: a percussive foley loop is acoustically a perc loop). Integrated
into fusion_renamer -- files with useless names (e.g. "HAGGIS", "113BPM_2")
now classify correctly via the acoustic loop model.

---

## 15. Crash leak fixed: sustained-energy loop gate (2026-09-09)

Crash was 39% -- 9 of 23 crashes leaked into Drum Loop because a crash rings
>2.5s and its cymbal shimmer throws enough spectral-flux onsets to pass the
loop gate. The distinguisher: a crash is one hit that decays; a loop sustains.
Energy last-third/first-third ratio: crash median 0.00, loop 0.87. Adding
`decay_ratio >= 0.25` to the loop gate keeps 91% of loops and rejects 91% of
crashes.

Result: Crash 39% -> 78.3%, fusion overall 76.1% -> 77.9%, Drum Loop holds
87.8%. Remaining crash errors are Clap/Hi-Hat (genuine cymbal/transient
overlap, small n).

### Fusion progression this session
| Stage | Overall | Drum Loop | Crash |
|-------|---------|-----------|-------|
| filename+acoustic+duration | 69.7% | 48.8% | 21.7% |
| + onset-density loop test | 71.8% | 48.8% | 39.1% |
| + two-stage loop model | 76.1% | 90.2% | 39.1% |
| + sustained-energy gate | 77.9% | 87.8% | 78.3% |

Now strong (>=78%): Kick 99, Clap 97, Snare 92, Rimshot 91, Drum Loop 88,
Hi-Hat 82, Percussion 81, Crash 78. Weak: Percussion Loop 57, Foley 54,
Foley Loop / Hi-Hat Loop / bare Loop (thin data or provenance), Other/none 33.

---

## 16. Correction: the "DSP evidence 1.2%" figure is a measurement artifact

`REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md` reports an evidence breakdown of
FOLDER 98.5% / FILENAME 81.2% / DSP 1.2%, and an audio-only accuracy of 17.5%.
The DSP figure has been read as the acoustic path being broken. It is not.
Three compounding problems make that number meaningless:

**1. Circular ground truth.** The report states truth is "derived from each
vendor pack's own folder naming" and is "not hand-verified per file". FOLDER
evidence reads folder names; truth *is* the folder name. 98.5% is therefore
close to tautological, and it inflates the 77.9% full-evidence headline.

**2. Adversarial selection.** DSP only wins when EMBEDDED_METADATA/FILENAME/
FOLDER all fail. So DSP is evaluated exclusively on the subset where naming is
unreadable, while truth is still taken from that same unreadable naming. This
is the same selection bias documented in section 4.2: the acoustic path is
judged only on the population the other evidence could not handle.

**3. The OOD gate is penalised for working.** Of 576 DSP-winning items, 230
(40%) return NO subcategory at tagConfidence exactly 0.00 -- i.e. the engine
declined to guess. Inspection shows these are `Crickets 1.wav`,
`AFTA_Texture 1.wav`, `FG_Texture_BottleFoley.wav`,
`GOTV_Noise Pops & Clicks.wav` and similar: genuinely out-of-domain texture and
field-recording content. Refusing them is correct behaviour -- the same gate the
OOD report credits with a 100% correct-rejection rate -- but the benchmark
scores every refusal as a wrong answer.

The remaining 346 items do predict, at mean confidence 0.382, and are mostly
wrong; but they are scored against folder-derived truth on files whose folders
the parser could not read, so that too is weak evidence either way.

### Consequences

- Do not treat 1.2% as the acoustic model's quality, and do not treat 98.5%
  (FOLDER) or the 77.9% blend as evidence of product accuracy.
- A refusal is not an error. Any future benchmark must score
  correct-rejection separately from misclassification, or the OOD gate will
  always look like a failure.
- The only non-circular ground truth in this project remains the 649 by-ear
  labels (section 13). Measured there: keyword/folder-derived labels are
  themselves only 71.9% accurate on drum one-shots.

### Recommended fix

Re-run the corpus benchmark scoring against hand-verified labels, with three
buckets rather than two: correct / incorrect / correctly-refused. Until then
the cross-vendor report should be read as a coverage report, not an accuracy one.

---

## 17. Bioacoustics encoder (Perch v2) bake-off — 2026-09-10

Hypothesis (owner's suggestion): bioacoustics models are trained on short,
transient, real-world recorded sounds, so they may help on the classes every
music/AudioSet-trained encoder handles worst -- Foley and Percussion.

Tested Perch v2 (Google, Apache-2.0, via justinchuby/Perch-onnx) against CLAP
and the handcrafted 33-D features, on the 649 by-ear labels (the only
non-circular ground truth), identical folds. Perch takes [batch,160000] = 5s @
32kHz, which is exactly what the C++ production path already produces.

| Encoder | Accuracy |
|---------|----------|
| Perch (1536-D) | 70.9% |
| CLAP (512-D) | 69.1% |
| handcrafted (33-D) | 60.9% |
| **Perch + CLAP** | **73.0%** |
| Perch + CLAP + DSP | 72.6% |

**The hypothesis was right that Perch helps, and wrong about why.**

| Class | Perch | CLAP |
|-------|-------|------|
| Crash | **74%** | 57% |
| Snare | **81%** | 74% |
| Kick | **90%** | 85% |
| Drum Loop | **80%** | 76% |
| Percussion | 38% | **43%** |
| Foley | 23% | **27%** |

Perch loses on Foley and Percussion -- the classes it was predicted to win.
What it wins is sharp TRANSIENTS (Crash +17pp, Snare +7pp). Bird calls and
insect clicks are transient events with complex spectral structure, so the
transfer is to attack character, not texture.

### Conclusions

1. Perch and CLAP are complementary (transient vs timbre) and their
   concatenation is the best result measured: 73.0%.
2. Foley is 23-27% across three independent encoders and 4% on handcrafted
   features. That is now conclusive: Foley is a provenance category, not an
   acoustic one, and belongs as a metadata/folder tag rather than a classifier
   target.
3. The handcrafted 33-D features still beat both deep encoders on Kick (93%),
   where the physics (low pitched fundamental) is unambiguous. Cheap features
   remain best where the physical signature is clear.

Licensing note: Perch is Apache-2.0 and usable commercially. BirdNET is
CC-BY-NC on several releases and is NOT usable in a shipped plugin.

---

## 18. Learned fusion vs rule cascade, and the right synthesis (2026-09-10)

### Negative result: a learned fusion does NOT beat the hand-written cascade

Trained one classifier over all signals concatenated (Perch 1536 + CLAP 512 +
handcrafted 33 + temporal 4 + filename one-hot 18), 530 files, 10 classes:

| Signals | Accuracy |
|---------|----------|
| Perch + CLAP | 73.0% |
| + handcrafted DSP | 73.0% (+0.0) |
| + temporal | 73.0% (+0.0) |
| + filename | 76.6% (+3.6) |
| **rule cascade (fusion_classify)** | **77.9%** |

Two findings:

1. **The handcrafted 33-D and temporal features add nothing on top of Perch+
   CLAP.** The deep encoders already encode duration/attack/spectral character.
   The handcrafted block still earns its place as a CHEAP standalone (60.9% with
   no 400MB model), but it is redundant alongside the encoders.
2. **The rule cascade wins because it encodes measured knowledge the model
   cannot learn from 530 examples.** The cascade hard-overrides on filename
   tokens whose precision was measured at 90-97%; the learned model sees those
   as 18 features diluted among 2085 audio dimensions and cannot discover how
   decisively to trust them. Per-class the cascade wins on Percussion (81 vs
   60), Snare (93 vs 82), Clap (98 vs 90).

This is a case where hand-written domain rules beat learning, because of label
scarcity rather than because the rules are cleverer.

### The right synthesis: keep the rules, upgrade the engine behind them

The cascade's acoustic fallback was still the weak handcrafted 33-D (60.9%).
Replacing only that stage with Perch+CLAP, keeping every filename rule:

**77.9% -> 81.9%**

| Class | handcrafted acoustic | Perch+CLAP acoustic |
|-------|---------------------|---------------------|
| Hi-Hat | 82.0% | **88.3%** |
| Crash | 78.3% | **82.6%** |
| Other/none | 33.3% | **47.3%** |
| Clap | 97.8% | 98.9% |
| Snare | 92.9% | 94.1% |
| Drum Loop | 87.8% | 90.2% |
| Kick | 98.6% | 97.2% |
| Percussion | 80.9% | 78.7% |
| Percussion Loop | 57.1% | 53.6% |
| Foley | 53.8% | **19.2%** |

Foley regressed sharply: its filename token precision (0.53) is below the trust
threshold so it routes to acoustic, and Perch/CLAP are worse on Foley than the
handcrafted features were. Consistent with sections 13/17 -- Foley is
provenance, not acoustics.

### Deployment implication

81.9% requires Perch (409MB) + CLAP (271MB) at inference. The handcrafted
cascade at 77.9% requires neither. That is a 4pp accuracy / ~680MB tradeoff
which is a product decision, not a technical one.

---

## 19. Foley resolved: it was a dumping ground; function and source are separate axes

### Foley is not a coherent acoustic category (owner hypothesis, confirmed)

Hypothesis: "maybe we call something we don't understand Foley". Tested by
measuring acoustic coherence -- mean cosine of each class's members to their own
centroid in Perch+CLAP space. A real category clusters; a dumping ground scatters.

| Class | coherence | scatters into |
|-------|-----------|---------------|
| Kick | 0.854 | 3 classes |
| Clap | 0.816 | 2 |
| Snare | 0.816 | 5 |
| Hi-Hat | 0.772 | 6 |
| Drum Loop | 0.769 | 4 |
| Crash | 0.731 | 4 |
| Percussion | 0.705 | 7 |
| **Foley** | **0.656** | **8** |
| Percussion Loop | 0.638 | 7 |
| Other/none | 0.594 | 11 |

Foley is the second-least-coherent class in the taxonomy, immediately above the
bin literally named "none". Confirmed: it functions as a partial catch-all.

### Removing it as a classifier target: 81.9% -> 86.1%

Dropping Foley/Foley Loop from the acoustic targets gained +4.2pp overall and
also lifted Snare (94.1 -> 95.3) and Other/none (47.3 -> 54.5), which it had
been polluting.

### Object nouns tag SOURCE, not category

Owner idea: detect physical-object names (kitchen, wood, glass) and call those
Foley. Measured against by-ear labels:

| Detector | recall | precision |
|----------|--------|-----------|
| explicit "foley" wording | 46% | **75%** |
| physical-object nouns | 31% | 31% |
| combined | 62% | 42% |

Object nouns are a poor Foley *detector* but for an instructive reason: the
misses are files like `JVIEWS_hihat_alternative_clock_shop_113.wav` and
`JVIEWS_suitcase_and_amp_138.wav` -- hi-hats built from clock-shop and suitcase
recordings. Producers name a sample after what MADE it even when it FUNCTIONS as
a drum.

So object nouns are not detecting the wrong thing, they are detecting a
different, also-valuable thing:

- **Function** (Kick / Hi-Hat / Drum Loop) -- what the producer uses it as. The
  classifier's job.
- **Source / material** (clock, suitcase, glass, wood) -- what made it. A
  searchable TAG, orthogonal to function.

Implemented in fusion_renamer as `foley_tag()` (explicit foley wording, 75%
precision, advisory only) and `source_tags()` (object nouns -> searchable
metadata). A clock-shop hi-hat is now classified Hi-Hat AND tagged 'clock', so
it is findable both ways.

### Net

Foley is removed as a classifier target. The taxonomy now separates function
(predicted) from provenance/source (tagged), which is the distinction that has
been causing trouble since section 13.

---

## 20. Encoder lever exhausted: MERT/AST bake-off (2026-09-10)

Prediction: MERT (music SSL, MIT) would be the strongest single encoder because
it is the only one trained on the corpus domain (music), where CLAP is general
audio, Perch is bioacoustics and PANNs is AudioSet events.

**Wrong.** MERT is the WEAKEST single encoder tested.

| Encoder | Alone | Domain |
|---------|-------|--------|
| Perch v2 | **70.9%** | bioacoustics (short transient events) |
| CLAP | 69.1% | general audio + text |
| AST | 64.0% | AudioSet (ViT) |
| MERT | **57.4%** | music SSL (songs) |

MERT models musical structure over time -- tempo, key, harmony. The corpus is
isolated one-shots and short loops; a 5s window holding a single kick has no
musical structure to model. **The relevant domain is not "music", it is "short
isolated sound events"** -- which is what Perch (bird/insect calls) and CLAP
(audio events) are trained on. The domain match was on the wrong axis.

### Ensembles still gain, but with clear diminishing returns

| Ensemble | Accuracy | Approx. weight |
|----------|----------|----------------|
| Perch + CLAP | 73.0% | ~680 MB |
| + MERT | 74.7% | ~1.06 GB |
| + AST | **75.5%** | **~1.4 GB** |

MERT adds +1.7pp to the ensemble despite being weakest alone -- it contributes
something the others do not. But **+2.5pp for doubling model weight** is a poor
deployment trade against Perch+CLAP, and a very poor one against the handcrafted
cascade (~0 MB).

For scale: Perch->CLAP was +10.23pp. Four encoders buys +2.5pp.

**Conclusion: the encoder-swap lever is exhausted.** Remaining gains lie in
taxonomy hygiene (`Other/none`, per section 19's Foley precedent), calibration,
and per-class routing -- none of which cost model weight or labels.

### Not worth testing further
- EnCodec / DAC: neural codecs optimise reconstruction, not semantic
  organisation.
- Whisper / Wav2Vec2 / HuBERT: speech-trained, wrong domain.
- AudioCraft / MusicGen: generation not classification, and CC-BY-NC weights are
  unusable commercially.
- BEATs remains the only untested candidate with a plausible case (SOTA AudioSet
  mAP), but its weights are not on HF and it needs the unilm codebase.

---

## 21. REJECTED: dropping `Other/none` as a class (2026-09-10)

Section 19 removed Foley as a classifier target for +4.2pp. `Other/none` shows
the same coherence signature (0.594, scatters into 11 classes), so the same
treatment was tried. **It must not be applied.**

Dropping it appears to give 86.1% -> 90.9%, and lifts Percussion (+4.3) and Drum
Loop (+4.9). But that 90.9% is measured on 449 files instead of 504 -- it simply
**excludes the 55 hardest files**. It is not comparable to 86.1%. This is the
same measurement fault criticised in section 16: scoring on a subset that removes
the difficult cases.

Worse, the change is actively harmful. With no `Other/none` class to fall back
on, the model does not become uncertain about junk -- it becomes confidently
wrong:

| Confidence gate | real files kept | junk let through |
|-----------------|-----------------|------------------|
| >= 0.7 | 100% | **70.9%** |
| >= 0.8 | 100% | **60.0%** |
| >= 0.9 | 100% | **43.6%** |

(Absolute confidences are optimistic -- fit and scored on the same data -- but
the gap between real 0.997 and ex-junk 0.809 is the real signal.)

At a 0.9 gate, 44% of genuine none-of-the-above files would be confidently
mis-renamed.

### The distinction that matters

- **Foley was MISLABELLED.** Its files genuinely belong to real acoustic classes
  (a struck can is acoustically percussion). Removing the label let them go where
  they belonged. Correct.
- **`Other/none` is GENUINELY none-of-the-above.** Its files belong to no real
  class. Removing the label does not make them classifiable; it removes the
  model's ability to express rejection.

**Treatment:** `Other/none` stays a TRAINABLE class (so rejection is
expressible) while remaining a NON-RENAME target (already the case via
NON_TARGETS in fusion_renamer). Coherence alone does not justify removing a
class -- the question is whether its members belong somewhere else.

**86.1% remains the honest headline.**

---

## 22. Confidence calibration (2026-09-10)

The renamer only acts above a confidence threshold, so the gate is the product.
Section 21 found genuine none-of-the-above files scoring 0.809 mean confidence,
which suggested the gate does not mean what it appears to. Measured properly on
out-of-fold data, the Perch+CLAP stage is badly overconfident:

| stated confidence | actual accuracy | gap |
|-------------------|-----------------|-----|
| 0.748 | 0.425 | **+0.323** |
| 0.853 | 0.600 | +0.253 |
| 0.986 | 0.879 | +0.107 |

ECE = 0.145. Temperature scaling (T fitted on half the out-of-fold logits,
evaluated on the other half) gives **T = 2.28** -- the model is ~2.3x
overconfident. Held-out ECE **0.142 -> 0.075 (47% better)**.

### Product metric: coverage at 95% precision

| | coverage | gate needed |
|---|----------|-------------|
| uncalibrated | 43.7% | **0.994** |
| temperature-scaled | **48.4%** | 0.770 |

Two gains. ~5% more of the library auto-renames at the same safety level; and
the threshold becomes interpretable -- uncalibrated you had to demand 0.994
(near-certainty) to reach 95% precision, calibrated 0.77 achieves it.

(The 98%-precision comparison, 2.4% vs 1.2%, is on single-digit counts and too
noisy to read.)

### Safety consequence

**Calibration is a prerequisite for adopting the Perch+CLAP acoustic stage, not
an optimisation.** Uncalibrated, the renamer's default 0.75-0.80 gate would
admit files that are only 42-60% correct and would over-rename. `CALIBRATION_T`
and `calibrated()` are now in fusion_renamer; the handcrafted RandomForest path
is separately better calibrated (94.7% measured at its 0.7 gate) and does not
need it.

---

## 23. C++ integration: measured loop rule ported (2026-09-10)

First piece of the Python work ported into the production engine. Chosen
because it is **independent of the unresolved model-size decision** -- pure
arithmetic, no model weight.

### What was replaced

`AbletonTaxonomy::detectLoopVsOneShot` used a duration/decayTime-ratio
heuristic whose own source comment recorded that "no threshold gives strong
recall+precision together", that the signal "has limited discriminative power
on this corpus", and that its threshold was set to verify "net-neutral" against
the 620-file corpus (390/620 before and after, zero newly-wrong, zero
newly-correct). It changed no outcomes.

Its documented failure mode was exactly the one we hit independently: a long
one-shot with a natural tail (crash, reverb) promoted to Loop.

### What replaced it

```
isLoop = durationSeconds >= 1.5  AND  energyDecayRatio >= 0.10
```

`energyDecayRatio` = mean-square energy of the final third over the first
third. A crash is front-loaded (~0.00 by the final third); a loop sustains
(~0.87).

**Measured 96.4% held-out** (649 by-ear labels, 5-fold CV with thresholds
fitted on the train fold only), versus 90.8% for duration alone. `duration >=
1.5s` was selected in all five folds.

Note this beats the Python rule in use (`duration>=2.5 AND onsets>=8 AND
decay_ratio>=0.25`, 95.6%) while needing no onset detector -- so the port is
both simpler and slightly better. Onset counting was avoided deliberately:
librosa's spectral-flux peak picker and the engine's own onset counter are
different algorithms and their absolute counts are not interchangeable, so a
threshold tuned on one would not transfer.

### Changes
- `AudioFeatures` and `AudioAnalysisResult` gain `energyDecayRatio` (default
  1.0 = sustained, so a legacy row is never spuriously demoted to one-shot).
- Computed in both `analyzeAudioBuffer` and `analyzeAudioProperties`.
- `TaxonomyInput` gains the field; wired at both call sites.
- New 3-arg `detectLoopVsOneShot` overload carries the measured rule.
- **The 2-arg overload preserves the ORIGINAL heuristic verbatim.** Forwarding a
  neutral ratio instead would have classified every file >= 1.5s as a loop,
  silently breaking un-updated callers. The existing tests caught this.

### Verification
`TestTaxonomy` passes including three new cases for the measured rule (long +
sustained -> Loop; long crash with decayed tail -> One-Shot; short -> One-Shot).
`TestAcousticClassifierParity` and `TestCachedReclassification` unchanged and
passing.

---

## 24. C++ filename heuristic corrected against by-ear labels (2026-09-10)

Second decision-independent port. The engine's filename/folder token matcher in
`prepareFile()` had six mappings that are measurably wrong. Each was checked
against the 649 by-ear labels rather than assumed:

| Token | C++ said | Ear says | Agreement |
|-------|----------|----------|-----------|
| `crash` | Hi-Hat | **Crash** | 6/6 |
| `cymbal` | Hi-Hat | **Crash** | 10/12 |
| `shaker` | Hi-Hat | **Percussion** | 11/12 (incl. Percussion Loop) |
| `tambourine` | Hi-Hat | **Percussion** | 3/5 |
| `rim` | Snare | **Rimshot** | 8/11 |
| `snap` | Snare | **Foley** | 5/6 (only 1/6 was Snare) |

Confirmed correct and left alone: `kick` 56/62, `snare` 76/84, `clap` 86/89,
`hat` 35/42, `tom` 7/8, `perc` 15/23.

### Changes
- `crash`/`cymbal`/`splash`/`china` -> **Crash** (new emitter)
- `rim`/`rimshot`/`xstick` -> **Rimshot** (new emitter, ordered BEFORE snare so
  "rimshot" is not swallowed by the snare rule)
- `shaker`/`tambourine` moved Hi-Hat -> Percussion; percussion vocabulary
  extended (djembe, cajon, timbale, guiro, agogo, tamb)
- `snap` removed from Snare -- 5 of 6 were Foley, so the mapping was actively
  harmful; left unmatched to defer to acoustics
- `ride` removed from Hi-Hat -- genuinely ambiguous (3/8 Misc/Review, 2/8
  Hi-Hat), so no confident mapping is justified

**`Crash` and `Rimshot` already existed in `AbletonTaxonomy`'s subcategory table
but were unreachable**, because nothing in the pipeline ever emitted those
instrument types. The taxonomy could describe them; the classifier could never
produce them.

Verification: `TestTaxonomy`, `TestCachedReclassification` and
`TestAcousticClassifierParity` all pass.

### Not ported, and why

The full Python synonym dictionary (`name_detect.py`) additionally carries
per-class measured precision weights used to decide whether the filename should
override acoustics. That belongs with the confidence-gated cascade, which is
still Python-side and gated on the model-size decision. What is ported here is
the part that is unambiguously correct regardless of that decision: the token
-> type mappings themselves.

---

## 25. Foley implemented as a SOURCE ATTRIBUTE in C++ (2026-09-10)

Earlier sections framed this as "demoting" Foley. That framing was wrong.
Foley matters to users -- which is precisely why it must not be derived from
audio, where it would be wrong ~75% of the time. The question was never whether
to keep Foley, but which evidence source makes it reliable.

### Folder evidence was tested and rejected

| Source | coverage | precision |
|--------|----------|-----------|
| filename (basename) | 82.8% | **78.6%** |
| immediate folder only | 31.6% | 51.1% |
| folder + basename | 85.6% | 75.5% |
| filename ELSE folder | 85.6% | 77.3% |

Folder-only precision is 51%. The cascade buys +2.8pp coverage for -1.3pp
precision. Not worth it; files without filename evidence should go to the
acoustic stage, which is what the architecture already does.

### Full-library coverage scan (69,508 files, 5s)

| | |
|---|---|
| filename evidence present | 30,568 (44.0%) |
| **no filename evidence** | **38,940 (56.0%)** |

Note this is far below the 77-83% quoted in section 13, because that figure used
folder AND filename while `name_detect` reads only the basename. **56% of the
real library must be decided acoustically** -- a much larger burden than
previously assumed.

Library composition by filename evidence: Loop 10.8%, Kick 10.3%, Percussion
9.9%, Snare 7.9%, Impact 7.1%, Foley 6.8%, Chord Loop 5.1%, Hi-Hat 5.0%.

### Foley as an attribute

Implemented `AbletonTaxonomy::isFoleySourced()`, emitted as a SECONDARY TAG
beside the functional subcategory rather than replacing it. A hi-hat built from
clock-shop recordings is honestly `{subcategory: "Hi-Hat Loop", tags: [...,
"Foley"]}` -- findable both ways.

Vocabulary tuning (measured on by-ear labels):

| lexicon | recall | precision |
|---------|--------|-----------|
| broad object nouns | 31% | 32% |
| tightened objects only | 26% | 67% |
| **foley wording + tight objects** | **62%** | **69%** |
| foley wording alone | 46% | 75% |

Producer-descriptor words that merely look like objects were removed after
inspection: **"dirty" means distorted** (owner confirmation), "knock" describes
a snare's punch, "metal" is often a genre. Including them dropped precision to
32%. `dirt` was additionally matching inside "Dirty" -- the C++ implementation
uses explicit word-boundary matching and normalises `_ - .` to spaces, since
underscores are word characters and a naive boundary test misses them.

Verification: `TestTaxonomy` includes seven cases covering the clock-shop
hi-hat, explicit wording, object nouns, and all three descriptor false
positives. All C++ suites pass.

---

## 26. Tested and rejected: stereo, inharmonicity, spectral trajectory (2026-09-10)

Three proposed signals, all measured on the by-ear labels. Recording the
negative result so they are not re-attempted.

### The signals are real and interpretable

| Class | stereo corr | stereo width | flux |
|-------|-------------|--------------|------|
| Crash | +0.37 | **0.68** | 5.95 |
| Clap | +0.55 | 0.39 | 22.8 |
| Hi-Hat | +0.75 | 0.22 | 30.1 |
| Kick | **+0.94** | **0.05** | 26.8 |
| Drum Loop | +0.93 | 0.05 | **4.87** |

Stereo width matches production convention exactly -- kicks centred (0.05),
crashes and claps widened (0.68 / 0.39). Flux cleanly separates loops (4.9-6.2)
from one-shots (20-30). Both look highly promising in isolation.

### But they add almost nothing on top of the existing 33 features

| Features | Accuracy |
|----------|----------|
| current 33 | 61.7% |
| + stereo (corr, width) | 62.9% |
| + spectral flux | **63.8%** |
| + brightness slope | 62.7% |
| + all four | 62.5% (**worse than flux alone**) |

All four combined scoring below flux alone indicates noise-fitting at n=525.

Decisive test on the specific hypothesis -- stereo should fix Crash vs Hi-Hat,
where widths are 0.68 vs 0.22:

| | Crash vs Hi-Hat (n=81) |
|---|---|
| 33 features | 89.0% |
| 33 + stereo | **89.0% (+0.0)** |
| stereo alone | 65.2% |

Stereo alone beats chance, so the signal is genuine -- but the 33 features
already encode everything it contributes. MFCCs capture spectral shape and the
timbre block carries ZCR and harmonic ratio.

### Inharmonicity: no signal at all

Every class measured 0.08-0.09 (deviation of partials from integer multiples of
f0). No discrimination whatsoever. Either drum content is uniformly inharmonic
or the estimator is too crude; either way it is not worth pursuing.

### Lesson

This is the third instance of the same pattern (see also section 18: handcrafted
features adding +0.0pp on top of Perch+CLAP). **A signal being real,
interpretable, and visibly separating in a class-mean table does not mean it is
NEW information.** Redundancy with existing features must be measured, not
assumed. Only spectral flux showed a gain worth anything (+2.1pp) and even that
did not survive combination.

---

## 27. Quantisation solves the size problem; pseudo-labelling breaks the accuracy ceiling (2026-09-10)

### Quantisation: 693 MB -> 210 MB at no accuracy cost

Dynamic int8 initially failed on both models with a shape-inference error, then
produced a model that would not run (`ConvInteger` unimplemented on the CPU EP).
Two fixes: strip the graph's stale `value_info` before quantising, and restrict
quantisation to MatMul so Convs stay float.

| Model | fp32 | int8 | embedding cosine |
|-------|------|------|------------------|
| Perch v2 | 409 MB | **131 MB** | 0.9997 |
| CLAP | 284 MB | **79 MB** | 0.9975 |
| **total** | **693 MB** | **210 MB** | — |

End-to-end accuracy check (9 classes, by-ear labels): fp32 77.8%, **int8 78.2%**
-- within noise, i.e. quantisation is free. CPU latency 232 ms (Perch) + 299 ms
(CLAP) per clip, one-time and cached.

**210 MB is ordinary plugin territory.** The size objection is resolved.

### Every modelling lever is now exhausted

| Lever | Result |
|-------|--------|
| Better encoders | +2.5pp for 2x weight (section 20) |
| More features: stereo, harmonics, trajectory | **+0.0pp** (section 26) |
| Learned fusion over all signals | *worse* than hand rules (section 18) |
| Better classifier head | +0.4pp -- noise |

Six classifier heads (LogisticRegression, linear SVM, RBF SVM, two MLPs,
RandomForest) span 76.0-78.2%. A 2.2pp spread across that much architectural
variety is noise. **The ceiling is what 504 labelled files can support.** The
binding constraint is data, not method.

### Pseudo-labelling: +7.9pp, no manual labelling

Section 13 measured that when filename and acoustic evidence independently
agree, they are 95.5% correct. Using that agreement to manufacture labels from
the 21,793-file corpus yields 4,162 pseudo-labels (Percussion 1026, Kick 969,
Snare 914, Hi-Hat 659, Clap 594).

Trained on by-ear + pseudo-labels, evaluated only on held-out BY-EAR labels
(CLAP embeddings):

| Training data | Accuracy |
|---------------|----------|
| by-ear only (504) | 69.7% |
| + 1,000 pseudo | 73.0% |
| **+ 3,000 pseudo** | **77.6%** |
| + 4,162 pseudo | 76.6% |

**+7.9pp**, peaking near 3,000 then tailing off as pseudo-label noise
accumulates. This is the largest single gain since the encoder swap, and it
required no manual labelling.

### Methodology note

A first run of this experiment reported a 53.7% baseline. That was a row
misalignment: the local script filters rows by `os.path.exists()`, which the
remote box cannot evaluate, so 510 labels were scored against 504 embeddings.
Caught because the baseline contradicted CLAP's known 69.1%. Fixed by shipping a
pre-aligned (labels, embeddings) pair rather than re-deriving the filter
remotely. **A baseline that disagrees with a previously measured number is a bug
signal, not a discovery.**

---

## 28. Pseudo-labelling does not stack with better representations (2026-09-10)

Section 27 measured +7.9pp from pseudo-labelling on CLAP-only embeddings.
Extracted Perch for the full 21,793-file corpus (22 min on the 96-core box) to
test whether it stacks on the full Perch+CLAP stack.

**It does not.**

| Training data | CLAP only | Perch+CLAP |
|---------------|-----------|------------|
| by-ear only (504) | 69.7% | 75.8% |
| + 3,000 pseudo | 77.6% (**+7.9**) | 76.4% (+0.6) |
| + 4,162 pseudo | 76.6% | 76.8% (+1.0) |

Pseudo-labelling substitutes for representation quality rather than adding to
it. Once the representation is good, the extra data has little left to teach.

### The per-class mechanism

| Class | change | in pseudo set? |
|-------|--------|----------------|
| Percussion | 42.6 -> 57.4 (+14.8) | yes (1026) |
| Crash | 69.6 -> 78.3 (+8.7) | yes |
| Hi-Hat | 81.7 -> 85.0 (+3.3) | yes (659) |
| Clap | 87.2 -> 90.4 (+3.2) | yes (594) |
| **Other/none** | 52.7 -> **41.8** (-10.9) | **no** |
| **Percussion Loop** | 71.4 -> **60.7** (-10.7) | **no** |

The keyword matcher only produces five classes, so adding thousands of those
skews the class balance and starves everything else. The near-zero net is those
two effects cancelling.

Balancing was tested as the obvious fix -- capping pseudo-labels per class at
50/100/200/400 -- and does not work either: 74.6-75.8% against a 75.8%
baseline. Capping removes the harm but also removes the benefit.

### Levers now measured and exhausted

| Lever | Result | Section |
|-------|--------|---------|
| Better encoders | +2.5pp for 2x weight | 20 |
| More features (stereo, harmonics, trajectory) | +0.0pp | 26 |
| Learned fusion over all signals | worse than hand rules | 18 |
| Better classifier head (6 architectures) | +0.4pp, noise | 27 |
| Pseudo-labelling | +1.0pp on the full stack | this |

**There is no algorithmic shortcut remaining that has not been measured.** The
path to materially higher accuracy is more REAL labels. Every substitute for
them has now been tried and quantified.

Practical note: the per-class results do suggest a targeted use -- pseudo-labels
lifted Percussion by +14.8pp, the weakest well-populated class. Applying them
selectively to specific weak classes, rather than globally, may still be worth
it even though the aggregate gain is nil.

---

## 29. Data augmentation: +1.2pp. Six levers now measured; the problem is data-limited

Augmentation differs from pseudo-labelling (section 28) in a way that should
matter: it manufactures HARD variations with GUARANTEED-correct labels (a
pitch-shifted kick is still a kick), where pseudo-labelling manufactures EASY
examples with uncertain ones.

576 files x 6 variants (original, pitch +/-1.5 semitones, time-stretch
0.92/1.09, -6dB) = 3,456 embeddings via the int8 Perch+CLAP stack.

| Training data | Accuracy |
|---------------|----------|
| originals only (504) | 74.0% |
| + augmented variants of training-fold files | **75.2%** (+1.2) |

**Methodology:** augmented copies of a test file are never placed in its
training fold. Without that constraint the model memorises pitch-shifted copies
of its own test set and reports a large fake gain.

### All six levers

| Lever | Gain | Section |
|-------|------|---------|
| Better encoders (5 tested) | +2.5pp for 2x weight | 20 |
| More features (stereo, harmonics, trajectory) | +0.0pp | 26 |
| Learned fusion over all signals | worse than hand rules | 18 |
| Classifier head (6 architectures) | +0.4pp | 27 |
| Pseudo-labelling | +1.0pp | 28 |
| Data augmentation | +1.2pp | this |

Every method-side intervention lands between 0 and +2pp. Six independent
results in that band is not bad luck; it is the signature of a **data-limited**
problem. At 504 labels across 9 classes -- roughly 56 examples per class -- no
architectural change substitutes for examples.

### What remains genuinely untried

- **LoRA / adapter fine-tuning.** Every result in this document uses FROZEN
  embeddings with a scikit-learn head. The encoder has never been trained. Full
  fine-tuning on 504 labels would overfit, but LoRA on the last blocks is
  designed for exactly this regime. This is the one unused PyTorch capability.
- **Audio LLMs** (Qwen2-Audio, Apache-2.0). Reasoning about audio rather than
  embedding it -- a different mechanism, not a sixth encoder. 7B params, so an
  offline enrichment pass, never in-plugin.
- **BEATs.** The only untested encoder with a real case (SOTA AudioSet mAP), but
  expected +1pp based on the other five, and its weights are not on HF.
- **Active learning.** Does not help today, but labelling the model's most
  uncertain files makes any FUTURE labelling roughly 3x more efficient per label.

---

## 30. Silero VAD as a vocal gate: 1.85 MB, zero false positives on drums

TTS itself is generation, not analysis -- wrong tool. But the adjacent speech
tech is right, and Silero VAD (MIT, **463K params / 1.85 MB**) is a near-free
high-precision vocal detector.

Fraction of clip flagged as speech, 40 files/class from keyword labels:

| Class | speech fraction | % flagged |
|-------|-----------------|-----------|
| Vocal Phrase | 0.356 | 50% |
| Vocal Loop | 0.117 | 25% |
| Bass One-Shot | 0.033 | 5% |
| Synth | 0.009 | 2% |
| Foley | 0.004 | 0% |
| **Kick / Snare / Hi-Hat / Clap / Percussion** | **0.000** | **0%** |

**Zero false positives across every drum class.** Recall is moderate, but the
keyword labels are themselves only ~72% accurate (section 13), so some files
labelled Vocal Phrase are not vocals -- the precision result is the solid one.

This is the right shape for a GATE rather than a classifier: when it fires,
believe it. At 1.85MB it is 0.9% of the 210MB Perch+CLAP stack.

Caveat: our by-ear labels are drum-only, so the vocal classes remain
unvalidated against ground truth. This measurement uses keyword labels and is
indicative, not conclusive.

### Key detection is a separate problem

Musical key from vocals is classical MIR -- chroma + Krumhansl-Schmuckler
profiles, or CREPE pitch tracking into a note histogram -- and unrelated to
TTS/ASR. The engine already carries a `key` field in the cache, so the
infrastructure exists.

---

## 31. Embedded metadata and folder context: both tested, both rejected

Two non-audio evidence sources never previously tried.

### Embedded WAV chunks -- contradicts a v2.0 plan claim

Chunk survey over 647 by-ear files: LIST 42.3%, smpl 17.3%, ID3 ~16%, bext
15.3%, acid 9.4%, inst 7.9%.

| Source | coverage | agrees with ear on loop/one-shot |
|--------|----------|----------------------------------|
| `acid` OneShot flag | 9.5% | 65.5% |
| `smpl` loop points | 17.9% | 55.3% |
| **duration + decay rule (section 23)** | **100%** | **96.4%** |

Of files that HAVE `smpl` loop points defined, only **12%** are actually loops
by ear -- tools write that chunk as sampler zone metadata irrespective of
musical looping.

**`SLO_AUDIO_CLASSIFICATION_MEGA_PLAN.md` claims embedded metadata "guarantees
99% loop detection precision". Measured: 55-65%, on under 18% coverage, versus
96.4% from two arithmetic features on 100% coverage.** Do not build on it.

### Folder homogeneity (sibling content, not folder name)

| | |
|---|---|
| median folder purity | 0.98 -- packs are genuinely well organised |
| files in a >=80% pure folder (n>=5) | 53% |
| sibling-majority agrees with ear | 75.6% (filename alone: 78.6%) |
| **files with NO filename evidence in a pure folder** | **8 of 99** |
| **sibling vote correct on those** | **12.5%** |

**Folder context fails precisely where it is needed.** Well-organised packs name
their files properly AND keep pure folders; the two are correlated. Files
lacking filename evidence sit in heterogeneous folders, which is *why* they lack
it. Sibling context therefore re-confirms easy files and cannot reach hard ones.

This is the same structure seen throughout: each additional signal explains the
same easy subset again. It is the strongest available evidence that the residual
errors are not addressable by adding evidence sources.

### Still untested
- **LoRA / adapter fine-tuning** -- the encoder has never been trained (see
  section 29).
- **True loop-point detection** (does the tail splice to the head?) and
  **bar-grid alignment** (is length an integer number of bars at the detected
  BPM?). These target the definition of a loop directly rather than by proxy.
- **Metric learning / few-shot** heads.

---

## 32. Meta (FAIR) encoders: licence-filtered, tested, rejected

Most Meta audio models one would want here are CC-BY-NC and unusable
commercially: **AudioMAE, ImageBind, MusicGen/AudioGen weights, MMS, Seamless**.
Permissive: **EnCodec (MIT)**, **HuBERT / wav2vec2 (Apache-2.0)**, **Demucs
(MIT)**. Only the permissive ones were tested.

576 by-ear files (note: the 649 quoted elsewhere in this doc is stale -- 603
labelled, 27 no longer on disk), 530 in classes with n>=15.

| features | accuracy |
|----------|----------|
| BASELINE Perch+CLAP | 73.0% |
| EnCodec alone (256-D) | 53.2% |
| HuBERT alone (1536-D) | 56.2% |
| wav2vec2 alone (1536-D) | 40.8% |

A single 5-fold split showed `Perch+CLAP+wav2vec2` at **+1.9pp**, which was
suspicious: wav2vec2 is the WEAKEST encoder alone yet appeared to add the most,
and +1.9pp on 530 files is ~10 files. **Repeated CV over 8 seeds shows it was
noise:**

| addition | true delta | sd | seeds where it helps |
|----------|-----------|----|----------------------|
| + wav2vec2 | **+0.24pp** | 0.42 | 5/8 |
| + HuBERT | **+0.26pp** | 0.74 | 4/8 |
| + EnCodec | **-0.54pp** | 0.78 | 1/8 |

All indistinguishable from zero. This is the same shape as the rejected
`Other/none` result (section 21) -- a single-split number that did not survive
resampling. **Single-split deltas under ~2pp on this corpus must not be believed
without repeated CV.**

Why they fail is unsurprising in hindsight: EnCodec optimises reconstruction,
not semantics, and its bottleneck discards exactly the perceptually-marginal
structure that distinguishes drum classes; HuBERT/wav2vec2 operate at 16 kHz,
which removes most of a hi-hat's identity.

## 33. The four missing axes: measured, and all four rejected

Four families describe a sound. Existing features covered two well (SPECTRUM,
ENVELOPE); MOTION was thin and PROVENANCE absent. `sound_axes.py` implements 28
features across the four gaps: inharmonicity (partial deviation from integer
multiples, tristimulus, odd/even balance, voiced fraction, comb salience), pitch
trajectory (f0 CONTOUR -- slope in semitones/sec, range, direction,
monotonicity), modulation spectrum (slow 0.3-2Hz / roughness 2-8Hz / flutter
8-30Hz), and provenance (spectral ceiling, noise floor, DC offset, clipping,
stereo correlation, mid/side, native rate, crest factor).

**Each group carries real information alone** (527 files, 10 classes, 17.8%
majority floor): provenance 45.5%, inharmonicity 37.2%, modulation 37.2%, pitch
trajectory 28.1%, all four together 56.7%.

**None of it is new information.**

| added to Perch+CLAP | delta |
|---------------------|-------|
| + inharmonicity | **+0.0pp** |
| + modulation | -0.2pp |
| + pitch trajectory | -0.8pp |
| + provenance | -0.9pp |
| + all four (28-D) | -0.4pp |

Per-class recall is unchanged to within 1pp on every one of the ten classes.

**The targeted hypothesis also failed.** Inharmonicity was proposed specifically
for the metal/cymbal group, not for general accuracy. Measured d-prime on the
confusions it was meant to fix: Crash vs Hi-Hat **-0.53**, Crash vs Snare -0.23,
Snare vs Clap -0.38. All below the 0.8 usable threshold. The one strong
separation found anywhere was `voiced_frac` on Kick vs Percussion (0.96), a pair
that was not a problem.

This was recorded in advance as the "best single bet". It was wrong -- the sixth
incorrect prediction in this project. The correct default is now explicit:
**assume a new feature adds nothing until repeated CV says otherwise.**

### What all of sections 31-33 establish together

Embedded metadata, folder context, three Meta encoders, and four new descriptive
axes have now each been measured and each added nothing. Every one of them
carries genuine information in isolation. Every one of them is redundant with
what Perch+CLAP already encodes.

The residual errors are not caused by a missing signal. Feature engineering,
encoder selection, and evidence fusion are exhausted as levers. What remains
untried is (a) **LoRA/adapter fine-tuning** -- the encoders have never been
trained, every result to date uses frozen embeddings, and (b) **more labels**,
which is the one input that has never been increased.

---

## 34. LoRA: closed. The first two results were both invalid controls

Three runs were needed because the first two measured a broken control.

**Run 1 reported "+12.2pp for LoRA". It was false.** The control (arm B, frozen
CLAP + trained head) scored 55.7% while arm A (the same frozen features under
sklearn) scored 67.2%. A control that loses to itself is broken.

**Run 2 (LayerNorm added) did not fix it** -- arm B only reached 58.2%. The
diagnosis was wrong.

**The actual cause: `requires_grad=False` is not `eval()`.** The CLAP audio
tower contains **54 Dropout layers and a BatchNorm2d**. Freezing stopped
gradients but left the module in train mode, so the "frozen" encoder emitted a
different embedding on every step and BatchNorm's running statistics were
silently overwritten. Measured on identical input:

| | max output difference |
|---|---|
| eval vs eval | 0.000000 |
| **train vs train** | **0.315953** |
| **eval vs train** | **1.781031** |

The head was fitting randomly corrupted features. Putting the backbone in
`eval()` restores determinism (0.000000) while LoRA parameters remain fully
trainable -- gradients flow through eval-mode modules.

### Corrected result (3 seeds x 5 folds)

| arm | accuracy | per seed |
|---|---|---|
| A frozen CLAP + sklearn probe | 67.2% | 67.9, 67.0, 66.8 |
| B frozen CLAP + trained head **(valid control)** | 70.5% | 70.8, 70.2, 70.6 |
| C LoRA CLAP + trained head | 72.1% | 72.5, 72.5, 71.3 |

**LoRA effect (C - B) = +1.57pp**, per-seed +1.7 / +2.3 / +0.8. **Fails the
+2.0pp gate and is not stable across seeds.**

Note also that most of the apparent gain over the published baseline (C - A =
+4.84pp) comes from the trained head and LayerNorm, **not from LoRA** -- exactly
what arm B exists to reveal.

Two lessons recorded:

1. A control that underperforms a simpler method is a broken control, not
   evidence for the treatment. Both invalid runs would have shipped a false
   positive without arm B.
2. **This was measured under random CV, which section 35 shows overstates
   unseen-collection accuracy by ~10pp.** Even the +1.57pp is measured on the
   wrong metric. Any future encoder fine-tuning must be judged under grouped
   evaluation.

**Route closed.** Not reopened without a materially different formulation.
