# Lane 03 — Licence-clean audio ML capabilities (understanding, transcription, separation, search, generation)

**Date:** 2026-10-15 · **Platform target:** Apple M3, 16 GB RAM, macOS · **Product constraint:** KENN ships closed-source → code AND weights must be MIT / BSD / ISC / Apache-2.0 (MPL-2.0 test-only). GPL/AGPL/LGPL/BSL/PolyForm/CC-NC/non-commercial/unclear = flag.

**Scope:** what KENN can DO with audio beyond the 14 Oct engineering-candidates doc (which already covers loudness/spectral/stereo libs, Demucs + demucs-mlx, and the GPL/AGPL trap list). This lane covers KENN_PLAN **B3–B4** — the provider slots the plan names (audio-to-MIDI, reference suggestions, AudioGen) — and supplies the licence evidence for the mix-scoring research rows that feed **E2/E9**. `KENN_PLAN.md` defines E1–E11 explicitly (lines 2375–2447); E1 (real-time analysis), E3 (actionable help) and E4 (explain/teach) are native-flow work, out of scope for audio-ML licensing.

**Method:** Each claim verified against the primary repo/HF page/issue where possible on 2026-10-15. Status legend: **[V]** verified this run with URL + date · **[R]** reproduced from previous run's log, not re-fetched · **[I]** inferred · **[?]** could not verify.

**Review state:** takeover-reviewed 15 Oct 2026 — every adoption-gating licence claim and the KQ0 sample re-verified against primary sources, and the MSST SDR tables re-fetched; corrections and remaining unknowns are listed in the closing takeover review. This file is the canonical lane-03 note.

**Verdict vocabulary (master table):** **ADOPT** = shippable inside the allow-list (not an adoption approval) · **WATCH** = gated: off-list licence (CC-BY-4.0, MS-PL, community/revenue terms), an owner decision, or an unread answer · **AVOID** = blocked: GPL/AGPL/LGPL, non-commercial, unclear, or no licence text at all. These map 1:1 to the aggregate report's shippable / gated / blocked.

## KQ0 — Verification of previous run's 10 headline claims

| # | Previous conclusion | Status | What changed |
|---|---|---|---|
| 1 | Demucs v4 weights not shippable | **CONFIRMED** | Exact author quote re-fetched (see below). Added: a second thread comment ties it to MUSDB training terms, and the MUSDB dataset terms are now read, so the chain-of-title caveat is grounded |
| 2 | ZFTurbo MSST + his checkpoints MIT | **NARROWED** | MIT is stated only for two specific checkpoints (53-stem; `model_bs_roformer_ep_17_sdr_9.6568`), not "his checkpoints" as a class. `docs/pretrained_models.md` re-fetched: 75 lines, **no licence column**, zero occurrences of "licen" |
| 3 | Whisper large-v3-turbo weights MIT | **CONFIRMED** | HF metadata tags: turbo = mit, large-v3 = apache-2.0 |
| 4 | Basic Pitch Apache-2.0, ONNX ~230 KB | **CONFIRMED** | ONNX file is exactly 230,444 bytes; TFLite/CoreML/pb exports verified in the git tree; no separate weights licence statement exists (repo-distribution reading, flagged) |
| 5 | Traps (whisper-timestamped, NISQA, ADTOF, chromaprint) | **CONFIRMED** | All four re-verified with exact licence quotes |
| 6 | LAION-CLAP weights apache-2.0, code CC0 | **CORRECTED** | Code CC0-1.0 (repo + PyPI licence field). Primary checkpoint host `lukewys/laion_clap` is tagged **cc0-1.0**; apache-2.0 is only the HF-transformers mirror `laion/clap-htsat-unfused`. PyPI metadata is self-contradictory (classifier says "Apache Software License") |
| 7 | ACE-Step + DiffRhythm Apache-2.0 code+weights | **CONFIRMED + UPDATED** | DiffRhythm explicitly says "code and DiT weights"; ACE-Step v1.5 licence now **resolved: MIT** (repo LICENSE + README + HF tags) |
| 8 | Freesound API free only non-commercial, revocable | **CONFIRMED + STRENGTHENED** | ToS: "the license is temporary and may be withdrawn by Freesound at any time"; keys revocable |
| 9 | MAEB CLAP 8–14% retrieval; ACL 2026 caption critique | **DOWNGRADED** | MAEB (arXiv 2602.16008, 2026-02-17) and Omni-Embed-Audio (arXiv 2604.18360) exist, but the "8–14%" and "<3% FLEURS" figures could not be re-located today → **[?]**, not quotable |
| 10 | 16 GB timings unverified | **PARTIALLY IMPROVED** | New first-party data: ACE-Step M2 Max = 26.4 s per 1 min audio @27 steps. Everything else still unverified |

Details:

1. **Demucs** — [facebookresearch/demucs#327](https://github.com/facebookresearch/demucs/issues/327), comment by **adefossez, 2022-05-23** (verified via GitHub issue-comments API, 2026-10-15): *"The model weights are not covered by the MIT license, and are provided only for scientific purposes."* Corroborating comment by CarlGao4 (2024-06-09): *"The models are trained using MusDB dataset, which requires the result model can only be used for research purpose."* The thread also shows the Intel `demucs-openvino` mirror labelled MIT (2024-06-08 comment) — mirror mislabelling reproduces; the MrCitron CC-BY-NC mirror claim from the prior run was **not** re-checked this run. The MUSDB dataset terms are now read (KQ1), so the restriction behind both quotes is documented, not assumed.
2. **ZFTurbo MSST** — [issue #245](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245), ZFTurbo, 2026-09-25T15:03Z: *"I have released the model weights for 53-stem model under the MIT License. This license fully permits all the points you listed. ... I do not hold the copyright to all audio data used to train this model."* and *"Except I'm not author of all models on pretrained_models.md list."* [Issue #254](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/254), ZFTurbo, 2026-09-30T15:09Z, for `model_bs_roformer_ep_17_sdr_9.6568.ckpt`: *"I released this checkpoint under the MIT license ... the model was trained on the MUSDB18-HQ dataset. I do not know if the dataset's license imposes any restrictions on the commercial use of models trained on it, so you will need to verify that on your end."* A follow-up (lukaspauka-collab, 2026-10-12) asking about `model_scnet_ep_36_sdr_10.0891.ckpt` (SCNet XL IHF) was **unanswered** as of 2026-10-15. The live [docs/pretrained_models.md](https://raw.githubusercontent.com/ZFTurbo/Music-Source-Separation-Training/main/docs/pretrained_models.md) (re-fetched 2026-10-15) lists config+weights links in five tables with **no licence column at all** (75-line file, zero occurrences of "licen"); the repo itself is MIT (GitHub API).
3. **Whisper** — HF API 2026-10-15: `openai/whisper-large-v3-turbo` license=**mit** (809 M params per model card [HF page](https://huggingface.co/openai/whisper-large-v3-turbo)); `openai/whisper-large-v3` license=**apache-2.0** (1550 M). Runtimes: `faster-whisper` PyPI licence = MIT (verified); `whisper.cpp` MIT (previous run [R], not re-fetched).
4. **Basic Pitch** — [repo](https://github.com/spotify/basic-pitch): "Copyright 2022 Spotify AB. This software is licensed under the Apache License, Version 2.0". **No sentence anywhere grants a separate weights licence** — the model files ship inside the repo/package, so the Apache-2.0 grant is expected to cover them, but that is our reading, not an author statement. File sizes from the git tree (2026-10-15): `nmp.onnx` **230,444 bytes** (225 KiB), `nmp.tflite` 204,448 bytes, CoreML mlpackage = 123,027 + 145,956 bytes, TF SavedModel 1,084,140-byte pb. Default runtime order is TF→CoreML→TFLite→ONNX; TF is not installed by default; input is resampled to 22,050 Hz; M1 note = Python 3.10 only.
5. **Traps** — whisper-timestamped: GitHub API licence = **AGPL-3.0**; README credit list also names `dtw-python` = **GPL v3** dependency. NISQA: [README](https://raw.githubusercontent.com/gabrielmittag/NISQA/master/README.md) — code MIT; *"The model weights (nisqa.tar, nisqa_mos_only.tar, nisqa_tts.tar) are provided under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) License"*; domain column = Transmitted/Synthesized **Speech** only. ADTOF: [LICENSE](https://raw.githubusercontent.com/MZehren/ADTOF/master/LICENSE) first line = "Attribution-NonCommercial-ShareAlike 4.0 International". chromaprint: [LICENSE.md](https://raw.githubusercontent.com/acoustid/chromaprint/master/LICENSE.md) — *"Chromaprint's own source code is licensed under the MIT license, but we include some parts of the FFmpeg library ... As a whole, Chromaprint should be therefore considered to be licensed under the LGPL 2.1 license."* audfprint repo API licence = MIT.
6. **CLAP** — LAION-AI/CLAP repo API licence = **CC0-1.0**; PyPI `laion-clap` = CC0 1.0; HF API: `lukewys/laion_clap` (hosts `music_audioset_epoch_15_esc_90.14.pt` etc.) = **cc0-1.0**; `laion/clap-htsat-unfused` = **apache-2.0** (1.07 M downloads). MuQ repo MIT but `OpenMuQ/MuQ-large-msd-iter` weights = **cc-by-nc-4.0**; MERT repo Apache-2.0 but `m-a-p/MERT-v1-95M` = **cc-by-nc-4.0**. So the previous run's "MuQ + MERT weights CC-BY-NC-4.0" stands.
7. **Generation** — ACE-Step [README](https://github.com/ace-step/ACE-Step) "This project is licensed under Apache License 2.0"; HF `ACE-Step/ACE-Step-v1-3.5B` license=apache-2.0. ACE-Step v1.5 licence **resolved this pass: MIT** — repo LICENSE = MIT text ("Copyright (c) 2026 ACEStep"), README licence line = MIT, HF tags `Ace-Step/Ace-Step1.5`, `-xl-turbo` and `-turbo-continuous` all license:mit (tech report arXiv 2602.00744); its card asserts commercially usable, licensed training data — a vendor claim, not an independent finding. DiffRhythm [README](https://github.com/ASLP-lab/DiffRhythm): *"DiffRhythm (code and DiT weights) is released under the Apache License 2.0"* (2025-03-07 news item). `StabilityAI/stable-audio-open-small` HF = license `other/stability-ai-community`, gated=auto (blocked).
8. **Freesound** — [API terms summary](https://freesound.org/docs/api/terms_of_use.html): *"You can use the Freesound API for free only for non-commercial purposes."* [Full ToS](https://freesound.org/help/tos_api/): *"Unless otherwise agreed with Freesound, the license is temporary and may be withdrawn by Freesound at any time. API use is discretionary and we may cancel your use on notice to you."* Access keys *"may be revoked"*; commercial terms *"negotiated on a case by case basis"*.
9. **Retrieval evidence** — [MAEB, "Massive Audio Embedding Benchmark", arXiv 2602.16008](https://arxiv.org/abs/2602.16008) (submitted 2026-02-17), **downgraded this pass**: the paper exists, evaluates 53 encoders, and its best clustering result is 22.7% V-measure (clap-htsat-fused); M2D-CLAP leads text-to-audio retrieval at 47.9% (licence unchecked). The previous run's *"CLAP variants around 8–14%"* and *"below 3% for most language pairs"* FLEURS quotes could **not** be re-located on 2026-10-15 → **[?]**, not quotable; use only the task-level caution, never the percentages. The "ACL 2026" critique is [Omni-Embed-Audio, arXiv 2604.18360](https://arxiv.org/abs/2604.18360) v3 (accepted ACL 2026 Main): *"these benchmarks rely on caption-style queries that differ substantially from real-world search behavior, limiting their assessment of practical retrieval robustness."* Its own OEA solution is a 3B/3B/7B-class multimodal LLM stack (OEA-Qwen7B) — not 16 GB-friendly.
10. **16 GB timing** — the only first-party Mac number found anywhere in this sweep: ACE-Step README hardware table, **MacBook M2 Max, RTF 2.27 @27 steps → 26.43 s per minute of audio** (and 58.25 s/minute @60 steps); Windows/macOS run with `--bf16 false`; max VRAM reduced to 8 GB via `--cpu_offload --overlapped_decode` (2025-05-10 news). No published M3-16 GB timings for Demucs, BS-RoFormer, CLAP, or Whisper were found in this lane.

## KQ1 — Source separation SOTA refresh (licence-first)

### Takeaway
The only shippable SOTA separation today is the ZFTurbo MSST ecosystem: MIT framework, plus **two** checkpoints with explicit first-party MIT statements (53-stem MVSep Mega; 4-stem BS-RoFormer `model_bs_roformer_ep_17_sdr_9.6568`), and one MIT-tagged vocals model from KimberleyJensen. Everything else in the SOTA tier is either non-commercial (demucs, open-unmix umxl), unstated (viperx/aufr33/DrumSep/SCNet-pending — including BS PolarFormer, which now tops the vocals table at SDR 11.00), or unverifiable (MDX23C repo gone).

### Cited Findings

- **Demucs v4 / htdemucs** — code MIT; weights **not covered** (quote in KQ0.1). [issue #327](https://github.com/facebookresearch/demucs/issues/327). No first-party licence exists for any htdemucs checkpoint. `demucs-mlx` covers the 14 Oct doc but inherits the same weight problem.
- **MUSDB / MUSDB18-HQ** — the dataset behind most 4-stem SOTA checkpoints: the [sigsep-mus-db README](https://github.com/sigsep/sigsep-mus-db) (fetched 2026-10-15) says *"The dataset is hosted on Zenodo and requires that users request access, since the tracks can only be used for academic purposes."* The `musdb` Python package is MIT. Whether the access restriction reaches commercial use of trained weights is a legal reading, not an engineering one — ZFTurbo's own position is "verify on your end".
- **Open-Unmix** ([repo](https://github.com/sigsep/open-unmix-pytorch), README fetched 2026-10-15) — code MIT; `umxl` weights: *"Note, that the weights are only licensed for non-commercial use (CC BY-NC-SA 4.0)."* `umxhq`/`umx` weights have **no licence sentence**; both are trained on MUSDB18(-HQ) whose dataset terms need separate review. An MLX port exists: `aufklarer/OpenUnmix-HQ-MLX` (HF tag mit, 2026-03) but it converts the unresolved umxhq weights.
- **Spleeter** ([repo](https://github.com/deezer/spleeter)) — *"The code of Spleeter is MIT-licensed"* — **code only**; pretrained model licence is unstated; trained on Deezer's private stems. README itself warns of TensorFlow Apple M1 issues. Commercial path is "Spleeter Pro" (paid).
- **BS-RoFormer / Mel-Band RoFormer architectures** — `lucidrains/BS-RoFormer` repo = MIT (API, pushed 2026-06-14). A `lucidrains/mel-band-roformer` repo **could not be found today** (404 via API) — Mel-Band implementations live inside downstream repos instead: ZFTurbo MSST (**MIT** repo) and `xavriley/roformer-separation` (MIT). A ggml/C++ inference port exists: `chenmozhijin/BSRoformer.cpp` (MIT, 2026-06).
- **KimberleyJSN/melbandroformer** — HF API licence = **mit** (card modified 2026-04-22); weights = `MelBandRoformer.ckpt`, 913,106,900 bytes; SDR vocals 10.98 (Multisong) — the top entry in the docs' Vocal models table apart from BS PolarFormer (11.00, no licence statement anywhere). The separate repo `KimberleyJensen/Mel-Band-Roformer-Vocal-Model` carries no licence file.
- **ZFTurbo MSST checkpoints** — explicit MIT only as quoted in KQ0.2 (53-stem; bs_roformer bass/stems). SCNet XL IHF (MUSDB test avg 10.08 / Multisong 9.92 — the top 4-stem MUSDB row in the table) licence question **pending** as of 2026-10-15 ([#245 follow-up](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245), the 2026-10-12 comment unanswered).
- **Everything viperx/aufr33/TRvlvr in the MSST docs** (`model_bs_roformer_ep_317_sdr_12.9755`, MelBand viperx, DrumSep, denoise/dereverb) — weights sit on `TRvlvr/model_repo`, `jarredou/models`, `anvuew/*`, `Sucial/*` GitHub releases or HF with **no licence statement anywhere**; ZFTurbo explicitly disclaims authorship of them.
- **MDX23C** — the first-party repo (`kuielab/mdx23c`) returns 404 today; no authoritative code or licence page found. The MSST lists two MDX23C entries, neither with any licence statement: a 4-stem MUSDB18HQ-trained model (MUSDB test avg 7.15 / Multisong 7.02) and a vocals model (SDR vocals 10.17, Multisong).
- **Drum-separation checkpoints** (`jarredou DrumSep`, `aufr33-jarredou MDX23C DrumSep`, kick/snare/toms/hh/cymbals) — unstated licences; third-party wrapper `xavriley/mdx23c-drum-separation` is MIT code only.
- **SOTA numbers in one place** (MSST docs re-fetched 2026-10-15; "Multisong" unless noted; the docs' own note says their vocal metrics come from mvsep.com's quality checker): **Vocal models** — BS PolarFormer vocals SDR **11.00** (table top), KimberleyJSN MelBand 10.98, viperx BS RoFormer 10.87, MDX23C vocals 10.17, HTDemucs4 MVSep 8.78. **4-stem MUSDB18HQ list** — SCNet XL IHF MUSDB avg **10.08** / Multisong 9.92 (licence pending), SCNet XL 9.80 / 9.72, BS RoFormer 9.65 / 9.38, SCNet Large (starrytong) 9.70 / 9.28, DTTNet 7.83 / 7.48, MDX23C 7.15 / 7.02. **Multi-stem** — HTDemucs4 Multisong avg 9.16; 6-stem HTDemucs4 (bass/drums/vocals/other/piano/guitar) exists in the MSST list → **but its weights are the fbaipublicfiles demucs `.th` files → demucs weight licence applies → not shippable**.
- **Conversion precedent** (in-thread, not published code): kawasakikaito (#254) describes converting shared backbone + bass mask to **CoreML fp16** for iOS; lukaspauka-collab (#245) plans **TorchScript** for a macOS plugin. Both are third-party plans, not released tools.
- **Extra stems**: 53-stem MVSep Mega is the only >6-stem model with an MIT statement (#245); it is **not** listed in the docs table and no first-party host was located — third-party HF mirrors (noblebarkrr, oulianov, …) carry no licence tags; DrumSep (5–6 drum stems) licences unstated.

### Inferences
- A KENN-safe separation feature = MSST (MIT) + KimberleyJSN mel-band vocals (MIT) + ZFTurbo BS-RoFormer bass/drums checkpoint (MIT; quote the MUSDB18-HQ caveat and ZFTurbo's "verify on your end" line verbatim in NOTICE.md). This exactly matches the workflow in #245's body ("instrumental by subtracting a Mel-Band RoFormer vocal estimate from the mix").
- 16 GB fit: these checkpoints are few-hundred-MB transformer models; one track at a time on M3 is plausible but **no measured M3 number exists** (Gaps). Expect CPU/GPU seconds-to-minutes per 3–4 min track; must be measured.
- The MUSDB18-HQ dataset terms are now read (access by request, "academic purposes only"; quote in KQ1), but whether they bind commercial use of trained weights is a legal reading that remains open, so even the "MIT" checkpoints carry a documented chain-of-title caveat. The clean long-term fix is fine-tuning on KENN user-authorized stems, which is out of scope for this lane.

### Gaps
- MUSDB18-HQ dataset terms are now read (quote above), but whether they bind commercial use of trained weights is a legal reading — open.
- `jarredou/BS-RoFormer-SW` HF page returns 401 again (may be private/renamed) → its "licence unknown" status is inherited from context, not directly observed today.
- BS PolarFormer (table-topping vocals SDR) has no licence statement anywhere; the SCNet XL IHF question is still unanswered (#245 follow-up, 2026-10-12).
- No published M3 (not M2 Max) timing for any separation model.

## KQ2 — Note/MIDI transcription

### Takeaway
Basic Pitch is the single clean, small, production-mature AMT option (Apache-2.0, 230,444-byte ONNX, no TensorFlow needed, and KENN_PLAN B4 already names it). Pitch-tracking has clean small options (torchcrepe, swift-f0 MIT). MT3's code is Apache-2.0 (`magenta/mt3`) but its checkpoints are unstated; piano_transcription_inference is archived and carries no licence file (its README claims Apache 2.0); RMVPE code is Apache-2.0 but weights are unstated.

### Cited Findings
- **Basic Pitch** — Apache-2.0 (repo README); official `nmp.onnx` = **230,444 bytes** (225 KiB); official TFLite 204,448 bytes, CoreML mlpackage 123,027 + 145,956 bytes, TF SavedModel 1,084,140-byte pb (git tree, 2026-10-15); default runtime order TF→CoreML→TFLite→ONNX, TF install is optional; instrument-agnostic polyphonic, *"works best on one instrument at a time"*; mono, resampled to 22,050 Hz; macOS M1 = Python 3.10 note. A VST sibling exists (NeuralNote, third-party).
- **MT3** — code Apache-2.0 (`magenta/mt3`, API, pushed 2026-10-07); the old `google-research/mt3` path returns 404 today. README offers "a pretrained checkpoint" via Colab but states **no checkpoint licence**; T5X/JAX dependency chain is heavyweight. Treat weights as unstated.
- **piano_transcription_inference** (`bytedance/piano_transcription`) — repo **archived** (pushed 2023-08-18), GitHub API licence = **None** (no LICENSE file at HEAD) even though the README carries a "## LICENSE / Apache 2.0" section; the runtime package `piano_transcription_inference` has no licence file either, and its weights come from Zenodo record 4034264 with no stated terms. An incomplete claim without a licence file — still avoid.
- **torchcrepe** — actual repo now `maxrmorrison/torchcrepe` (the old `marl/torchcrepe` path 404s); API licence = **MIT** (pushed 2025-05-16). Weight bundled with the Python package; per-weight licence not separately stated (inferred MIT).
- **RMVPE** (`Dream-High/RMVPE`) — API licence = **Apache-2.0** (2024); pretrained `rmvpe.pt` weight licence **unstated**; widely used inside the so-vits-svc AGPL ecosystem — flag the weight.
- **swift-f0** (`lars76/swift-f0`) — API licence = **MIT** (pushed 2026-09-25); lightweight f0 tracker, model bundled in repo (size/detail not verified this run).
- **Parakeet TDT 0.6B v3** (cross-ref; lane 02 owns the voice stack) — HF licence = **cc-by-4.0** (downloadable, not HF-gated; off KENN's allow-list → gated, owner decision + attribution line); MLX runtime `senstella/parakeet-mlx` = Apache-2.0. Listed here only because ASR sits beside this lane's transcription scope.
- **Melody extraction** — no licence-clean first-party model identified this run; the classic Melodia is a GPL Vamp plugin (not re-verified).
- Basic Pitch timeline: ICASSP 2022 paper, still maintained by Spotify.

### Inferences
- For KENN B3/B4 the practical stack is: Basic Pitch ONNX on bounded instrument clips (KENN_PLAN B4 explicitly says "Basic Pitch ONNX on bounded instrument clips, one at a time"), plus torchcrepe/swift-f0 if a monophonic pitch curve is wanted, e.g. for vocal tuning analysis. None of these need TensorFlow on macOS in production.
- MT3's quality is higher on multi-instrument mixes but the licence + dependency profile makes it research-only until the checkpoint owner states terms.

### Gaps
- MT3 checkpoint licence: unstated (README silence; Google storage bucket terms not reviewed).
- swift-f0 model file licence/size and RMVPE weight provenance not verified.
- No clean, shippable guitar-transcription model found (piano focused repos are dead ends; guitar-specific AMT is research code).

## KQ3 — Audio embeddings and sound search

### Takeaway
LAION-CLAP is the only licence-clean audio-text embedder (code CC0, checkpoints CC0; the HuggingFace mirror is Apache-2.0). OpenL3 is clean-but-attribution (CC-BY-4.0 weights) and dated. MuQ and MERT are blocked (NC weights); MS-CLAP's weights are **MS-PL** — off the allow-list → gated, not blocked; M2D-CLAP (MAEB's text-to-audio leader) has an unchecked licence. Expect limited absolute retrieval: the earlier "8–14%" figure could not be re-located **[?]**, so quote the task-level caution, not percentages.

### Cited Findings
- **LAION-CLAP** — [repo](https://github.com/LAION-AI/CLAP) licence CC0-1.0 (API, pushed 2025-05); PyPI `laion-clap`: the licence field carries the CC0 text while the classifier says "Apache Software License" — self-contradictory metadata, so trust the repo LICENSE (CC0); checkpoints on [`lukewys/laion_clap`](https://huggingface.co/lukewys/laion_clap) = **cc0-1.0** tag (music / music+speech / music+speech+audioset variants listed in README; files 1.86–2.35 GB each, `music_audioset_epoch_15_esc_90.14.pt` = 2,352,471,003 bytes); HF Transformers port `laion/clap-htsat-unfused` = **apache-2.0** (1.07 M downloads). Embedding dims: 512-d joint space / 768-d HTSAT audio tower **[I]** (config not re-read).
- **MS-CLAP** — code repo `microsoft/CLAP` = **MIT** (API, archived). Weights **resolved this pass**: the HF card [`microsoft/msclap`](https://huggingface.co/microsoft/msclap) = **ms-pl**, hosting `CLAP_weights_2022.pth` (2.33 GB), `CLAP_weights_2023.pth` (690 MB) and clapcap weights (1.71 GB); `microsoft/clap-ms-2023` still 401s. MS-PL is permissive but off KENN's allow-list → gated.
- **M2D-CLAP** — text-to-audio leader in MAEB (47.9% T2A); licence and repo terms **not checked this run [?]** — resolve before any work.
- **MuQ** — code MIT (`tencent-ailab/MuQ`, API); weights `OpenMuQ/MuQ-large-msd-iter` = **cc-by-nc-4.0** → blocked. (MuQ-MuLan is the text-alignable variant per MAEB.)
- **MERT** — code Apache-2.0 (`yizhilll/MERT`, API); weights `m-a-p/MERT-v1-95M` = **cc-by-nc-4.0** → blocked.
- **OpenL3** — code MIT; [README](https://raw.githubusercontent.com/marl/openl3/master/README.md) has a dedicated section: *"Model Weights License: The model weights are made available under a Creative Commons Attribution 4.0 International (CC BY 4.0) License."* Off-list (attribution, not MIT/Apache) but non-NC. Python ≥0.4 requires TensorFlow 2 (heavy runtime).
- **musicnn** — code ISC (API); README carries **no weights licence**; models are trained on the Million Song Dataset (research-only terms) → flag.
- **YAMNet** — not re-verified this run; TensorFlow Hub distribution historically Apache-2.0 **[R/I]**.
- **Retrieval-quality evidence** — MAEB ([arXiv 2602.16008](https://arxiv.org/abs/2602.16008), 2026-02-17, "Massive Audio Embedding Benchmark"): 53 encoders; best clustering = 22.7% V-measure (clap-htsat-fused); M2D-CLAP tops text-to-audio retrieval at 47.9% (licence unchecked). The "8–14%" and "<3% FLEURS" figures from the previous run could not be re-located → **[?]**. Omni-Embed-Audio ([arXiv 2604.18360](https://arxiv.org/abs/2604.18360), ACL 2026 Main) argues caption-style benchmarks flatter models vs real "user intent" queries; its OEA solution is a 3B/3B/7B-class multimodal LLM stack (OEA-Qwen7B — not 16 GB-friendly).

### Inferences
- For KENN sample/library search, CLAP is fine as a **ranking/embedded-suggestion aid**, but product copy should not promise semantic search accuracy: MAEB's best clustering result is 22.7% V-measure and its retrieval percentages did not survive re-checking **[?]**, so there is no verified number to promise with.
- CLAP can run on 16 GB Mac (small transformer tier); ONNX/CoreML export is technically routine (torch.onnx) but no official export found **[I]**.
- Interesting side evidence: a 2026 DAFx paper ([arXiv 2607.03806](https://arxiv.org/abs/2607.03806)) shows LUFS/RT60/spectral-centroid are recoverable from CLAP embeddings — evidence that CLAP vectors carry low-level mix attributes, not only semantics.

### Gaps
- M2D-CLAP licence unchecked (MAEB's text-to-audio leader) — resolve before any work.
- `microsoft/clap-ms-2023` still 401; the msclap card is the reachable source of the MS-PL weights.
- No measured 16 GB memory/time profile for any embedder; dims not re-read from configs (checkpoint file sizes now recorded).
- No licence-checked evaluation of CLAP on a **user sample library** (all evidence is benchmark datasets like AudioCaps/Clotho/ESC50).

## KQ4 — Drum / rhythm

### Takeaway
beat_this is the one clean drum-adjacent win: MIT on **both code and published weights**, explicitly, with tiny checkpoints — but its published inference code calls LGPL `soxr` directly (`inference.py`), so the product must replace that call or isolate the dependency. ADTOF is non-commercial. All drum-separation checkpoints are licence-unstated.

### Cited Findings
- **beat_this** ([CPJKU/beat_this](https://github.com/CPJKU/beat_this), ISMIR 2024) — License section verbatim: *"The code and the published model weights are released under the MIT license. Note that some of the training files are fully copyrighted or under limited Creative Commons licenses, and it is up to the user to assess whether this may impact their use case."* Model sizes: main `final*` ≈ 78 MB; `small*` ≈ **8.1 MB** per model. The `soxr` dependency is used **at inference**, not just install: `beat_this/inference.py` imports it and calls `soxr.resample(signal, in_rate=sr, out_rate=22050)` (lines 274–275); PyPI `soxr` licence = **LGPL-2.1-or-later**. Optional DBN needs madmom (GPL) — not required; the paper's selling point is *no DBN postprocessing*.
- **ADTOF** — LICENSE file (fetched) = **CC BY-NC-SA 4.0** → blocked for a commercial product.
- **Drum transcription alternatives** — none found with a first-party permissive statement; the DrumSep checkpoints in MSST (jarredou/aufr33; kick/snare/toms/hh/cymbals) have unstated licences (see KQ1).
- **Groove extraction** — no shippable model found (Groove MIDI dataset and groove2groove research artifacts not licence-reviewed in this lane).
- Beat/downbeat wrappers: `xavriley/*` and `chenmozhijin/BSRoformer.cpp` are MIT code found in search (KQ1) but not rhythm models.

### Inferences
- KENN can offer beat/downbeat timelines from beat_this `small` (8 MB) at low risk, provided the production integration resamples first with a permissive resampler (vDSP or torchaudio) before the model call — a one-call-site substitution — or documents LGPL as an isolated dependency.
- Pattern-level groove analysis is better served by KENN's own DSP (onset/tempo from existing C++ meters) than by any licence-clean ML model found.

### Gaps
- The soxr-free substitution is untested (one call site, but the model's expected input rate must be matched).
- No licence-clean drum *transcription* (kit-piece transcription, not separation) found at all.

## KQ5 — Music generation (future, opt-in)

### Takeaway
Three clean families now: **ACE-Step** (v1 Apache-2.0, v1.5 **MIT** — both code+weights; first-party Mac numbers) and **DiffRhythm** (code + DiT weights Apache-2.0; VAE and HF tags unresolved). YuE is Apache-2.0 too but 8B-class → not 16 GB. Everything else is CC-NC or gated-community. Under KENN_PLAN B4, generation stays behind explicit opt-in and licence review.

### Cited Findings
- **ACE-Step v1** — [repo](https://github.com/ace-step/ACE-Step) Apache-2.0; HF `ACE-Step/ACE-Step-v1-3.5B` = apache-2.0; 3.5B params (name), 4 min of music in 20 s on A100; **MacBook M2 Max: RTF 2.27 @27 steps = 26.43 s / min of audio**; max VRAM reduced to 8 GB with `--torch_compile true --cpu_offload true --overlapped_decode true` (2025-05-10); macOS requires `--bf16 false`. LoRA variants (Lyric2Vocal, Text2Samples) exist.
- **ACE-Step v1.5** — **licence resolved this pass: MIT** on code and weights. `ace-step/ACE-Step-1.5` LICENSE = MIT text ("Copyright (c) 2026 ACEStep"); README licence line = MIT; HF `Ace-Step/Ace-Step1.5` license:mit (plus the `xl-turbo` and `turbo-continuous` variants); tech report [arXiv 2602.00744](https://arxiv.org/abs/2602.00744). The card asserts the checkpoint is commercially usable and trained on licensed data — a vendor claim, not an independent finding. No M3-16 GB timing published.
- **DiffRhythm** — [repo](https://github.com/ASLP-lab/DiffRhythm): *"DiffRhythm (code and DiT weights) is released under the Apache License 2.0"* (news 2025-03-07); macOS supported since 2025-03-11; *"DiffRhythm-base requires a minimum of 8G of VRAM... use the `--chunked` argument"*; full-length 285 s generation; HF checkpoint repos (`DiffRhythm-1_2`, etc.) carry **no licence tag** and `ASLP-lab/DiffRhythm-1_2B` 401s; the separate `DiffRhythm-vae` licence is unstated. Runtime requires `espeak-ng` (**GPL-3.0** program — a phonemization dependency to isolate/avoid bundling). Successors exist as papers — DiffRhythm 2 ([arXiv 2510.22950](https://arxiv.org/abs/2510.22950)) and DiffRhythm+ ([arXiv 2507.12890](https://arxiv.org/abs/2507.12890)) — weights and licences unreviewed **[?]**.
- **YuE** — code Apache-2.0 (API); weights `m-a-p/YuE-s1-7B-anneal-en-cot` = **apache-2.0**; 7B + 1B stack **[I]** → weight memory alone exceeds comfortable 16 GB f16 use.
- **Blocked (verified HF tags)**: `facebook/musicgen-small` = cc-by-nc-4.0; `facebook/magnet-small-10secs` = cc-by-nc-4.0; `cvssp/audioldm2` = cc-by-nc-sa-4.0; `declare-lab/tango2` = **cc-by-nc-sa-4.0** (previous note said nd — corrected); `StabilityAI/stable-audio-open-small` = `other` + `stability-ai-community`, gated. Stable Audio Open (full) uses the same gated community licence family.
- **Mustango** — its HF card carries an apache-2.0 tag only and nothing else was verified this run **[?]**; the Tango-family lineage means we keep it blocked until the card and weights are actually read.
- **MAGNeT** — cc-by-nc-4.0 (verified above).

### Inferences
- If generation ever ships, ACE-Step v1 is the pick on licence + Mac evidence; DiffRhythm second (smaller, but VAE/espeak caveats). Both are "background render" workloads on 16 GB (minutes per minute of audio on M-series class hardware), never interactive.
- The dataset provenance of both (massive web-music training) carries the same undocumented chain-of-title caveat ZFTurbo flags; product copy should say "AI-generated, verify originality" as their READMEs themselves do.

### Gaps
- DiffRhythm VAE licence unstated; `DiffRhythm-1_2B` still 401s; HF checkpoint repos carry no licence tags; DiffRhythm 2 / DiffRhythm+ licences unreviewed.
- No M3-16 GB generation benchmark; M2 Max RTF is the closest anchor.
- Mustango tag unread **[?]**; AudioLDM2 code licences not pursued (weights blocked first).

## KQ6 — Sample-library / asset retrieval infrastructure

### Takeaway
Freesound is usable **only** with a negotiated commercial deal (free tier is non-commercial, licences revocable at will, and per-sound CC terms still apply). For local fingerprinting, audfprint (MIT) is the clean substitute for chromaprint (LGPL-2.1 as a whole). Indexing a user's own local library has no upstream licence problem.

### Cited Findings
- **Freesound API free tier** — [API ToS summary](https://freesound.org/docs/api/terms_of_use.html): *"You can use the Freesound API for free only for non-commercial purposes."* [Full ToS](https://freesound.org/help/tos_api/) §1: *"Unless otherwise agreed with Freesound, the license is temporary and may be withdrawn by Freesound at any time. API use is discretionary and we may cancel your use on notice to you."* §2: access keys *"may be revoked"*. §3: *"Terms for commercial use of the API will be negotiated on a case by case basis with UPF."* §4 additionally bans redistributing Content outside the app, bulk copies of the DB, and service-bureau patterns.
- **Per-sound licences** — Content is under per-item CC licences (CC0, CC-BY, and BY-NC variants); even with an API deal, NC sounds must be filtered out for a commercial product [R, from Freesound platform terms; not re-pulled this run].
- **chromaprint** — [LICENSE.md](https://raw.githubusercontent.com/acoustid/chromaprint/master/LICENSE.md): *"Chromaprint's own source code is licensed under the MIT license, but we include some parts of the FFmpeg library ... As a whole, Chromaprint should be therefore considered to be licensed under the LGPL 2.1 license."* The same file notes the shipped binary's effective licence depends on the FFT library it links against; it does **not** name vDSP or FFTW — the earlier "vDSP fine, FFTW GPL" split was our inference **[I]**, not their wording.
- **audfprint** (`dpwe/audfprint`) — GitHub API licence = **MIT**; frozen since 2019 but pure NumPy/Python and simple to vendor.

### Inferences
- Local library indexing plan: file-hash dedupe → audfprint fingerprints for near-duplicate detection → CLAP embeddings for text/similarity search. All run against the user's own files, so no distribution licence arises; only the *code* licences matter.
- For optional online sample search, treat Freesound as a contracted vendor (commercial agreement required); keep it behind explicit opt-in per KENN's B4 "no silent network provider" rule.

### Gaps
- No Freesound commercial price/volume terms published (contact-only).
- audfprint's accuracy vs chromaprint not compared this run.

## KQ7 — Audio-quality / mix-scoring models

### Takeaway
No licence-clean **music-mix** quality model exists in the open. NISQA (speech) is NC. The nearest clean item is Meta's AudioBox-Aesthetics (CC-BY-4.0 for code *and* weights — permissive-with-attribution, but off KENN's strict MIT/Apache list), which predicts production-quality-style attributes and is music-capable.

### Cited Findings
- **NISQA** — code MIT; weights **CC BY-NC-SA 4.0**; domain = transmitted/synthesized **speech** only → blocked twice over (quote in KQ0.5).
- **AudioBox-Aesthetics** — `facebookresearch/audiobox-aesthetics` repo states *"The majority of audiobox-aesthetics is licensed under CC-BY 4.0"* (the microsoft/unilm portions remain MIT); HF `facebook/audiobox-aesthetics` = **cc-by-4.0**, 508 K downloads, modified 2025-03. Head semantics verified against the model card and [the paper, arXiv 2502.05139](https://arxiv.org/abs/2502.05139): CE = Content Enjoyment, CU = Content Usefulness, PC = Production Complexity, PQ = Production Quality.
- **SQUIM / speech quality in torchaudio** — speech-only (STOI/PESQ/SI-SDR proxies); not music-relevant; licence not re-verified.
- KENN's own path: the 14 Oct engineering doc already owns loudness/true-peak/spectral/stereo metering in C++ — that remains the only fully-owned mix-scoring layer.

### Inferences
- For E-family "mix scoring" aspirations, the defensible position today is: KENN DSP meters = shipped analysis; CLAP-embedding probes (DAFx 2026 evidence, KQ3) and AudioBox-Aesthetics = opt-in research aids, not shipped grading, because (a) CC-BY-4.0 is outside the strict code/weights list and (b) no model is validated on club/pop mixes.

### Gaps
- No open music-MOS model with permissive weights found (research CLAP-regression models are not released as weights).
- AudioBox-Aesthetics model size / M3 runtime not measured.

## Master candidate table

Verified 2026-10-15 unless marked. "Clean" = code and weights both MIT/BSD/ISC/Apache-2.0. **Verdict** = ADOPT (shippable as-is) / WATCH (gated; the parenthetical names the blocker to clear) / AVOID (blocked) — see the header vocabulary. **Effort** scale (14 Oct doc): S < 2 days · M ≤ 1 week · L > 1 week. Cost figures **[I]** unless a source is cited.

| # | Candidate | Function | Code licence | Weight licence | Size (verified) | M3 16 GB fit / cost [I] | Effort | Verdict | Maturity / notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Basic Pitch | audio→MIDI (AMT) | Apache-2.0 | Apache-2.0 (repo-distributed; no separate grant sentence [I]) | ONNX 230,444 B (225 KiB); TFLite 204,448 B; CoreML 123,027 + 145,956 B | Yes — seconds per bounded clip, no TF | S | **ADOPT** | Mature; official ONNX/CoreML/TFLite; named in B4; confirm the weights reading if it ships |
| 2 | Whisper large-v3-turbo | speech/lyrics transcription | MIT (repo) | **MIT** (turbo; v3 = Apache-2.0) | 809 M params; large-v3 1,550 M | Yes — whisper.cpp Metal | S–M | **ADOPT** | Mature; use whisper.cpp / faster-whisper (MIT); never whisper-timestamped (AGPL) |
| 3 | Parakeet TDT 0.6B v3 | speech ASR (lane 02's stack) | runtime `parakeet-mlx` Apache-2.0 | **cc-by-4.0** | 0.6 B | Yes (MLX runtime) | S | **WATCH** (gated: CC-BY-4.0) | not HF-gated; off KENN's allow-list → owner decision + attribution line |
| 4 | LAION-CLAP | audio/text embeddings, tagging | CC0-1.0 | CC0-1.0 (checkpoints); mirror `laion/clap-htsat-unfused` = Apache-2.0 | checkpoints 1.86–2.35 GB each | Yes — ~2 GB model one at a time | M | **ADOPT** | weak absolute retrieval ([?] on the old percentages); ranking aid, not search guarantee; PyPI metadata quirk |
| 5 | beat_this | beat/downbeat | MIT | **MIT** (explicit) | small 8.1 MB; final 78 MB | Yes — tiny | S | **ADOPT** (condition) | `inference.py` calls soxr (LGPL) at lines 274–275 → replace the call or isolate |
| 6 | KimberleyJSN mel-band RoFormer | vocal separation | MIT (MSST impl.) | **MIT** (HF tag; card mod 2026-04-22) | `MelBandRoformer.ckpt` 913,106,900 B | Likely — measure wall time | M | **ADOPT** (caveat) | SDR vocals 10.98 (Multisong); MUSDB18-HQ chain caveat documented; not the table top (PolarFormer 11.00 is, unlicensed) |
| 7 | ZFTurbo BS-RoFormer 4-stem | separation (bass/drums/etc.) | MIT | **MIT** (#254; "verify on your end" MUSDB caveat) | checkpoint `model_bs_roformer_ep_17_sdr_9.6568.ckpt` (size not measured) | Likely — measure wall time | M | **ADOPT** (caveat) | MUSDB 9.65 / Multisong 9.38; quote the author statement verbatim in NOTICE |
| 8 | BS PolarFormer | vocal separation (table top) | n/a | **no statement anywhere** | — | Unmeasured | — | **AVOID** (unstated) | tops the Vocal models table at SDR 11.00; nothing to pin |
| 9 | ZFTurbo 53-stem MVSep Mega | 53-stem separation | MIT | **MIT** (#245 first-party) | — | Unlikely (large) | M–L | **WATCH** (host) | not in the docs table; third-party HF mirrors carry no tags — locate the first-party release first |
| 10 | MSST framework | separation train/infer | MIT | n/a | — | Yes | S | **ADOPT** | engine for rows 6/7/9 |
| 11 | lucidrains/BS-RoFormer + `BSRoformer.cpp` | RoFormer implementations | MIT / MIT | n/a | — | n/a (code) | S | **ADOPT** | architecture code + ggml port for our own conversion path |
| 12 | ACE-Step v1 | music generation | Apache-2.0 | Apache-2.0 | 3.5 B | Yes, slow — M2 Max 26.43 s/min @27 steps [V] | L | **ADOPT** (opt-in) | macOS needs `--bf16 false`; B4 opt-in gate applies |
| 13 | ACE-Step v1.5 | music generation | **MIT** | **MIT** (LICENSE "Copyright (c) 2026 ACEStep"; HF tags mit) | not measured | Unmeasured on M3 | L | **ADOPT** (opt-in) | arXiv 2602.00744; card claims commercially licensed data — vendor claim; measure s/min on M3 first |
| 14 | DiffRhythm | song generation | Apache-2.0 | Apache-2.0 (DiT weights, README quote) | 1.2 B base | 8 GB min VRAM chunked (README) | L | **WATCH** (unresolved parts) | HF checkpoints untagged; 1_2B 401; VAE unstated; espeak-ng GPL-3; successors unreviewed |
| 15 | YuE | song generation | Apache-2.0 | apache-2.0 (s1 weights) | 7 B + 1 B | No — too large | L | **ADOPT** (licence) | clean licence, no 16 GB fit |
| 16 | torchcrepe | pitch tracking | MIT | MIT (bundled, inferred) | small | Yes | S | **ADOPT** | repo now `maxrmorrison/torchcrepe` |
| 17 | swift-f0 | f0 tracking | MIT | bundled in repo (detail unverified) | small | Yes | S | **WATCH** (details) | re-check the weight file before use |
| 18 | OpenL3 | audio embeddings | MIT | CC-BY-4.0 (explicit) | small | Yes — TF2 dep | M | **WATCH** (gated: CC-BY-4.0) | dated |
| 19 | AudioBox-Aesthetics | aesthetics/quality scoring | CC-BY-4.0 (majority; unilm portions MIT) | CC-BY-4.0 | not measured | Likely | M | **WATCH** (gated: CC-BY-4.0) | heads CE/CU/PC/PQ verified; only clean-ish music-quality model |
| 20 | audfprint | fingerprint/dedupe | MIT | n/a | small | Yes | S | **ADOPT** | frozen 2019; pure NumPy; chromaprint substitute |
| 21 | faster-whisper / whisper.cpp | ASR runtime | MIT / MIT | n/a | small | Yes | S | **ADOPT** | runtimes for row 2 |
| 22 | Open-Unmix | separation baseline | MIT | umxl CC-BY-NC-SA (**blocked**); umxhq unstated | small | Yes | S | **AVOID** (weights) | MLX port converts the unresolved umxhq weights |
| 23 | Demucs v4 | separation | MIT | **"not covered by the MIT license ... only for scientific purposes"** | ~300 MB class | — | — | **AVOID** (weights) | mirrors disagree; never rely on mirrors |
| 24 | Spleeter | separation | MIT | Unstated (code-only statement) | small | M1 pain (README) | — | **AVOID** (weights) | — |
| 25 | MT3 | multi-instrument AMT | Apache-2.0 (`magenta/mt3`) | **Unstated** | T5-class | Unlikely | — | **AVOID** (weights unstated) | `google-research/mt3` 404s today |
| 26 | RMVPE | vocal pitch | Apache-2.0 | **Unstated** | small | Yes | — | **AVOID** (weights) | AGPL-adjacent ecosystem |
| 27 | piano_transcription_inference | piano AMT | no licence file (README claims Apache 2.0) | Zenodo weights, terms unstated | small | — | — | **AVOID** | archived 2023 |
| 28 | musicnn | music tagging | ISC (via setup.py; no LICENSE file) | Unstated (MSD-trained) | small | Yes | — | **AVOID** (weights) | — |
| 29 | MS-CLAP | audio/text embeddings | MIT (`microsoft/CLAP`, archived) | **MS-PL** (HF `microsoft/msclap`) | 2.33 GB / 690 MB / 1.71 GB | Yes | M | **WATCH** (gated: MS-PL) | `microsoft/clap-ms-2023` still 401 |
| 30 | M2D-CLAP | embeddings (MAEB text-to-audio leader, 47.9%) | unchecked | unchecked **[?]** | — | — | — | **WATCH** (licence unread) | resolve before any work |
| 31 | MuQ / MERT | audio embeddings | MIT / Apache-2.0 | **CC-BY-NC-4.0** | — | — | — | **AVOID** (weights) | — |
| 32 | YAMNet | tagging | Apache-2.0 [R] | Apache-2.0 [R] | small | Yes | S | **WATCH** (re-check) | not re-verified this run |
| 33 | ADTOF | drum transcription | CC-BY-NC-SA-4.0 | same | small | — | — | **AVOID** | LICENSE first line is the trigger |
| 34 | NISQA | speech quality | MIT | **CC-BY-NC-SA-4.0**, speech-only | small | — | — | **AVOID** | two independent blockers |
| 35 | MusicGen / MAGNeT | generation | MIT family | **CC-BY-NC-4.0** | 0.3–3 B | — | — | **AVOID** (weights) | — |
| 36 | AudioLDM2 / Tango2 | generation | permissive family | **CC-BY-NC-SA-4.0** | 1–3 B | — | — | **AVOID** (weights) | Tango2 corrected NC-SA (prior note said ND) |
| 37 | Stable Audio Open (Small) | generation | community licence | gated `stability-ai-community`, revenue terms | small | Maybe | — | **WATCH** (gated) | — |
| 38 | chromaprint | fingerprint | MIT parts | n/a | tiny | — | — | **AVOID** (LGPL-2.1 as a whole) | row 20 is the substitute |
| 39 | Freesound API | sample source | vendor ToS | per-sound CC (filter NC for commerce) | n/a | — | — | **WATCH** (gated: commercial deal) | free tier non-commercial + revocable |
| 40 | Mustango | generation | apache-2.0 tag only **[?]** | same **[?]** | 1 B class | — | — | **AVOID** (default) | Tango-family lineage; read the card before believing the tag |
| 41 | viperx / aufr33 / TRvlvr / jarredou / anvuew / Sucial families | separation/drum/dereverb/denoise | n/a | **no licence statement anywhere** | — | — | — | **AVOID** (unstated) | ZFTurbo explicitly disclaims authorship |

**Attribution obligations** (once a WATCH row clears the gate): Apache-2.0 → ship the licence text and any NOTICE file; MIT/BSD/ISC → reproduce the copyright notice and licence text in the product notices; CC0 → none; CC-BY-4.0 → human-readable attribution plus a licence link (this is what keeps it off today's allow-list); MS-PL → reproduce the licence text. `docs/research/THIRD_PARTY_LICENCES.md` is the record of what ships.

## Ranked shortlist vs KENN_PLAN B3/B4 (and E2/E9 research rows)

Plan definitions read from `KENN_PLAN.md` (15 Oct 2026):
- **B3 — MIDI creation** (lines 2370–2373): "Validate bounded, hashed, labelled artifacts; preview musical metadata; select an exact target; propose insertion; verify Apply and Undo." — the artifact gate the MIDI providers feed.
- **B4 — Optional integrations** (line 2374): the provider slots this lane serves — "Audio-to-MIDI, reference suggestions, AudioGen, SLO and offline AutoMix remain separate typed artifact providers with unavailable states"; generation needs "explicit opt-in and license/provider review"; names "local whisper.cpp push-to-talk or Basic Pitch ONNX on bounded instrument clips, one at a time"; and pins this lane's rule: "**Pin code and weight licences separately** and qualify offline operation and resource use."
- **E-codes**: the plan defines E1–E11 explicitly (E1 real-time analysis :2375, E2 grade :2381, E3 help :2416, E4 explain/teach :2420, E5 gate flow :2423, E6 reference library :2427, E7 memory :2432, E8 curriculum :2436, E9 grade reliability :2440, E10 before/after :2444, E11 expert network :2447). The earlier note here — "E1–E4 not located; assumed to be the B4 probes" — was **wrong and is retracted**. The audio-ML rows map to **B4** (providers), **B4 / E6-adjacent** (reference suggestions + local archive search), **B4 support** (beat/timeline helpers) and **E2/E9 research** (mix scoring), matching the aggregate report §3.8.

| Rank | Feature (plan item) | Stack | Licence state | Effort | First step / notes |
|---|---|---|---|---|---|
| 1 | Audio-to-MIDI on bounded clips (B4 names Basic Pitch) | Basic Pitch ONNX (CoreML on macOS) | Clean both sides | **S** | First step: run `nmp.onnx` on one bounded instrument clip and measure wall time + peak RAM on the M3-16 GB unit. |
| 2 | Push-to-talk voice (B4 names whisper.cpp) | whisper.cpp or faster-whisper + large-v3-turbo | Clean both sides | S–M | First step: whisper.cpp Metal on 30 s of speech; pin runtime + weight licences in the notices. Never whisper-timestamped (AGPL). |
| 3 | MIDI artifact pipeline (B3) | Existing artifact provider + Basic Pitch output | Clean | S | First step: confirm the existing artifact validation accepts a Basic Pitch MIDI as a bounded/hashed/labelled artifact. |
| 4 | Reference/material suggestions (B4 "reference suggestions"; E6-adjacent) | LAION-CLAP embeddings + local index (audfprint for dedupe) | CC0 both sides | M | First step: embed 100 local reference files and check nearest neighbours by ear before any copy promises "search". |
| 5 | Separation / target extraction (B4 helpers) | MSST + KimberleyJSN mel-band (vocals) + ZFTurbo BS-RoFormer (bass/drums) | MIT per author statements; MUSDB18-HQ caveat documented | M–L | First step: one 3–4 min track through the BS-RoFormer checkpoint on the M3; measure wall time and peak memory (no published M3 numbers exist). |
| 6 | Beat/downbeat timeline (B4 support) | beat_this `small` | MIT both sides | S | First step: resample with vDSP/torchaudio and call the model without `soxr`; confirm identical beats, keep the call site soxr-free. |
| 7 | Library dedupe/detection (B4) | audfprint | MIT | S | First step: vendor the NumPy script and dedupe a folder of test renders. |
| 8 | AudioGen, opt-in only (B4) | ACE-Step v1 / v1.5 (MIT) primary; DiffRhythm alternate | Apache-2.0 (v1) / MIT (v1.5); DiffRhythm code+DiT Apache-2.0 with VAE and tags unresolved | L | First step: one 30 s render on the M3-16 GB in each candidate's macOS configuration to get a real s/min number; gate behind opt-in + licence review exactly as B4 requires. |
| — | Mix scoring (E2/E9 research) | KENN DSP meters (shipped) + optional AudioBox-Aesthetics research | CC-BY-4.0 (gated) | M/L | No clean music-MOS model exists; keep out of shipped claims. First step: read the AudioBox card + paper before any probe. |

Rows 1–8 and the mix-scoring row mirror the aggregate report §3.8 with this lane's corrections. Effort scale (14 Oct engineering-candidates doc): **S** < 2 days · **M** ≤ 1 week · **L** > 1 week.

## Avoid / gate list (with exact triggering text)

Blocked items first (AVOID); gated items (WATCH) are marked at the end.

- **Demucs v4 weights** — "The model weights are not covered by the MIT license, and are provided only for scientific purposes." (adefossez, 2022-05-23). Mirrors contradict each other (Intel MIT vs repo statement) — do not rely on mirrors.
- **whisper-timestamped** — AGPL-3.0 repo + `dtw-python` GPL v3 dependency.
- **NISQA weights** — CC BY-NC-SA 4.0, plus speech-only. Code is MIT but weights are the blocker.
- **ADTOF** — CC BY-NC-SA 4.0 (repo-wide LICENSE).
- **chromaprint (as a whole)** — "As a whole, Chromaprint should be therefore considered to be licensed under the LGPL 2.1 license."
- **Open-Unmix `umxl`** — "the weights are only licensed for non-commercial use (CC BY-NC-SA 4.0)". `umxhq`/`umx` licence unstated + MUSDB terms.
- **Spleeter weights** — licence statement covers code only; models unstated.
- **MuQ and MERT weights** — CC-BY-NC-4.0 (both).
- **MusicGen, MAGNeT, AudioLDM2, Tango2** — CC-BY-NC(-SA)-4.0 weights.
- **BS PolarFormer** — tops the MSST vocal table (SDR 11.00) but carries no licence statement anywhere in the docs (which have no licence column).
- **viperx/aufr33/TRvlvr/jarredou/anvuew/Sucial checkpoint families** — no licence statement; the MSST author explicitly disclaims authorship of models he did not train.
- **MDX23C first-party code** — repo 404 today; checkpoints unstated.
- **piano_transcription_inference** — archived; no LICENSE file; README claims Apache 2.0 without one; runtime package unlicensed too.
- **MT3 / RMVPE checkpoints** — code licences clean (`magenta/mt3` Apache-2.0; RMVPE Apache-2.0), weights unstated → blocked under "pin code and weight licences separately".
- **musicnn weights** — unstated + Million Song Dataset research terms.
- **Mustango (default)** — tag unread **[?]**; blocked by Tango-family lineage until the card and weights are read.

Gated (WATCH), not blocked: **Stable Audio Open Small** (community licence + revenue terms); **Freesound API without a commercial agreement** (free tier non-commercial and revocable; keys can be revoked); **CC-BY-4.0 rows** (Parakeet, OpenL3, AudioBox-Aesthetics — need an allow-list decision + attribution line); **MS-CLAP** (MS-PL, off-list); and **GPL programs to isolate, not bundle** (espeak-ng for DiffRhythm; madmom only if DBN postprocessing is ever enabled in beat_this).

## Verified vs inferred

**[V] Verified 2026-10-15** (fetched live; takeover-pass additions included): demucs #327 quote; MSST #245/#254 quotes + timelines; MSST `docs/pretrained_models.md` re-fetched (75 lines, no licence column) and all SDR tables re-read; MUSDB README access/academic line + `musdb` package MIT; beat_this LICENSE quote, model sizes, and the inference-time `soxr.resample` call (`inference.py` lines 274–275); ACE-Step v1 LICENSE + v1.5 LICENSE ("Copyright (c) 2026 ACEStep") + HF tags; KimberleyJSN HF tag mit + 913,106,900-byte checkpoint; Basic Pitch sizes via git tree; piano_transcription archived state + README claim + companion repo without licence; MT3 (`magenta/mt3` Apache-2.0; `google-research/mt3` 404); repo metadata for LAION-AI/CLAP (CC0), whisper-timestamped (AGPL + dtw GPL), ADTOF (NC-SA file), NISQA (MIT code, NC-SA weights quote), open-unmix (MIT), spleeter (MIT), torchcrepe (MIT), RMVPE (Apache), swift-f0 (MIT), openl3 (MIT + CC-BY-4.0 README), musicnn (ISC via setup.py), lucidrains BS-RoFormer (MIT), `BSRoformer.cpp` (MIT), audfprint (MIT), chromaprint (LICENSE.md text), AudioBox-Aesthetics ("majority … CC-BY 4.0" + unilm MIT + head semantics + arXiv 2502.05139), microsoft/CLAP (MIT); HF tags for whisper-turbo (mit), whisper-v3 (apache-2.0), lukewys/laion_clap (cc0-1.0 + file sizes), laion/clap-htsat-unfused (apache-2.0), microsoft/msclap (**ms-pl**), Parakeet TDT 0.6B v3 (cc-by-4.0), MuQ/MERT (NC), musicgen/magnet (NC), audioldm2/tango2 (NC-SA), stable-audio-open-small (community+gated), ACE-Step v1 (Apache) and v1.5 + xl-turbo + turbo-continuous (mit), audiobox-aesthetics (cc-by-4.0), YuE s1 (Apache); PyPI for soxr (LGPL-2.1-or-later), faster-whisper (MIT), laion-clap (licence field CC0, classifier quirk), beat-this; whisper.cpp (MIT); Freesound ToS quotes; MAEB title/date/47.9% T2A/22.7% clustering; Omni-Embed-Audio caption-style quote; DAFx arXiv 2607.03806 (CLAP carries LUFS/RT60/SC/RP).

**[R] Reproduced from a previous run's log, not re-fetched**: MrCitron demucs mirror = CC-BY-NC; YAMNet Apache-2.0; melodia GPL; Freesound per-sound CC filtering from platform terms.

**[I] Inferred (not sourced)**: 512-d CLAP / 768-d HTSAT dims; ONNX/CoreML export feasibility for CLAP; M3 timing expectations for all models; YuE 7B+1B memory infeasibility at 16 GB; chromaprint's FFT-library split (vDSP vs FFTW); Basic Pitch weights covered by the repo Apache grant.

**[?] Could not verify / contradictions**: MAEB's "8–14%" and "<3% FLEURS" figures (not re-locatable — previously [V], now [?]); M2D-CLAP licence (unchecked); `jarredou/BS-RoFormer-SW` HF page (401); `lucidrains/mel-band-roformer` repo (404 — prior claim of an MIT lucidrains repo unconfirmed); `kuielab/mdx23c` (404); `microsoft/clap-ms-2023` (401 — the msclap card is the reachable source); INTEL mirror MIT tag observed only indirectly via a thread comment; Mustango tag unread; YAMNet not re-checked.

## Gaps

1. **MUSDB18-HQ chain-of-title** — dataset terms are now read (access by request, "academic purposes only", KQ1); whether they bind commercial use of trained weights is a legal reading, still open. Every MUSDB-trained "MIT" checkpoint (ZFTurbo, Kimberley, open-unmix) carries it. ZFTurbo's own advice: verify on your end.
2. **No published M3 (16 GB) benchmarks** for Demucs/RoFormer/CLAP/whisper/ACE-Step/beat_this; only ACE-Step's M2 Max RTF exists first-party. Every shortlisted model needs an on-machine wall-time and peak-memory measurement.
3. **Freesound commercial terms** are contact-only — no published pricing/limits.
4. **DiffRhythm**: VAE licence, untagged HF checkpoints, `DiffRhythm-1_2B` 401, espeak-ng GPL-3 handling, and the DiffRhythm 2 / DiffRhythm+ licences are all unresolved.
5. **Unresolved licence lookups**: M2D-CLAP (unchecked), MT3 checkpoint (unstated), BS PolarFormer (unstated), 53-stem first-party host (not located), `jarredou/BS-RoFormer-SW` (401), `microsoft/clap-ms-2023` (401), Mustango card (unread), RMVPE / swift-f0 weight terms, YAMNet re-check.
6. **No licence-clean drum transcription or groove model** found; drum separation checkpoints all unstated.
7. **No open music-MOS model with permissive weights**; mix scoring remains KENN-DSP-only plus opt-in research models.
8. **Basic Pitch weight licence** rests on repo-level Apache-2.0 (no separate grant sentence) — worth a one-line confirmation from Spotify if it ships.
9. **CC-BY-4.0 allow-list decision** (Parakeet, OpenL3, AudioBox-Aesthetics) — owner call; the attribution obligation is documented in the master-table note.

## Takeover review — 15 Oct 2026

**What this pass did.** Independent re-verification of every adoption-gating licence claim in this file and of the KQ0 sample, against primary sources fetched live on 2026-10-15 (repo LICENSE files, HF cards/tags, GitHub issue comments and repo metadata, PyPI metadata, the MSST docs tables, the sigsep-mus-db README, arXiv abstracts), plus the plan codes in `KENN_PLAN.md` 2360–2447. This is the reviewed canonical lane-03 note; the aggregate report's §3.6–3.8, §5 and §7 draw from it.

**Corrections made in this pass (15).**

| # | Where | Was | Now |
|---|---|---|---|
| 1 | KQ1 vocals leader | KimberleyJSN 10.98 called the best single-stem vocals entry | BS PolarFormer 11.00 tops the table; no licence statement → AVOID |
| 2 | KQ1 MDX23C | "SDR 7.02 MUSDB / 10.17 vocals" as one blob | two rows: MUSDB18HQ 4-stem MUSDB 7.15 / Multisong 7.02; vocals model 10.17 (Multisong) |
| 3 | KQ1 SCNet XL IHF | "MUSDB avg 9.80–10.08" | MUSDB test avg 10.08 / Multisong 9.92 |
| 4 | KQ0.9 + KQ3 MAEB | "8–14%" CLAP retrieval and "<3% FLEURS" quoted as fact | not re-locatable → **[?]**; verified: 53 encoders, 22.7% best clustering, M2D-CLAP T2A 47.9% |
| 5 | KQ3 MS-CLAP | weights "unresolved" (401) | **ms-pl** on HF `microsoft/msclap` (three checkpoints sized); `clap-ms-2023` still 401 → WATCH |
| 6 | KQ2 piano_transcription | "no licence at all" | archived; no LICENSE file (spdx null); README claims Apache 2.0; runtime package none → AVOID stands |
| 7 | KQ2 MT3 | "code Apache-2.0 (API)" | `google-research/mt3` 404s today; current repo `magenta/mt3` Apache-2.0; checkpoint licence still unstated |
| 8 | KQ5 ACE-Step v1.5 | "licence not verified" | **MIT** verified (LICENSE + README + HF tags; vendor commercial-use claim noted) |
| 9 | KQ4 soxr | inference-time role "not inspected" | confirmed: `beat_this/inference.py` lines 274–275 call `soxr.resample(signal, in_rate=sr, out_rate=22050)` |
| 10 | KQ6 chromaprint FFT | "vDSP fine; FFTW would make it GPL" | LICENSE.md names neither; the split was our inference → **[I]**; LGPL-as-a-whole finding stands |
| 11 | KQ7 AudioBox | head semantics "verify before use [I]" | CE/CU/PC/PQ verified against card + paper; licence = "majority … CC-BY 4.0" with unilm portions MIT |
| 12 | Shortlist mapping | "E1–E4 not located; assumption" | E1–E11 defined at `KENN_PLAN.md` 2375–2447; rows re-labelled B4 / B4+E6-adjacent / B4 support / E2/E9 research |
| 13 | KQ1 MUSDB | dataset terms "never fetched" | read: access by request, "academic purposes only" (quote in KQ1); `musdb` package MIT; chain-of-title grounded |
| 14 | KQ5 DiffRhythm | flat "Apache both sides" | README quote stands for code+DiT; HF checkpoints untagged; 1_2B 401; VAE unstated → WATCH; successors unreviewed |
| 15 | KQ5 Mustango | "not verified → blocked by family" | card carries an apache-2.0 tag only **[?]**; stays blocked by default |

**Verdict changes this pass**: MS-CLAP blocked → **WATCH** (MS-PL found); ACE-Step v1.5 unverified → **ADOPT** (MIT); new rows: Parakeet **WATCH** (CC-BY-4.0), BS PolarFormer **AVOID** (unstated), M2D-CLAP **WATCH** (licence unread), Mustango **AVOID** (default). Stable Audio Open and Freesound re-labelled **WATCH** (gated) in the same three-tier vocabulary the aggregate uses. Everything else keeps its tier.

**Remaining [?]**: MUSDB-trained-weight commercial reading (legal); M2D-CLAP licence; MT3 checkpoint; BS PolarFormer; 53-stem first-party host; jarredou HF 401; clap-ms-2023 401; Mustango tag; RMVPE/swift-f0 weight terms; YAMNet re-check; MAEB percentages; Freesound commercial terms; no M3-16 GB timings; Basic Pitch weights grant (reading).

**Owner decisions this lane surfaces**: (a) widen the allow-list for CC-BY-4.0 (Parakeet, OpenL3, AudioBox) or keep them research-only; (b) commission the MUSDB chain-of-title legal read; (c) approve the soxr substitution approach in beat_this — the same question is already tracked in the E2 meter path (`KENN_PLAN.md` line 2388); (d) one-line Basic Pitch weights confirmation from Spotify if it ships; (e) whether MS-CLAP (MS-PL) is worth pursuing as a CLAP alternative; (f) accept the corrected E-mapping above.
