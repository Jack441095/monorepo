# Lane 05 — Mix analysis and grading engine (E1–E5, E9–E10, B1)

**Date:** 2026-10-15 · **Platform target:** Apple M3, 16 GB RAM, macOS · **Product constraint:** KENN ships closed-source → code AND weights must be MIT / BSD / ISC / Apache-2.0 (MPL-2.0 test-only). GPL/AGPL/LGPL/BSL/PolyForm/CC-NC/unclear = problem. No dependency additions — every candidate below is a proposal for owner approval.

**Scope:** the measure → grounded grade → actionable help → explanation chain. This lane extends, and does not repeat, the [14 Oct reuse screen](audio_analysis_reuse_2026-10-14.md) (libebur128, r8brain, JUCE 8x receipts), the [E2 grade note](e2_grade_proposal_2026-10-14.md) (30/30/40 weights), [lane 03](03-audio-understanding.md) KQ7 (mix-scoring models), [lane 04](04-teaching-patterns.md) §1–§2 (MixAssist, MED, citable conventions), and KENN_PLAN items E1–E5, E9, E10 and B1. KENN already owns the relevant native kernels: C++ K-weighting / gated LUFS / LRA / 4x true-peak candidate, Hann FFT + 40-band LTAS (Accelerate/vDSP on macOS), 7-band stem masking, bulk correlation/statistics, and an AutoMix kernel set (`tooling/native/dsp_core/`, `plugins/kenn-vst3-au/Source/`).

**Method:** every claim checked against the primary PDF/repo/API on 2026-10-15. Status legend: **[V]** verified this run with URL + date · **[R]** reproduced from a previous run's log, not re-fetched · **[I]** inferred · **[?]** could not verify.

**Headline claims:**

1. No new licence-clean measurement library has appeared since the 14 Oct screen that beats extending KENN's own C++ kernels. libebur128 is still at v1.2.6 (tag commit 2021-02-14, repo last push 2023-06-25); it stays a **test-side comparator only** (§1).
2. The official conformance material KENN_PLAN marked "download URL unverified" is now located: EBU Tech 3341-2023 states its minimum-requirement test signals are downloadable from **http://tech.ebu.ch/loudness**, synthesised at 48 kHz; ITU Report **BS.2217-2 (10/2016)** is a free PDF table of 29 compliance files with expected loudness values at **±0.1 LKFS**; **ITU-R BS.1770-5 (11/2023)** is the current algorithm version (§1).
3. Current standards revisions move the citable line: **EBU R128-2023** (Nov 2023) is the current publication (lane 04 cited "rev 3 (2020)"), **Tech 3342-2023 V4** is the current LRA document, and BS.1770-5 adds Annexes 3–4 (advanced-sound and object-based loudness) beyond the stereo loudness Annex 1 KENN implements (§1, §3).
4. The only mature open tool for reference mastering/matching, **matchering, is GPL-3.0** — the reference-match / EQ-match space has **no licence-clean library to adopt**; `reference_matching.py` already does 7-band balance + EQ Eight preset generation in-house and is the right base to extend (§2).
5. The only clean full-reference perceptual metric found, **ViSQOL (Apache-2.0)**, is validated on codec degradation at 48 kHz, not on artistic mix differences → research-only, not a grade input (§2).
6. **MUSDB18 and MUSDB18-HQ are non-commercial on Zenodo** (`other-nc`, verbatim below). This closes the dataset end of the chain-of-title question for every "MIT" checkpoint trained on MUSDB: the caveat is now quotable, though the legal status of trained weights remains an owner/legal call (§3).
7. MixAssist status re-verified at source: paper **CC BY 4.0**, code repo **MIT**, both Zenodo records **cc-by-4.0**, both HuggingFace copies **no licence** — use the Zenodo files for phrasing work, never the Hub copies (§3).
8. Teaching figures need **no new dependency**: the frontend already draws waveform/timeline/band/radar charts on canvas (`MixReviewWaveform.vue`, `MixReviewTimeline.vue`, `MixReviewBandChart.vue`, `MaskingRadar.vue`); a spectrogram image is an extension of that pattern from existing C++ FFT data. wavesurfer.js (BSD-3-Clause) is the fallback only if interactive playback-linked figures are wanted (§1, §4).
9. Two genuinely new MIT candidates are worth a bounded benchmark: **sz_meters** (C++, BS.1770-4 gating + inter-sample true peak + AES17 RMS/crest/correlation, 2026-09) and **AudioCommons timbral_models** (Apache-2.0, eight interpretable timbre attributes) for the teaching layer (§1, §3, §4).
10. No open dataset pairs acceptable ranges with explanations, and no open standard defines a "mix grade". E9 reliability must come from KENN's own held-out listener set; the six MED CC BY songs are the only clean external listening material (§3, §4).

## §1 Q1 — Measurement and standards tooling since the 14 Oct screen

### 1.1 Standards refresh (citable documents, read from the primary PDFs this run)

| Document | Current version / date | What KENN gets from it |
|---|---|---|
| ITU-R BS.1770-5 | **(11/2023)**, in force; BS.1770-4 (10/2015) superseded [V](https://www.itu.int/rec/R-REC-BS.1770/en) | Algorithms: Annex 1 loudness (mono/stereo/3/2 — what KENN measures), Annex 2 true-peak guidelines, **Annex 3 larger channel configurations, Annex 4 object-based** (new in -5). Scope text read from the PDF this run [V](https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1770-5-202311-I!!PDF-E.pdf) |
| EBU R128-2023 | **November 2023** ("EBU R 128-2023") [V](https://tech.ebu.ch/docs/r/r128.pdf) | Citable target, verbatim: *"the Programme Loudness Level shall be normalised to a Target Level of −23.0 LUFS. Where attaining the Target Level is not achievable practically (for example, live programmes), a tolerance of ±1.0 LU is permitted"*. The −1 dBTP ceiling quote stays Tech 3343 (lane 04 [R]) |
| EBU Tech 3341-2023 | **V4, November 2023** — *"V4; editorial and formatting changes"* [V](https://tech.ebu.ch/docs/tech/tech3341.pdf) | "EBU Mode" meter spec: live-meter update **"shall be at least 1 Hz"**; KENN's 10 Hz cadence clears this with margin. True-peak tolerance table + official test-signal pointer (§1.2). Covers EBU Mode only — not advanced formats |
| EBU Tech 3342-2023 | **V4, November 2023** — *"V4; Editorial and formatting changes"*; V3 (Jan 2016) fixed the −10 LU relative gate and ≥10 Hz calculation frequency [V](https://tech.ebu.ch/docs/tech/tech3342.pdf) | Loudness Range (LRA) definition — the citable dynamic-range measure KENN's kernel already computes but does not yet conformance-test |
| EBU Tech 3343-2023 | November 2023 [R: downloaded this run, quotes from lane 04] | Production guidelines: −1 dBTP ceiling, ±0.2 LU production tolerance [R lane 04] |
| EBU Tech 3344 | **V2.1, July 2016** [V](https://tech.ebu.ch/docs/tech/tech3344.pdf) | Distribution/reproduction guidance; mentions −1 dBTP and codec handling. Older than R128-2023 — cite with its 2016 date |
| AES TD1006 / TD1008, Spotify target | [R lane 04 — not re-read this run] | Broadcast and streaming loudness targets used by the declared-target part |

### 1.2 Official conformance material — the 14 Oct "unverified URL" is now pinned

- **EBU Tech 3341-2023, reference [7], verbatim:** *"tech.ebu.ch 'Minimum requirements test signals for 'EBU Mode' loudness meters', available from the EBU at http://tech.ebu.ch/loudness"* and *"These 'minimum requirements test signals' are available for download from the EBU Technical website [7], synthesized at a sampling rate of 48 kHz."* [V PDF]. The live page itself returned HTTP 403 behind Cloudflare to both urllib and curl this run (`Just a moment...`) — **reachability unverified [?]**, but the official pointer is now citable.
- **ITU Report BS.2217-2 (10/2016)** — *"Compliance material for Recommendation ITU-R BS.1770"* — free ITU PDF, 9 pages, **29 test files** with file-based and live expected values, **tolerance ±0.1 LKFS**, *"All the files are 16-bit PCM wav-files at a sampling rate of 48 kHz."* Includes relative-gate test (−10.0 LKFS expected; ~−8.0 LKFS if the −8 LU gate is used), absolute-gate test (−69.5 LKFS; −73 LKFS without an absolute gate), tone sweeps at −24/−23 LKFS across 25 Hz–10 kHz, a −18 LKFS frequency sweep, and 6-channel summing/channel checks with LFE = −inf. [V](https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-BS.2217-2-2016-PDF-E.pdf); BS.2217-1 (06/2012) is the same table for BS.1770-3 [V](https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-BS.2217-1-2012-PDF-E.pdf).
- Caveats: the report *describes* the test files but does not itself embed audio (the `.wav` hosting is unverified [?]); the table targets BS.1770-2/-3 era — advanced-format Annexes 3–4 of BS.1770-5 have no equivalent compliance set found [?]; the terms of the EBU signal files (distribution vs test-use) are not stated in Tech 3341 [?].

### 1.3 Gap-by-gap verdict against the existing C++ kernels

| Gap named in the brief | What exists today | Best available option | Verdict |
|---|---|---|---|
| Streaming LUFS variants (M/S/I, LRA, gating) | C++ candidate: K-weighting, ungated 400 ms/3 s energy, gated integrated with −70/−10 LU gates and fixed 1600-bucket histogram; passes Tech 3341 cases 1–5 at 44.1/48/96 kHz, 881 checks [R plan receipt]. Known gaps: case 13 momentary grid (up to 0.46 LU low on a 400 ms tone starting off the 100 ms grid), LRA conformance, 5.0-channel cases | libebur128 v1.2.6 (MIT) remains the independent comparator; no newer release exists (latest tag v1.2.6, commit 2021-02-14; repo last push 2023-06-25 [V API]). **sz_meters** (MIT, C++) is a new second comparator with its own gating + true peak | **Extend own kernel** (hop fix, LRA conformance); comparators test-side only — libebur128's 3 s double ring + scratch is ~5.53 MB per stereo state at 96 kHz [R 14 Oct], which does not fit the live 64-insert picture |
| Dynamic range / PLR | LRA computed by the C++ kernel [R dsp_core README]; crest factor in the realtime core; no PLR readout | Citable: **LRA = EBU Tech 3342-2023**. PLR (true peak − integrated LUFS) has **no open standard** — TT/DR is a Pleasurize Foundation convention with tiny MIT implementations (alleato-llc/dr, Rust, 0★) — reference only | **Derive in-house**: PLR is one subtraction over meters KENN owns; label it a house rule with its formula. Add Tech 3342 conformance for LRA |
| Phase / width | Bulk correlation kernels, width/side-mid in the realtime core and mix review | Nothing worth adopting: a goniometer is a trivial Lissajous render of existing L/R; correlation sign is the only published part (lane 04 §2: 3 of 16 mix_doctor deductions have a published basis) | **Extend own kernels** (display-level) — no library |
| Spectrogram / teaching figures | Frontend canvas charts exist (waveform, timeline, band chart, masking radar); backend has C++ FFT magnitudes + 40-band LTAS | **wavesurfer.js** (BSD-3-Clause, 10.4k★, pushed 2026-10-13 [V API]) ships official `spectrogram.ts`/`spectrogram-worker.ts` plugins [V repo tree]. matplotlib is PSF-style permissive but **off the strict allowlist** and not installed [V] | **Extend existing Vue canvas components** from C++ FFT data (no new dep); wavesurfer.js only if interactive playback-linked figures are wanted; matplotlib only if server-side PNG figures are wanted (owner decision, off-list licence) |

### 1.4 Library candidate re-check (licence first; activity from GitHub API, 2026-10-15)

| Candidate | Licence | Activity | Notes |
|---|---|---|---|
| libebur128 | MIT [V API] | latest tag v1.2.6 = commit 2021-02-14; last push 2023-06-25 → **quiet** | Unchanged since the 14 Oct screen |
| r8brain-free-src | MIT [V API] | latest tag version-6.5 = commit 2023-12-07; repo last push 2026-09-30 → active | Standby resampler only if the JUCE 8x accuracy/cost gate fails |
| sz_meters (StudioZIO) | **MIT** (LICENSE text read: "MIT License / Copyright (c) 2026 StudioZIO") [V] | new: pushed 2026-09-09, 2★ | C++, *"The DSP depends on nothing but the C++ standard library"*; BS.1770-4 loudness with gating, inter-sample true peak, AES17 RMS, crest factor, correlation; JUCE optional module wrapper [V README] |
| metermaid | MIT [V API] | pushed 2026-10-07, 19★ | Rust/Tauri desktop meter app (BS.1770/R128 + spectrum) — spot-check tool for human ears, not a shippable dependency |
| alleato-llc/dr | MIT [V API] | pushed 2026-02-15, 0★ | Rust CLI implementing the Pleasurize/TT DR algorithm — read-only reference for the DR definition |
| lufsly / lufsly-extension | MIT [V API] | 2026-07, 1★ | Browser LUFS/TP/DR apps — no need for KENN |
| Grisey | GPL-3.0 [V API] | 65★, 2026-09 | Metering plugin — **avoid** |
| audiojs/loudness | NOASSERTION [V API] | 3★, 2026-09 | BS.1770-4 JS atoms — licence unclear, no dependency |
| producer-player | NOASSERTION [V API] | 24★, 2026-09 | Mastering analysis app, licence file unrecognised — pattern reading only |

## §2 Q2 — Reference comparison and matching

### 2.1 The matchering question, answered

**matchering (sergree/matchering, 2.7k★, pushed 2026-10-07) is GPL-3.0.** The raw LICENSE file begins *"GNU GENERAL PUBLIC LICENSE / Version 3, 29 June 2007"* [V]; GitHub API agrees [V]. Forks (including `matchering-cli` variants) are derivative works and stay GPL [I]. Its README states the capability precisely, and that statement is the useful part:

> *"Our algorithm matches both of these tracks and provides you the mastered TARGET track with the same [RMS], [FR], [peak amplitude] and [stereo width] as the REFERENCE track has."* [V README]

That four-axis match (RMS/loudness, frequency response, peak, stereo width) is a reasonable checklist to hold KENN's own reference-match part against — but no matchering code, weights or container may be adopted.

### 2.2 What is adoptable

| Candidate | What it is | Licence | Fit for KENN | Verdict |
|---|---|---|---|---|
| **ViSQOL** (google/visqol) | Full-reference perceptual similarity metric; audio mode needs **48 kHz**, outputs MOS-LQO (max ≈4.75), SVR mapping, recommends 3–10 s of active audio; trained on codec degradation ≥24 kbps [V README] | **Apache-2.0** [V README + API] | Clean licence but wrong domain: it scores *degradation* between a reference and a degraded copy, not artistic divergence between two good mixes. Bazel build [V README]; no Mac numbers [I] | **WATCH / research only.** Optional E9 experiment, never a grade input |
| **AutoEq** (jaakkopasanen) | Headphone frequency-response matching against target curves; `frequency_response.py` does smoothing, normalization, error and EQ-parameter derivation [V README/API] | **MIT** [V API] | Headphone domain, but it is the cleanest permissively licensed reference implementation of "measure FR delta → propose filter gains"; useful as a *math reference* for EQ-match suggestions | **Reference only.** Do not add as a dependency |
| FFTBalance (juzzlin) | CLI that matches the spectrum of an input file to a reference file [V README] | MIT repo [V API], **but** requires FFTW3 (GPL, below) + libsndfile (LGPL-2.1) | Experimental, 3★, dependency chain poisons it | **Avoid bundling.** See avoid list |
| jhtonyKoo/music_mixing_style_transfer | Reference→target mixing-style transfer (FX encoder + cloner) [V README] | MIT code [V API]; **weights on Google Drive, no licence**; *"Trained with MUSDB18"* [V README] | MUSDB18 is non-commercial (§3); weights unstated; repo stale since 2023-10 | **Avoid weights. Pattern reading only** (its FX-parameter embedding idea overlaps KENN's automix lane, not grading) |
| sai-soum/Diff-MST | Differentiable mixing console, reference-song style transfer [V] | **CC BY-NC-SA 4.0** (LICENSE first line, quoted in avoid list) | Non-commercial → cannot ship or train into the product | **Blocked** |
| KENN in-house: `reference_matching.py` | 7-band energy fractions, EQ-match gains → EQ Eight `.adv` preset, dynamics + stereo profiles, `score_reference_match` out of 40 (tonal 20, dynamics 10, low-end mono 5, width 5) [V local source] | Own code | Already the correct base for E2/E10/B4; 40-band LTAS exists natively and can replace the 7-band path where the doc notes "uploaded spectral health is unscored because the analyser's 7 bands differ from the Doctor's bands" [R plan] | **Extend in-house** |
| Loudness-matched A/B | B4 requires *"authorized files, corresponding sections and matched playback loudness"* [R plan] | — | Compute the matched gain from KENN's own LUFS meters; no library arises | **Build from existing meters** |

### 2.3 Net for Q2

There is no clean, mature reference-matching library. The strategy is: keep `reference_matching.py` as the scorer, feed it the native 40-band LTAS, add loudness-matched A/B gain from existing meters, and borrow only *algorithm documentation* (matchering's four axes; AutoEq's gain derivation). ViSQOL is the single clean candidate for a bounded research evaluation, with the domain caveat stated up front.

## §3 Q3 — Critique, grading sources and dataset licences

### 3.1 MixAssist — re-verified at source this run

| Artifact | Licence | Evidence |
|---|---|---|
| Paper (arXiv 2507.06329, COLM 2025) | **CC BY 4.0** [R lane 04, arXiv licence line] | Phrasing reference; quote with attribution |
| Code (github.com/mclemcrew/MixAssist) | **MIT** [V API: licence=MIT, 19★, pushed 2026-07-24] | Re-verified today; matches lane 04 |
| Raw data, Zenodo 15571750 (2025-06-02) and 15848443 (2025-07) | **cc-by-4.0 both** [V Zenodo API 2026-10-15] | Use these copies; attribution required |
| HuggingFace copies `mclemcrew/MixAssist`, `mclemcrew/MixParams` | **no licence declared** (license=None) [V HF API 2026-10-15] | Reading only — never ship or redistribute |

### 3.2 MED (Mix Evaluation Dataset) — status per lane 04, extended

Lane 04 verified today [R]: MED is not on Zenodo; the Hub mirror `sparrowreivun/Mix-Evaluation-Dataset-2.0` declares no licence; the DAFx-17 paper's own data-availability text makes only **six of ten songs CC BY 4.0**. The listening interface (rd-conx.github.io/med-web, MUSHRA-style A/B) is public. **KENN use: offline calibration and E9 listening material only, restricted to the six CC BY tracks; never redistribute from the Hub mirror.** No official bulk-download page beyond the paper was found this run [?].

### 3.3 New and adjacent items since lane 04

| Item | What it is | Licence | Use |
|---|---|---|---|
| **MUSDB18 / MUSDB18-HQ** (Zenodo 1117372 / 3338373) | Music separation corpus used to train most "MIT" checkpoints | **`other-nc`**, verbatim: *"MUSDB18 is provided for educational purposes only and the material contained in them should not be used for any commercial purpose without the express permission of the copyright holders"*; MUSDBHQ same wording [V Zenodo API] | Closes the dataset end of lane 03's gap #1: every MUSDB-trained checkpoint (ZFTurbo BS-RoFormer, Kimberley vocals, open-unmix, style transfer) now carries a quotable non-commercial dataset caveat. Whether trained weights are a derivative remains a legal question — document, don't assume [I] |
| **AudioCommons timbral_models** | Eight interpretable attributes — hardness, depth, brightness, roughness, warmth, sharpness, booming (regression 0–100), reverb (classification 0/1); *"dependency to essentia was removed"* in v0.4 [V README] | **Apache-2.0** repo (models ship inside it) [V API] | The only clean "sounds like" descriptor models found. README says no longer maintained (repo push 2026-07-06 is a fix). Developed for *"semantically annotating non-musical content"* [V README] → validate on music before any use. Candidate for offline reference/teaching descriptors (E4), not the grade |
| **AI TrackMate** (arXiv 2412.06617, NeurIPS 2024 Creative AI Track) | Training-free pipeline: Music Analysis Module → LLM-readable report → feedback instruction; also cited as *"measure-then-phrase"* precedent in lane 04 | Paper **CC BY 4.0** [V arXiv HTML]; **no official code repo found** (demo page `worzpro.github.io/aitrackmate-demo-page` only) [V searches]; its analysis module cites `AudioCommons/timbral_models` [V arXiv HTML] | Pattern + citation; the timbral_models link is the actionable half |
| **MuseCritic** (arXiv 2608.11755, Aug 2026) | Semi-scalar reward model: natural-language critique over five aesthetic dimensions → continuous reward; trained/evaluated on 200 SongEval songs | GitHub `WuqnEl/MuseCritic`: **licence None** [V API, 5★, pushed 2026-09-20] | Reading only. Critique-as-reward is a 2026 pattern worth watching; song aesthetics ≠ mix grading |
| **automix-toolkit** (csteinmetz1) | Training recipes + pretrained drum auto-mixing models [V README] | Code **Apache-2.0**; HF `csteinmetz1/automix-toolkit` weights **apache-2.0** [V HF API] | KENN has its own AutoMix kernels; these models are ENST-drums/MedleyDB-derived and drum-specific. Pattern only |
| PardonMix / MEGAMI / SPHERE / sequential stem blending | Disagreement-is-structured; multiple valid mixes; convention-encoded rewards | [R lane 04] | Cite as-is from lane 04; no new action |

### 3.4 Citable grading conventions vs house rules (extension of lane 04 §2)

**Citable now (read this run):** BS.1770-5 (11/2023) as the current measurement standard version; EBU R128-2023 target −23.0 LUFS and live tolerance ±1.0 LU; Tech 3341-2023 EBU Mode update rate ≥1 Hz + true-peak tolerances; Tech 3342-2023 (LRA definition); BS.2217-2 expected values (±0.1 LKFS) as test oracles. **Still citable from lane 04 [R]:** Tech 3343 −1 dBTP ceiling; AES TD1006/TD1008 values; Spotify −14 LUFS / −1 dBTP.

**House rules (keep labelled):** PLR and DR thresholds; correlation/width ranges and mono-compat thresholds; headroom targets; and the entire notion of a 0–100 mix grade — **no open standard defines mix quality or a grade**, so every deduction without an EBU/ITU/AES anchor stays tagged `judgement` exactly as `mix_doctor.py` does today (13 of 16) [R plan].

## §4 Q4 — Build vs reuse verdicts (ranked, with first steps)

| # | Gap / E-item | Verdict | Effort | First concrete step |
|---|---|---|---|---|
| 1 | Official conformance material (E2/B1 meter proof) | **Adopt as test material** — EBU Tech 3341 signals + ITU BS.2217-2 values | S | Download the EBU set once, hash it, add it beside the generated signals in `test_streaming_meter_main.cpp`; add the BS.2217-2 expected values as an oracle table; confirm EBU file terms before any redistribution |
| 2 | Momentary 100 ms grid (Tech 3341 case 13, up to 0.46 LU low) | **Extend own C++ kernel** | S | Add a shorter hop (e.g. 10 ms) behind the disabled candidate; re-run cases 1–5 at 44.1/48/96 kHz |
| 3 | LRA conformance + PLR readout | **Extend own kernel**; LRA citable, PLR house rule | S | Tech 3342 range case in the C++ test target; expose `plr_db = true_peak − integrated_lufs` with a house-rule source tag |
| 4 | Independent comparator #2 | **Benchmark sz_meters (MIT)** against the 8x reference | S–M | Build it bare (no JUCE), run the same tone/phased-tone matrices, then the mains-power timing run before any live-path consideration |
| 5 | Reference match (E2 §40 pts / E10 / B4) | **Extend in-house** (`reference_matching.py` + native 40-band LTAS) | M | Feed the 40-band LTAS into the reference path; compute matched A/B gain from existing meters; no new dependency |
| 6 | EQ-match suggestions (E3) | **Keep in-house 7-band + EQ8 preset**; AutoEq as math reference only | M | Validate the existing `.adv` preset output against manual EQ moves on one mix under E9 listening |
| 7 | Teaching figures (E4/E10) | **Extend existing Vue canvas components**; wavesurfer.js only if interactive | M | Add a spectrogram heat layer to `MixReviewWaveform.vue` fed by C++ FFT magnitudes |
| 8 | Timbral teaching descriptors (E4) | **Pilot timbral_models (Apache-2.0), offline only** | M | Run 3 mixes + 3 references (30 s each); check the eight attributes move as expected with known EQ moves; stays out of the grade until that passes |
| 9 | Grade reliability (E9/B1) | **Build KENN's own held-out set** | M–L | Assemble owner-scored mixes + the six MED CC BY songs as references; measure agreement blind |
| 10 | Perceptual metric research | **ViSQOL (Apache-2.0) evaluation only** | L | One-off batch on 48 kHz MED excerpts; do not wire into the grade |

**No dependency is approved by this document.** Candidates requiring owner approval if pursued: sz_meters, timbral_models, wavesurfer.js, matplotlib (off-list licence).

### Master candidate table

| Candidate | Capability | Licence code | Licence weights | M3 cost | Activity | Effort | Verdict |
|---|---|---|---|---|---|---|---|
| EBU Tech 3341-2023 signals | EBU Mode conformance audio, 48 kHz | EBU publication; file terms unstated [?] | n/a | offline | Nov 2023 doc | S | **Use for tests** (terms check first) |
| ITU BS.2217-2 table | 29-file expected-value oracle, ±0.1 LKFS | ITU free PDF | n/a | offline | 10/2016 | S | **Use for tests** |
| libebur128 | LUFS M/S/I + LRA + 4x/2x true peak | MIT | n/a | ~5.53 MB/state @96 kHz [R]; live cost too high for 64 inserts [R] | quiet (v1.2.6, 2021; push 2023) | S | **Comparator only** |
| sz_meters | C++ BS.1770-4 gating, inter-sample TP, AES17 RMS/crest/correlation | **MIT** [V LICENSE] | n/a | unmeasured [est: low, scalar per-sample] | new (2026-09, 2★) | M | **Benchmark candidate** |
| r8brain-free-src | Resampler | MIT | n/a | measured in 14 Oct receipts for JUCE, not r8brain [R] | active (push 2026-09-30) | M | Standby only |
| metermaid | Desktop LUFS meter (Rust/Tauri) | MIT | n/a | n/a (app) | 2026-10, 19★ | S | Spot-check tool only |
| alleato-llc/dr | TT/Pleasurize DR meter | MIT | n/a | unmeasured [est: low] | 2026-02, 0★ | S | Reference for DR definition |
| lufsly (+extension) | Browser LUFS/TP/DR | MIT | n/a | n/a | 2026-07, 1★ | — | Skip |
| Grisey | Metering plugin | **GPL-3.0** | — | — | 2026-09 | — | **Avoid** |
| audiojs/loudness | JS loudness atoms | NOASSERTION | — | — | 2026-09 | — | Avoid (unclear) |
| producer-player | Mastering analysis app | NOASSERTION | — | — | 2026-09 | — | Pattern only |
| wavesurfer.js | Waveform + spectrogram plugins | **BSD-3-Clause** | n/a | [est: browser-side, worker-based; unmeasured] | active (2026-10-13) | S–M | Optional if interactive figures wanted |
| peaks.js (BBC) | Waveform viewer | **LGPL-3.0** | n/a | — | 2026-10-12 | — | **Avoid** |
| matplotlib | Server-side figures | PSF-style permissive, **off allowlist** [V LICENSE text] | n/a | [est: small, batch] | active | S | Owner decision only |
| matchering | Reference mastering (RMS/FR/peak/width match) | **GPL-3.0** [V LICENSE] | n/a | — | 2026-10, 2.7k★ | — | **Avoid**; capability list only |
| ViSQOL | Full-reference perceptual metric (48 kHz) | Apache-2.0 | n/a (SVR bundled) | [est: heavy; Bazel; unmeasured] | 2025-05, 931★ | L | Research only |
| AutoEq | FR matching + EQ derivation (headphones) | MIT | n/a | [est: small, offline] | 2025-07, 16.3k★ | S | Math reference only |
| FFTBalance | Spectrum-match CLI | MIT wrapper; FFTW **GPL**, libsndfile **LGPL-2.1** | n/a | — | 2025-12, 3★ | — | **Avoid bundling** |
| jhtonyKoo style transfer | Reference→target mixing style | MIT code | Drive links, no licence; MUSDB18 NC | — | stale 2023 | — | Weights **avoid**; pattern only |
| Diff-MST | Differentiable mixing console | **CC BY-NC-SA 4.0** | same | — | 2025-07, 65★ | — | **Blocked** |
| timbral_models | 8 timbre attributes (teaching) | Apache-2.0 | bundled in repo | [est: seconds/track, Python; unmeasured] | unmaintained; push 2026-07 | M | **Pilot candidate** |
| automix-toolkit | Drum auto-mixing models | Apache-2.0 | **apache-2.0 (HF)** | [est: heavy] | 2024-08, 119★ | — | Pattern only |
| MuseCritic | Critique→reward song model | **None** (repo) | unverified | — | 2026-09, 5★ | — | Reading only |
| AI TrackMate | Measure→report→feedback pipeline | Paper CC BY 4.0; no repo found | — | — | 2024-12 | — | Pattern + citation |
| MixAssist (code/Zenodo) | Phrasing dialogues | MIT code; cc-by-4.0 data | n/a | offline | code 2026-07 | M | **Use with attribution** |
| MixAssist (HF copies) | same data | **no licence** | — | — | — | — | Do not use |
| MED (six CC BY songs) | Listening material for E9 | CC BY 4.0 (6/10 songs) | n/a | offline | DAFx-17 | M–L | **Use for E9 only** |
| MUSDB18 / -HQ | Separation corpus | **`other-nc`** ("educational ... no commercial purpose") | n/a | offline | — | — | Cannot ship/train commercially; quotable caveat |

## Ranked shortlist mapped to KENN_PLAN items

1. **S — E2/B1: add official conformance material to the meter proof** (EBU Tech 3341 signals + ITU BS.2217-2 oracle table). Closes the "download URL unverified" plan note with a citable pointer.
2. **S — E1/E2: momentary hop fix** (case 13) before the meter is called EBU Mode.
3. **S — E2: LRA conformance + PLR as a labelled house-rule readout.**
4. **S–M — E2: sz_meters (MIT) as second comparator**, benchmarked against the existing 8x accuracy reference.
5. **M — E2/E10/B4: extend `reference_matching.py`** with 40-band LTAS and loudness-matched A/B gain; no new dependency.
6. **M — E4/E10: spectrogram figure from existing canvas components**; wavesurfer.js (BSD-3) only if interactive.
7. **M — E4: timbral_models pilot (Apache-2.0)** for "sounds like" teaching language, kept out of the grade.
8. **M–L — E9/B1: held-out listening set** (owner mixes + six MED CC BY tracks); MixAssist dialogues for phrasing only.
9. **L — E2 research: ViSQOL (Apache-2.0) evaluation**, domain caveat stated.

## Avoid list (exact triggering text)

- **matchering** — LICENSE first lines: *"GNU GENERAL PUBLIC LICENSE / Version 3, 29 June 2007"* [V]. Forks are derivative works; no adoption, including the CLI and Docker image.
- **Grisey, dr14_t.meter, audiometer, pedalboard** — GitHub API `license=GPL-3.0` [V]. Do not vendor, link or shell out to them in shipped code.
- **peaks.js** — GitHub API `license=LGPL-3.0` [V]. LGPL is outside the stated constraint even for test-only use.
- **FFTBalance** — repo MIT, but README requires FFTW3 (*"released under the GNU General Public License (GPL ...)"* [V fftw.org]) and libsndfile (*"GNU LESSER GENERAL PUBLIC LICENSE / Version 2.1, February 1999"* [V COPYING]). Do not bundle; do not treat the MIT top layer as sufficient.
- **Diff-MST** — LICENSE first line: *"Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International"* [V].
- **jhtonyKoo/music_mixing_style_transfer weights** — Google Drive files with no licence and *"Trained with MUSDB18"* [V README]; MUSDB18 Zenodo licence: *"provided for educational purposes only ... should not be used for any commercial purpose without the express permission of the copyright holders"* [V]. Code (MIT) may be read; weights may not ship.
- **MuseCritic repo** — GitHub API `license=None` [V]; unlicensed model weights and code.
- **audiojs/loudness, producer-player, dawcraft** — GitHub API `NOASSERTION` (licence file present but unrecognised or none) [V]; treat as unclear terms.
- **matplotlib** — permissive but off the MIT/BSD/ISC/Apache allowlist [V]; owner decision required before any use, including figure generation.
- **ffmpeg-based loudness tools** — not fetched today; LGPL/GPL by build [R]; the existing rule stands.

## Verified vs inferred

**[V] Verified this run (2026-10-15), primary source read or API queried:**

- Standards: ITU BS.1770-5 in force (11/2023), version list + PDF structure read — https://www.itu.int/rec/R-REC-BS.1770/en, PDF downloaded. EBU R128-2023 (Nov 2023) quote read from https://tech.ebu.ch/docs/r/r128.pdf. Tech 3341-2023 V4 history + signals URL + live-meter ≥1 Hz + references read — https://tech.ebu.ch/docs/tech/tech3341.pdf. Tech 3342-2023 V4 history — https://tech.ebu.ch/docs/tech/tech3342.pdf. Tech 3343 (2023) and Tech 3344 V2.1 (Jul 2016) title pages read from the downloaded PDFs. BS.2217-2 (10/2016) and BS.2217-1 (06/2012) PDFs downloaded; summary, ±0.1 LKFS tolerance, 29 files, 48 kHz 16-bit facts read. Tech 3341 page at tech.ebu.ch/loudness returned Cloudflare 403 (unverifiable today).
- Licences via GitHub API: libebur128 MIT (v1.2.6 commit 2021-02-14; push 2023-06-25); r8brain MIT (version-6.5 commit 2023-12-07; push 2026-09-30); sz_meters MIT (LICENSE raw read); metermaid MIT; alleato-llc/dr MIT; lufsly MIT; Grisey GPL-3.0; audiojs/loudness NOASSERTION; producer-player NOASSERTION; wavesurfer.js BSD-3-Clause (+ `src/plugins/spectrogram.ts` present); peaks.js LGPL-3.0; matplotlib licence text is the PSF-style agreement (GitHub detector: none); matchering GPL-3.0 (raw LICENSE read); AutoEq MIT; FFTBalance MIT (README deps read); ViSQOL Apache-2.0 (README licence line + notes); MixAssist MIT; jhtonyKoo MIT (+ MUSDB18 training line); Diff-MST CC BY-NC-SA LICENSE read; timbral_models Apache-2.0 (+ 8-attribute README, essentia-removed note); MuseCritic licence None; automix-toolkit Apache-2.0.
- Datasets/weights: Zenodo MixAssist 15571750 & 15848443 = cc-by-4.0; HF MixAssist/MixParams license=None; MUSDB18 (1117372) and MUSDB18-HQ (3338373) = `other-nc` with the quoted text; HF `csteinmetz1/automix-toolkit` = apache-2.0.
- Other: FFTW homepage GPL statement; libsndfile COPYING LGPL-2.1 head; AI TrackMate arXiv abstract + CC BY line and absence of an official repo in searches; MuseCritic arXiv abstract + repo link; KENN local source `packages/mix-review/core/reference_matching.py` (7-band, EQ8 preset, 40-point scorer) and `tooling/native/dsp_core/README.md`; frontend canvas components list.

**[R] Reproduced from previous runs' logs, not re-fetched:** KENN C++ meter conformance results (Tech 3341 cases 1–5, 881 checks; case 13 0.46 LU gap); the 98-tone / phased-tone peak receipts and JUCE 8x CPU percentages; libebur128 memory estimate; `mix_doctor` 3-of-16 published / 13 judgement split; Tech 3343 −1 dBTP quote and AES TD1006/TD1008 values; MED DAFx-17 quotes and Hub-mirror licence status; PardonMix/MEGAMI/SPHERE.

**[I] Inferred (judgement, not sourced):** all M3 cost cells marked [est]; sz_meters true-peak accuracy (no conformance evidence seen); timbral_models validity on music (trained for non-musical content annotation); ViSQOL's usefulness on artistic mix differences; the legal status of weights trained on MUSDB18; effort sizes S/M/L.

**[?] Could not verify:** EBU test-signal page reachability (403 via Cloudflare); hosting of the BS.2217 `.wav` files themselves; the licence terms of the EBU signal files; whether BS.1770-5 changed Annex 1/2 text vs -4 (structure read only, no diff); r8brain master vs latest tag contents; MuseCritic HF weight licence (not checked); an official MED bulk download page.

## Facts not verified

1. Where the 29 BS.2217 `.wav` files are actually distributed, and under what terms.
2. The licence/terms of the EBU Tech 3341 test-signal files themselves (the document only names the URL).
3. Whether BS.1770-5 modified the stereo Annex 1 algorithm relative to BS.1770-4 (not diffed).
4. sz_meters' true-peak measurement quality — no test vectors or conformance claims seen; unvalidated [I].
5. timbral_models' training-data licence chain (AudioCommons/Freesound sample terms) and its behavioural validity on full music mixes.
6. jhtonyKoo weights' terms (Google Drive, none stated).
7. The legal question of whether MUSDB18-trained weights count as derivative works of a non-commercial dataset — owner/legal call, not engineering.
8. MuseCritic weight licence on HuggingFace (only the repo licence=None was checked).
9. Whether any newer EBU/ITU compliance material covers BS.1770-5 advanced formats (Annexes 3–4) — none found in this sweep.
