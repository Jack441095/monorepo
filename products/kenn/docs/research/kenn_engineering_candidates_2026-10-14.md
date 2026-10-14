# KENN engineering candidates, 2026-10-14

Research only. Nothing here is installed, wired in or committed. The six comparable repos were shallow-cloned into a scratchpad and read, never executed. Stars, licences and release dates were pulled from the GitHub and PyPI APIs on 2026-10-14. Anything I could not check is marked **inferred** or **unverified**.

Licence rule applied throughout is `THIRD_PARTY_LICENCES.md`: KENN ships closed, so MIT, BSD, ISC, Apache-2.0 only (MPL-2.0 for test-only tooling). GPL, AGPL, LGPL, BSL, PolyForm and non-commercial code or weights are a problem.

Effort: S is under two days, M is up to a week, L is more than a week. Effort figures are my estimates, not measurements.

## 1. What KENN already has (so we do not re-buy it)

Read from the tree, not assumed:

- `packages/mix-review/core/local_engine.py`: numpy K-filter LUFS and LRA, numpy true peak, an optional pyloudnorm path, Pearson correlation, mono-sum drop, correlation timeline, 7-band and 40-log-band spectra, clip runs.
- `packages/mix-review/core/reference_matching.py`: `BANDS_7`, `compare_mix_to_reference`, dynamics and stereo comparison, EQ8 export.
- `packages/mix-review/core/masking_analysis.py` and `apps/backend/src/kenn/core/mix_doctor.py` (its five 20-point dimensions are being reworked; a missing meter now stays missing and the grade is UNRATED).
- E1 100 ms windows are done. E2 (the grade) exists only as a proposal in `e2_grade_proposal_2026-10-14.md`: 30 technical health, 30 declared target, 40 reference match; a part with no evidence is not scored and is shown as "42 of 60, no reference supplied", never rescaled.

So the useful gaps are: proof that our meters are right (conformance), a rule table for the grade with a cited source per deduction, better reference-match statistics, and evidence-grounded wording. Not another loudness library.

## 2. Comparable repos

All six read from their own source. "Verified" below means I read the code or file named.

### 2.1 track-coach (happysasha18/track-coach, MIT, 1 star)

The most useful of the six. It is a Claude Code skill, librosa plus Demucs, local HTML report.

What it computes (verified in `scripts/analyze_core.py`, `scripts/masking.py`, `scripts/validity.py`):

- Per-track features at 44.1 kHz (`SR = 44100` in `_common.py`): spectral balance, energy/brightness/density trends (Pearson r across the track), endpoint cosine between start and end spectra, local variance, modulation-rate drift.
- Per-stem masking using a 12 dB rule. That number is theirs, not a standard; their own docs say so.
- A reference-free tonal-bump detector that compares each band to its neighbours instead of to a target curve.

How it grounds advice (verified):

- Three tiers: Tier A is one signal, Tier B a fusion of signals, Tier C a per-stem result. Each recommendation card carries a plain "where this came from" line naming the signal or the combination (`build_widget.py`, the card-evidence map).
- `references/interpretation.md` is a lookup of "typical, not diagnostic" meanings per metric range, and the output rule is Measured, then What this typically means, then Up to you. No directives.
- A significance gate (`significant_stems`) so numbers from silent or near-silent stems are never shown. `validity.py` states the rule as "valid or doesn't exist": an invalid metric is withheld, not shown with a caveat.
- Mechanical gates on its own output: a traceability test that checks every spec invariant has a test row, and a shipped-language lint. Both are process ideas, not features.

Worth borrowing: evidence tiers, the significance gate, the validity rule, the neighbour-based bump detector, interpretation bands as data. Licence is MIT so code could be adapted with the notice kept, but the ideas are small enough to reimplement.

Weak spots: 1 star, one author, true-peak card text exists but I did not verify the true-peak maths itself; thresholds are their own. Do not copy numbers.

### 2.2 mixbot-ai-mixing-assistant (bginigeme, 0 stars, NO LICENCE FILE)

The existing comparable-products doc says MIT. I checked the repo and found no licence file, so no licence is granted. Treat as all rights reserved. Ideas only.

Verified from `audio_analyzer.py`, `audio_tools.py`, `ai_agent.py`:

- The genre argument is accepted and then ignored in the analysis.
- Loudness is RMS, not BS.1770 LUFS.
- Advice is generic canned text keyed on thresholds.

An anti-pattern list: a genre switch that changes nothing, RMS labelled as loudness, advice that does not cite a measurement.

### 2.3 ableton-mentor-mcp (RiotTheMan, MIT, 0 stars)

Verified from `MCP_Server/psycho_features.py`, `server.py`, `loopback.py`, `render_pipeline.py`:

- It collapses to mono before computing LUFS. BS.1770 sums per-channel power, so a mono mixdown gives a different number for any wide mix.
- The value labelled "true peak" is a sample peak. No oversampling.
- Per-track capture works by soloing each track in Live and recording through a loopback device (BlackHole, which is GPL). That mutates the user's session and is slow.

Worth borrowing: nothing in the code. Useful as a reminder of what not to do, and the psychoacoustic feature list is a reading list only.

### 2.4 ableton-tools (madisonrickert, 16 stars)

Verified from `skills/stem-verify/SKILL.md` and `engine/src/analysis.py`. The tool emits numbers plus threshold bands, and the model states the verdict. That split keeps arithmetic out of the LLM, which is where KENN already is. Worth borrowing: the threshold-band-in-payload shape (see top-5 item 2). I did not check its licence file separately; the existing doc lists it, so treat the licence as unverified until you read the file.

### 2.5 ableton-for-ai (peterkolbe, MIT, 1 star)

Verified from README and `audio_processor.py`. Its JSON is self-describing: the payload carries a `legend` explaining each field and unit. Cheap to copy as a pattern and it helps a small local model avoid misreading a field. Spectrogram images are produced for the model; KENN's local model is text-only so that part does not apply.

### 2.6 producer-pal (adamjmurray, 328 stars, GPL-3.0-or-later)

Licence read from its LICENSE file (the API said NOASSERTION). GPL-3 means we cannot copy or link code. It is a Live control surface (MCP plus REST), not an analyser, so it overlaps E-section device control more than mix analysis. Ideas only, and keep reading it out of the implementation path.

## 3. Library and technique candidates

Columns per candidate follow the brief. Size and offline fit: all of these run locally unless noted.

### 3.1 Loudness and true peak

**EBU Tech 3341 / 3342 loudness test set (conformance vectors)**
- URL: https://tech.ebu.ch (EBU loudness test set, v5.0). I could not fetch the EBU page directly (403) and the exact download URL is **unverified**; v5.0 came from a web search.
- Licence: EBU publishes it for free use as a test set; the exact terms are **unverified**. We would run it in tests, not ship it.
- Maturity: the EBU standard test material, stable.
- Serves: E2 (technical health) and E9, as the proof our LUFS, LRA and true peak match the spec.
- Build: a test module that runs each vector through `local_engine.py` and asserts the published tolerances. Gaps become bugs to fix before the grade uses those numbers.
- Effort S. Risk low. Highest value per hour on this list because the grade will quote these meters.

**pyloudnorm** (csteinmetz1/pyloudnorm), MIT, 783 stars, 0.2.0 released 2026-01-04, last push 2026-01-04.
- Pure Python on numpy and scipy. Already an optional path in `local_engine.py`.
- Serves: cross-check for LUFS and LRA during conformance, not a new runtime dependency.
- Risk: its true-peak and 4x oversampling are not what we want for TP. Use it as a second opinion on integrated LUFS only.

**libebur128** (jiixyj/libebur128), MIT, 491 stars, last push 2023-06-25.
- The C reference many tools wrap. Verified licence from the repo.
- Python wrapper **pyebur128** (jodhus), MIT, 5 stars, 0.1.1 from 2024-09-07. No macOS arm64 wheel for Python 3.13 (wheels stop at cp312; local Python is 3.13.7), so it needs a source build with a git submodule.
- Verdict: use libebur128 only as a test oracle if we want a second implementation. Not a runtime dependency. Effort M, risk medium (build friction, tiny maintainer base).

**8x FIR true-peak upsampling**
- Our current 4x fails 28 of 98 tones in the JUCE true-peak accuracy set; a JUCE 8x FIR passes all 98 (measured earlier in this project's research, see `audio_analysis_reuse_2026-10-14.md`).
- Serves: E2 and E9 true-peak deduction. Build a numpy polyphase 8x upsampler with a documented filter, keep `local_engine.py`'s interface. Effort M, risk low. The grade will punish a track at the -1 dBTP line, so an under-read there is a visible error.
- Do not use soxr for this; see 3.5.

**Targets to cite in the rule table**
- Spotify: -14 LUFS, true peak -1 dBTP (-2 dBTP if the master is louder than -14 LUFS). From Spotify's published guidance; I did not re-fetch it today, so treat as **inferred from earlier reading**.
- AES TD1008: music no louder than -16 LUFS. Its -1 dBTP figure is **unconfirmed**.
- PLR (peak to loudness ratio): standard definition, true peak minus integrated LUFS in dB. **Inferred**; no single standards body number to cite for "good PLR".

### 3.2 Spectral balance, tonal balance, reference matching

**Distribution-based tolerance (Wilson and Fazenda, JAES 2016)**
- Paper, not code. Describes a mix as a point in feature space (PCA axes read as amplitude, brightness, bass, width) and judges by z-score against a collection of mixes, not against one target curve. Details from memory of the abstract; read the paper before citing numbers. **Partly inferred.**
- Serves: `reference_matching.py` and the 40-point reference-match part of E2.
- Build: when the user supplies several references (or we ship a small genre set we are licensed to ship), compute mean and spread per band and score distance in standard deviations. Single-reference mode stays as today. Effort M, risk medium: a genre set needs data we can legally ship (see 3.6).

**Neighbour-based bump detector (track-coach idea)**
- Reference-free: flag a band that sticks up relative to its neighbours on the 40-log-band spectrum.
- Serves: mix_doctor, and E2's technical-health part when no reference exists, which is the "42 of 60" case.
- Effort S to M. Risk: needs tuning per band count; we set thresholds from our own corpus and say so, as track-coach does.

**Matchering** (sergree/matchering), **GPL-3.0**, 2658 stars, 2.0.6 from 2022-10-19, last push 2026-10-07.
- Reference-matching mastering (RMS, FR, peak, width). Good algorithm, wrong licence. **Problem: GPL.** Read the idea (match FR by smoothed per-bin gain, then limit) and write our own; do not link or copy.
- We already have 7-band matching and EQ8 export, which is the better fit for KENN since it advises and does not render audio.

### 3.3 Stereo and phase

Nothing to install. We already have correlation, mono-sum drop and a correlation timeline. Gaps worth closing with our own code:

- Mid/side energy ratio per band, so "wide above 4 kHz, mono below 150 Hz" can be stated as measured. Effort S, risk low, serves E2 and mix_doctor.
- Band-limited correlation (below and above 150 Hz). Effort S. Mono compatibility matters for bass; a full-band number hides a bass that cancels.
- All **standard definitions, inferred**; no library needed.

### 3.4 Key, tempo, onset

**librosa** (librosa/librosa), **ISC**, 8678 stars, 1.0.0 released 2026-08-11, last push 2026-10-06.
- Headline licence is fine. **Trap:** it hard-depends on **soxr**, which PyPI lists as **LGPL-2.1-or-later** (soxr 1.1.0, 2026-05-03). Under our policy LGPL is excluded. Dynamic linking of an LGPL library may be legally acceptable in a bundled app, but that is a legal call, not an engineering one, and `THIRD_PARTY_LICENCES.md` says no. I did not check whether KENN's packaging currently bundles soxr. That check is the first step before anyone adds librosa.
- Serves: tempo, onset, key (via chroma) if we ever want them. Today none of E1-E11 needs them beyond what Live already reports (project tempo).
- Verdict: do not add. If we want onset or tempo from audio, write onset strength with numpy (spectral flux) and take tempo from Live.

**beat_this** (CPJKU), MIT, 421 stars, 1.1.0 from 2026-04-14. Needs torch, and depends on soxr like librosa. Avoid for the same reason plus size.

**Essentia** (MTG/essentia), **AGPL-3.0**, 3772 stars, still active (pushed 2026-10-14). **Problem: AGPL.** Not usable. The only route is a commercial licence from MTG, which is a business decision.

**aubio**, **GPL-3.0**, 3770 stars, 0.4.9 from 2019-02-08, so unmaintained. Avoid.

**madmom**, GitHub shows NOASSERTION; PyPI says "BSD, CC BY-NC-SA" (0.16.1, 2018-11-14). The code is BSD but the trained models are non-commercial. Unmaintained since 2018. Avoid.

### 3.5 Source separation

**Demucs** (adefossez/demucs), MIT, 3344 stars, 4.1.0 from 2026-07-11, last push 2026-08-31. The original facebookresearch repo is archived (last push 2024-04-24); the adefossez fork carries on.
- Code licence is MIT. **Weights: no separate licence statement found, and the training data includes MUSDB, which I believe is non-commercial (unverified).** Needs legal review before shipping weights.

**demucs-mlx** (ssmall256), MIT, 44 stars, 1.6.1 from 2026-10-05.
- Runs on MLX, which KENN already uses (mlx, mlx-lm), so no torch. About 160 MB of weights, offline via an environment variable. The author reports 114x realtime on an M4 Max; that is **author-reported, not measured by us**. It also keeps a large GPU cache, so check memory next to the local model before trusting it on a 16 GB machine.
- Serves: Tier C per-part advice (kick versus bass masking on a stereo mix) when no stems exist. Live stems are better when the user can export them, so this is for the case of a bounced mix.
- Effort L (weights review, memory budget, a validity gate that says "separation unreliable" when stems leak). Risk high: separation artefacts feed measurements, and the significance gate from track-coach is required.

**python-audio-separator** (nomadkaraoke), MIT code, 1416 stars, 0.47.0 from 2026-08-27. It downloads many third-party models with mixed or unverified licences. **Unverified. Avoid.**

### 3.6 Datasets and research for mix metrics

- **MUSDB18, MedleyDB**: I believe both are non-commercial, so useful for internal evaluation only and not for shipping a derived model or reference curves. **Unverified.**
- **Mix Evaluation Dataset** (Zenodo) and **MixAssist** (a dialogue dataset on mixing advice): licences **not verified**. Zenodo's API returned 403 and I did not read the licence pages. Use MixAssist as a design reference for how engineers phrase advice; do not train on it until the licence is read.
- **Pestana tonal-balance slope values**: I recall a spectral slope range from the literature but did not verify the numbers. Do not put them in the rule table until sourced.
- Practical point: a genre tolerance set we can legally ship has to come from our own corpus (owner audio is kept outside this repo and is data, not source) or from a dataset whose licence permits it.

### 3.7 Explaining mix problems from measurements

No library does this well. What exists is a pattern:

- A rule table: measurement, threshold, source, wording. Each deduction in E2 names its row. Same inputs always give the same grade.
- Evidence tiers (track-coach) so a Tier A claim and a Tier C claim are worded differently.
- A self-describing payload (ableton-for-ai) so the model sees units and legends.
- Interpretation bands as data (track-coach `interpretation.md`) so the model states "typical, not diagnostic" from a file, not from its own memory.

Effort M for the table plus tests. Risk: thresholds are opinions. Each row must say whether it is a standard, our corpus, or a judgement call.

## 4. Flagged licence problems

| Item | Licence | Why it matters |
|---|---|---|
| librosa, beat_this | ISC / MIT, but need soxr | soxr is LGPL-2.1-or-later; policy excludes LGPL |
| Matchering | GPL-3.0 | cannot link or copy |
| Essentia | AGPL-3.0 | cannot use without a commercial licence |
| aubio | GPL-3.0 | cannot link; also unmaintained since 2019 |
| pedalboard (Spotify) | GPL-3.0 | cannot link, even though popular |
| madmom | BSD code, CC BY-NC-SA models | non-commercial models |
| mixbot-ai-mixing-assistant | none | no licence file, so no rights granted (existing doc says MIT; that is wrong) |
| producer-pal | GPL-3.0-or-later | ideas only |
| BlackHole (used by mentor) | GPL | cannot bundle; method is also slow and mutates the session |
| Demucs weights, MUSDB | not stated / believed NC | legal review before shipping |

## 5. Verified versus inferred

Verified directly: the licences, star counts and release dates in section 3 (GitHub and PyPI APIs, 2026-10-14); LICENSE files for producer-pal; the code behaviour described for each comparable repo; what `local_engine.py`, `reference_matching.py`, `mix_doctor.py` and `masking_analysis.py` already contain.

Not verified: EBU download URL and terms; BS.1770-5 changes; TD1008 true-peak figure; MUSDB18, MedleyDB, Mix Evaluation Dataset, MixAssist and Demucs-weights licences; python-audio-separator model licences; Pestana slope numbers; Spotify targets (recalled, not re-fetched); Demucs-MLX speed and memory; whether KENN packaging bundles soxr.

## 6. Ranked shortlist: what to implement first

1. **EBU Tech 3341/3342 conformance tests for LUFS, LRA and true peak (S).** The E2 grade will quote these meters and deduct points on them. If a meter is wrong, every grade built on it is wrong in a way users can check against other tools. Cheap, no new dependency, finds bugs before the grade ships. Pair it with the 8x FIR true-peak fix (M), since the current 4x fails 28 of 98 tones.
2. **E2 rule table with a cited source and tier per deduction, thresholds carried in the payload as bands, with a legend (M).** This is the proposal's own requirement (every deduction names its source) and it is the pattern the two best comparables use (track-coach tiers, ableton-tools bands, ableton-for-ai legend). Rows say standard, corpus or judgement.
3. **Reference-free tonal-bump detector, then distribution tolerance for reference matching (S to M).** The bump detector fills the "no reference supplied" case with real evidence. The tolerance-bound approach from the literature replaces a single target curve with a spread, which fits a tool that advises and does not render.
4. **Stem and part significance gate, plus a validity rule (S).** Build it before any per-part feature: a metric from a silent or near-silent source is withheld, not shown with a caveat. It also protects item 5.
5. **Optional offline stem separation with demucs-mlx behind legal review of the weights (L).** Last because of weights licence, memory next to the local model, and artefact risk. Worth it only for bounced mixes with no stems, to give Tier C per-part advice.

## 7. Avoid list

- Matchering, Essentia, aubio, pedalboard, BlackHole: GPL or AGPL.
- librosa and beat_this until the soxr question is settled by a licence decision; write numpy onset code if we need it.
- madmom: non-commercial models, unmaintained.
- python-audio-separator: unverified third-party model licences.
- mixbot code (no licence) and producer-pal code (GPL): ideas only.
- Mentor's approach: mono-collapse before LUFS, sample peak called true peak, solo-and-record capture.
- pyebur128 as a runtime dependency: no arm64 wheel for Python 3.13, 5 stars. Test oracle at most.
- Anyone's threshold numbers copied across (track-coach's 12 dB masking rule included): they are their own choices, not standards.
