# KENN SEAL source audit — 2026-10-13

Exactly 20 existing local notes were checked and corrected. Seventeen are primarily backed by the official Live 12 manual; three combine manual controls with service or engineering references and studio workflow. All 20 now carry `factual-owner-review-pending`, rights `unknown`, shared-weight training permission `unknown` and derived-target approval `pending`. This audit provides factual evidence for review; it does not grant any of those approvals.

The corrections affect the ignored main note library only. Exact before and after bytes, source responses, receipts and five numbered four-note review packets are in the new ignored product directory `.runtime/seal-specialist-source-audit-resume-2026-10-13/`. The old frozen inventory and earlier audit receipts remain unchanged. No training, model download, dependency change, Live access or production index update formed part of this audit.

## Inventory reconciliation before editing

The full frozen inventory was reconciled by filename and exact SHA-256 before any note correction. The frozen `ableton_note` flag and the presence of `ableton` in a filename are distinct classifiers. The 229 filename-only matches were already present in the frozen 807-note library.

| Measure | Count |
| --- | ---: |
| Frozen notes / current pre-edit notes | 807 / 807 |
| New / missing filenames | 0 / 0 |
| Pre-edit hashes differing from frozen | 0 |
| Frozen Ableton classification flags | 118 |
| Current filenames containing `ableton` | 347 |
| Both classifiers | 118 |
| Filename match without frozen flag | 229 |
| Frozen flag without filename match | 0 |
| Corrected / untouched after this audit | 20 / 787 |

Frozen inventory SHA-256: `82450baa6c9e0dbe5395475444c31f370638bb0804fa09b978a3d0ff72c48170`. The local `inventory-before.json` records all 807 names, before hashes and classifier memberships; `frozen-metadata-before.json` fixes the hashes of 22 earlier evidence files. The classifications were reconciled, not rewritten.

## Primary sources and applicability

Ableton source checks used the current online **Live 12** manual on 2026-10-13. This is a major-version reference, not an attestation of an installed point release. No Live device parameter enumeration or API probe was performed. The export formats, Limiter modes and UI labels therefore require installed-build review before any executable instructions are approved. Studio presets and listening diagnoses are labeled separately from manual facts.

| Primary reference | Scope | Local response evidence |
| --- | --- | --- |
| [Live 12 audio effects](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/) | Utility, Compressor, Glue, EQ Eight, Delay, Filter Delay, Reverb, Hybrid Reverb and Limiter | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Live 12 warping](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/) | Warp algorithms, markers and save behavior | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Live 12 mixing](https://www.ableton.com/en/live-manual/12/mixing/) | Mixer meters and return routing | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Live 12 Audio Fact Sheet](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/) | Conditional neutrality, summing precision and freezing | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Live 12 export](https://www.ableton.com/en/live-manual/12/managing-files-and-sets/) | Selection, encoding and dither | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Live 12 automation](https://www.ableton.com/en/live-manual/12/automation-and-editing-envelopes/) | Arrangement envelope editing | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Live 12 clip envelopes](https://www.ableton.com/en/live-manual/12/clip-envelopes/) | Session automation versus clip modulation | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Spotify loudness normalization](https://support.spotify.com/us/artists/article/loudness-normalization/) | Current playback normalization and master recommendations | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Spotify audio file formats](https://support.spotify.com/us/artists/article/audio-file-formats/) | Native delivery formats | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [Apple Digital Masters brief](https://www.apple.com/apple-music/apple-digital-masters/docs/apple-digital-masters.pdf) | Original 24-bit PCM and highest native sample rate; April 2021 brief | Exact HTML/PDF bytes and SHA-256 in `source-registry.json` |
| [DPA polarity, phase and delay](https://www.dpamicrophones.com/mic-university/technology/polarity-phase-and-delay/) | Manufacturer definitions of polarity, phase and delay | Official web-reader inspection; direct download returned HTTP 403, so no response-byte hash is claimed |

Ten source responses were saved locally and hashed. DPA is the sole reader-only source. These snapshots establish what was checked; they do not establish reuse rights. The Apple brief is service-specific and is not a specification for every streaming destination.

## Exact candidate list, corrections and evidence

Numbers below are the same as the local packets. Pages 1–5 contain records 1–4, 5–8, 9–12, 13–16 and 17–20 respectively. `manual-primary` means the main device or workflow facts are grounded in the Live 12 manual; it does not turn optional studio advice into manual requirements.

### 1. `ableton-utility-device.md`

Page 1; family `utility-stereo`; manual-primary. Classification: manual facts with explicitly labeled studio choices.

Width above 100% widens stereo; side-only isolation belongs to Mid/Side mode at 100S, not Width at 400%. Bass Mono and a polarity flip cannot promise removal of existing cancellation; peak and crossover presets are studio choices. [Live 12 audio effects — utility](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#utility).

Before: `bd73c1683cb9d06d7ef7d20b38f17cf61365de550f6537b9cce1f9c74a1561e4` (2552 bytes). After: `431006e4fd166d755ef0f8a8c610dedc725d5d02baf45794abf72e14d8f5f696` (2154 bytes).

### 2. `ableton-warp-modes-and-transient-smearing.md`

Page 1; family `warp-modes`; manual-primary. Classification: manual facts; artifact diagnosis is a listening hypothesis.

Removed the claim that smearing almost always proves a mismatched mode and that Complex Pro guarantees the least smearing. Beats Transient Envelope is a volume fade, not Grain Size; additional markers change timing and do not guarantee sharper attacks. [Live 12 warping — warp modes](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/#warp-modes), [Live 12 warping — beats mode](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/#beats-mode), [Live 12 warping — complex and complex pro mode](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/#complex-and-complex-pro-mode).

Before: `4f7c3b32e27dd5db17ea7b62bab84947f0fb4cb43b13a833d5aeea96333eb6b5` (2312 bytes). After: `de39b6916480994a19be804e79d5c63b9de0fa469e65851e770ab1d8265bac91` (2466 bytes).

### 3. `ableton12-warp-algorithms-and-transient-preservation.md`

Page 1; family `warp-modes`; manual-primary. Classification: manual facts with optional material-specific comparisons.

Formants affects transposed samples; it does not repair untransposed vocals or preserve dynamics. Envelope default 128 is a tonal control position, not a transient-preservation guarantee; added Re-Pitch pitch coupling. [Live 12 warping — warp modes](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/#warp-modes), [Live 12 warping — complex and complex pro mode](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/#complex-and-complex-pro-mode).

Before: `8a8cef53b2fb6da5c93b6de3fa2a2f711a0b333ff9b053796e635520b71e4087` (2087 bytes). After: `8db7d0ce825d2a28086d187b65c15482f3525a63712d81ad7f59421d5a60f075` (2360 bytes).

### 4. `ableton12-return-tracks-and-parallel-send-routing.md`

Page 1; family `return-routing`; manual-primary. Classification: manual facts with optional parallel-effects workflow.

Return-send enabling applies to return-to-return feedback, not ordinary track sends; feedback is optional and disabled by default for level safety. Pre/Post belongs to the receiving return and controls source tapping before/after pan, volume and track-active; pre-fader is not required for parallel effects. [Live 12 mixing — return tracks and the main track](https://www.ableton.com/en/live-manual/12/mixing/#return-tracks-and-the-main-track), [Live 12 audio effects — delay](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#delay).

Before: `1e8ca31133bc8d8184608a55b90859dfbda6ca22b275065162ea48628b4faf48` (1902 bytes). After: `3051617c7d1638ce81066f9c5f9ea9ed400ab079f9fc8a5cd7389ad199a8e6d4` (2303 bytes).

### 5. `sends-and-returns-in-ableton.md`

Page 2; family `return-routing`; manual-primary. Classification: manual routing facts; EQ/compression choices are studio heuristics.

Separated routing facts from claims of inevitable CPU/cohesion benefits and from frequency presets. Located Pre/Post on receiving return; clarified feedback is optional. [Live 12 mixing — return tracks and the main track](https://www.ableton.com/en/live-manual/12/mixing/#return-tracks-and-the-main-track), [Live 12 audio effects — delay](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#delay), [Live 12 audio effects — hybrid reverb](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#hybrid-reverb).

Before: `7313266e5f3cd1731560f15c775cd23485ae11b829bb709d3b107b7dbdf36a74` (1918 bytes). After: `f42e8bd86610191a69f80bc8e72d2e7077aac6c9112182193211e8087adf9534` (2138 bytes).

### 6. `ableton-mixing-and-gain-staging.md`

Page 2; family `mixer-engine`; manual-primary. Classification: manual facts; no prescribed input peak target.

Removed an unsupported 60 dB fader-range claim and duplicate Approved block. Distinguished 32-bit internal processing from 64-bit single-point summing and output clipping boundaries. [Live 12 mixing — the live mixer](https://www.ableton.com/en/live-manual/12/mixing/#the-live-mixer), [Live 12 mixing — return tracks and the main track](https://www.ableton.com/en/live-manual/12/mixing/#return-tracks-and-the-main-track), [Live 12 Audio Fact Sheet — summing at single mix points](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/#summing-at-single-mix-points).

Before: `a855d9fad2c34b29eec1c31bb38cea4b8d5a18063862de88851135f2f3199441` (1927 bytes). After: `30fa45f5834b4f87771c827201b0ef68a7cfe3077c7f4805c666a250cd9cd3df` (2144 bytes).

### 7. `ableton12-mixer-gain-staging-and-headroom.md`

Page 2; family `mixer-engine`; manual-primary. Classification: manual engine facts; gain staging is material-dependent.

Removed universal -12 dB fader preset and claim the Main fader inherently maintains unity. Clarified 64-bit summing/32-bit processing and excluded arbitrary summing-bus overload warnings. [Live 12 mixing — the live mixer](https://www.ableton.com/en/live-manual/12/mixing/#the-live-mixer), [Live 12 Audio Fact Sheet — summing at single mix points](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/#summing-at-single-mix-points).

Before: `b7157f0486eb62764fcbae8b26eef3c46ad84d420da5d2894960b7246841a4d4` (1786 bytes). After: `67b89aa1fcc0f78d6ef76818825209010f8f5d8a786eea377c74a25c0dbb5514` (2089 bytes).

### 8. `ableton-audio-fact-sheet-neutral-operations.md`

Page 2; family `mixer-engine`; manual-primary. Classification: manual-defined conditional neutrality.

Changed summing precision from 32 to 64 bits at each mix point while retaining 32-bit internal processing. Warp neutrality requires unstretched playback at the original tempo; removed blanket neutrality and pan-law claims. [Live 12 Audio Fact Sheet — neutral operations](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/#neutral-operations), [Live 12 Audio Fact Sheet — summing at single mix points](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/#summing-at-single-mix-points), [Live 12 export — encoding options](https://www.ableton.com/en/live-manual/12/managing-files-and-sets/#encoding-options).

Before: `70d2d145fc0a0f67f7932f3a1be9d09928bb873107926a9dec83dbafb5c6a3aa` (1896 bytes). After: `5c5304b2f2c2d1336e45d2e909ecd9641962aaf25878c02a58d98866503216f9` (2416 bytes).

### 9. `ableton-compressor-device.md`

Page 3; family `dynamics`; manual-primary. Classification: manual modes and controls; numerical presets are studio choices.

Expand acts above threshold rather than expanding quiet signals below it; Peak/RMS/Expand are operating modes, not three envelope shapes. Corrected Lookup knee to Knee; removed claim lookahead prevents overshoot clicks and low-end distortion equals clipping. [Live 12 audio effects — compressor](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#compressor), [Live 12 audio effects — sidechain parameters 1](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#sidechain-parameters-1).

Before: `8efe655016ecc13e3be6d840abf7aa2e0a84e95a50e21d5113b62325c9799792` (2675 bytes). After: `2a8a251e1a01ee77f0fb71c59fd726cf8d00efbae52cab4ee93691040621141d` (2271 bytes).

### 10. `ableton-glue-compressor-device.md`

Page 3; family `dynamics`; manual-primary. Classification: manual controls and Soft clip limitations; bus settings are heuristics.

Removed unsupported named SSL/transistor identification and a separate Sidechain HP Filter control. Soft clip is a colored fixed waveshaper, not a transparent peak limiter; oversampling can still allow peaks above 0 dBFS. [Live 12 audio effects — glue compressor](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#glue-compressor), [Live 12 audio effects — context menu options for glue compressor](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#context-menu-options-for-glue-compressor).

Before: `526182065d5c4c7be9e76c24ac0b215a577e8035697aa499c676f0715ec2ea08` (2557 bytes). After: `7458feed50894d2e6f33a787614b37cc180f11178aa869d1c1015af20ba68813` (2229 bytes).

### 11. `ableton-eq-eight-device.md`

Page 3; family `equalization`; manual-primary. Classification: manual UI facts; historical API measurements excluded.

Edit selects L/R or M/S channel curves; the manual does not establish automatable parameter names, count, order or index values. Removed unverified historical Live 12.4.6 API readout from current factual guidance; exact original remains in before snapshot. [Live 12 audio effects — eq eight](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#eq-eight).

Before: `9ac95b9b8648d4b13aff338196dbd7f29be63950a55061b2b5f1be74c63916ad` (2525 bytes). After: `f9d3753122961423501c8cd5024296c07ea869c8a64aabd00659e95e5089a87e` (1942 bytes).

### 12. `ableton-delay-and-reverb-devices.md`

Page 3; family `time-effects`; manual-primary. Classification: manual controls; spectral/timing choices are studio heuristics.

Correct mode name is Repitch, not Pitch; Jump can click while changing a decaying delay, not invariably. Separated Reverb Spin early-reflection diffusion from Chorus tail modulation; removed universal CPU and frequency-preset claims. [Live 12 audio effects — delay](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#delay), [Live 12 audio effects — filter delay](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#filter-delay), [Live 12 audio effects — reverb](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#reverb).

Before: `38aa731481fee6af270e101a54c630dada8df9cc5ecc490f0825731d4ad22159` (2844 bytes). After: `08b857d2c945f30e57a149e5544c18744759f1a0d7da9e645dab2398ae264985` (2321 bytes).

### 13. `ableton-hybrid-reverb-device.md`

Page 4; family `time-effects`; manual-primary. Classification: Live 12 manual routing facts; optional reverb choices.

Replaced Live 11 citation with the checked Live 12 section; removed unsupported Abbey Road name attribution. Blend operates only in Serial/Parallel; EQ defaults after both engines and Pre Algo places it before algorithm, not necessarily before all input processing. [Live 12 audio effects — hybrid reverb](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#hybrid-reverb), [Live 12 audio effects — signal flow](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#signal-flow), [Live 12 audio effects — eq section](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#eq-section).

Before: `431140095dc79cf8f567c50b8f03a73781e628f1cfd490c10d6674200885e087` (2652 bytes). After: `9439b56225b45ff411b9e438bab03ef338e71001eec5798952ca42efffa8b18a` (2206 bytes).

### 14. `clip-automation-basics.md`

Page 4; family `automation`; manual-primary. Classification: manual automation/modulation distinctions.

Session Clip View allows automation or modulation; Arrangement Clip View supports modulation while Arrangement automation lives on track lanes. Separated Draw Mode steps from individual breakpoint editing. [Live 12 automation — drawing and editing automation](https://www.ableton.com/en/live-manual/12/automation-and-editing-envelopes/#drawing-and-editing-automation), [Live 12 clip envelopes — the clip envelope editor](https://www.ableton.com/en/live-manual/12/clip-envelopes/#the-clip-envelope-editor).

Before: `2e013da4bc86bda2ff3e1c0d8182efd3c4816b92ae65255a2d7babcaaccadbb0` (1111 bytes). After: `75661ac09672473c9f449850b5a60115aff6ae1115cef99bb7f511f2da3f9104` (1959 bytes).

### 15. `exporting-stems-and-mixdowns.md`

Page 4; family `export-delivery`; manual-primary. Classification: manual rendering facts with first-party service delivery exceptions.

Current Live 12 manual explicitly supports native FLAC export; removed external-converter requirement. Main is current Rendered Track label; Render Start/Length define range, and 16-bit/44.1 kHz is not universal streaming delivery. All Individual Tracks also includes groups, returns and Main; their sum need not recreate Main and effects inclusion must be deliberate. [Live 12 export — exporting audio and video](https://www.ableton.com/en/live-manual/12/managing-files-and-sets/#exporting-audio-and-video), [Live 12 export — encoding options](https://www.ableton.com/en/live-manual/12/managing-files-and-sets/#encoding-options), [Spotify audio file formats — official guidance](https://support.spotify.com/us/artists/article/audio-file-formats/), [Apple Digital Masters brief — official guidance](https://www.apple.com/apple-music/apple-digital-masters/docs/apple-digital-masters.pdf).

Before: `b14d21cabdd56e302a9a842c7eaacbf4bde8114ed0e0c79895fc8e515bce54f9` (2388 bytes). After: `e05a815058e83c2cdc775c24911131c544b7c90bc9c14ffcd5518a30beace964` (2851 bytes).

### 16. `warp-markers.md`

Page 4; family `warp-modes`; manual-primary. Classification: manual marker editing; density preference is a studio heuristic.

Specified upper half of Sample Editor for double-click creation rather than vague above-waveform location. Marker density is not a guarantee of naturalness or transient quality; distinguished automatic Set save from sample defaults. [Live 12 warping — warp markers](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/#warp-markers), [Live 12 warping — saving warp markers with a sample file](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/#saving-warp-markers-with-a-sample-file).

Before: `3acd0d4ac6e59a3901369618998f8585517a63dd9994035f6e2e870452bbfc42` (939 bytes). After: `ea421e18fcb27fe00d1cb7706f82c5316dd9fe0ee96bce84efb649a21d7a5c4a` (1865 bytes).

### 17. `gain-staging-basics.md`

Page 5; family `mixer-engine`; mixed primary evidence; excluded from manual-primary count. Classification: mixed manual engine facts and studio gain workflow.

Fixed peak/fader targets and compulsory unity Main export are not documented requirements. Freeze is not a Main-fader print; separated input/output boundaries and subjective workflow. [Live 12 mixing — the live mixer](https://www.ableton.com/en/live-manual/12/mixing/#the-live-mixer), [Live 12 Audio Fact Sheet — summing at single mix points](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/#summing-at-single-mix-points), [Live 12 audio effects — utility](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#utility), [Live 12 Audio Fact Sheet — freezing tracks](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/#freezing-tracks), [Live 12 export — exporting audio and video](https://www.ableton.com/en/live-manual/12/managing-files-and-sets/#exporting-audio-and-video).

Before: `76c067f09f7aa4acd9fff6f918915024626357fcbbab4b583a6681c7a7530b1f` (1273 bytes). After: `8029576f1b23a75739d13bbd529c434e9b8b26663b150e7d7efebb6853d33d60` (2517 bytes).

### 18. `sample-rate-bit-depth-dither.md`

Page 5; family `export-delivery`; manual-primary. Classification: manual export facts; native-rate workflow and service specifics.

Intermediate 24-bit exports are word-length reduction from Live processing; no-dither at every 24-bit intermediate is not a blanket rule. Separated a 32-bit further-processing recommendation from delivery-specific fixed-depth choices and removed universal 44.1/48 kHz prescriptions. [Live 12 export — encoding options](https://www.ableton.com/en/live-manual/12/managing-files-and-sets/#encoding-options), [Live 12 Audio Fact Sheet — recording internal sources at 32 bit](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/#recording-internal-sources-at-32-bit), [Apple Digital Masters brief — official guidance](https://www.apple.com/apple-music/apple-digital-masters/docs/apple-digital-masters.pdf).

Before: `d7417536c5399467183b91018f0badd7fcdc716900b10075811db0e8d2c56732` (1435 bytes). After: `fceb90946491a964213bf5a6eb7d69e0fa98c23272f0ea699329b569285ce21b` (2413 bytes).

### 19. `mastering-streaming-loudness.md`

Page 5; family `streaming-loudness`; mixed primary evidence; excluded from manual-primary count. Classification: first-party service guidance plus Live 12 device facts; chain is heuristic.

-14 LUFS is Spotify-specific normal playback guidance, not a universal platform acceptance requirement. A ceiling value alone is not a true-peak guarantee: current Live Limiter has a separate True Peak mode; Spotify recommends below -2 dBTP for masters louder than -14 LUFS. Removed claim that these studio settings describe owner deliveries; no owner delivery evidence was inspected. [Spotify loudness normalization — official guidance](https://support.spotify.com/us/artists/article/loudness-normalization/), [Spotify audio file formats — official guidance](https://support.spotify.com/us/artists/article/audio-file-formats/), [Live 12 audio effects — limiter](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#limiter).

Before: `1e07a4565a9ed8d57995352fd394ae18c9560db69036e0293374bec8fb96d6c6` (1495 bytes). After: `8424218a5510cc45c28548107ff20804b4e028b00bc50f1db283a3ad41c5a812` (2308 bytes).

### 20. `phase-and-polarity-checks.md`

Page 5; family `utility-stereo`; mixed primary evidence; excluded from manual-primary count. Classification: manufacturer signal definitions plus Live controls; listening workflow is heuristic.

Polarity inversion changes sign, not arrival time; it is not a general fix for phase/timing errors. Making sub mono does not guarantee cancellation is fixed; timing edits and fuller-sounding choice remain listening heuristics. [DPA polarity, phase and delay — official guidance](https://www.dpamicrophones.com/mic-university/technology/polarity-phase-and-delay/), [Live 12 audio effects — utility](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/#utility).

Before: `f7fc1e954864a2e3b7c0869c558c3ba342373a1feafd43bb73129358e62377eb` (1338 bytes). After: `bc1687a038b5fd522bb204689e68ddfabe2c9d9c18fb27fcdd64445639888092` (2318 bytes).

## Boundaries for later specialist drafts

The corrected text is the factual draft source. The preserved before files are historical evidence and must not be copied back into draft guidance. In particular, the former EQ Eight note’s alleged Live 12.4.6 API count, names, order, indices and ranges have no matching measurement receipt in this audit. Those assertions were removed from current guidance, and the note now explicitly separates manual UI behavior from unverified historical measurements.

The 20 notes form ten overlapping source families. Any later split must keep facts about the same device or workflow together; filename disjointness alone cannot demonstrate independence. This grouping is a human semantic review aid, not a measured leakage clearance.

| Source family | Audit records | Draft factual focus |
| --- | --- | --- |
| Utility and stereo | 1, 20 | Width versus side isolation; polarity versus delay; limits of mono checks |
| Warp modes and markers | 2, 3, 16 | Beats controls; transposition-dependent Formants; marker timing and save scope |
| Return routing | 4, 5 | Normal sends versus feedback enabling; receiving return Pre/Post tap |
| Mixer and numerical engine | 6, 7, 8, 17 | Peak/RMS meters; 32-bit processing versus 64-bit single-point summing; conditional neutrality |
| Dynamics | 9, 10 | Compressor operating modes versus envelope shapes; Glue Range and Soft clip limitations |
| Equalization | 11 | EQ Eight manual curve editing; no unsupported API assertions |
| Time effects | 12, 13 | Delay transitions; Reverb modulation; Hybrid Reverb routing and EQ position |
| Automation | 14 | Arrangement lanes versus Session automation/modulation |
| Export and word length | 15, 18 | Render selection; native formats; intermediate precision; final dither |
| Streaming loudness | 19 | Service-specific normalization and delivery; Limiter mode boundary |

Cross-family review must also account for shared gain facts (Utility/mixer), wet return processing (routing/time effects), limiting (dynamics/streaming) and delivery/dither (export/streaming). No owner style packet, adapter examples, reward labels or shared-weight permission was created here.

## Verification and review artifacts

Run the local scoped check from the main checkout:

```sh
python3 products/kenn/.runtime/seal-specialist-source-audit-resume-2026-10-13/verify_audit.py
```

The check verifies the 807-note denominator, all saved before/after bytes, exactly 20 changed files and 787 untouched files, all review-state fields, 11 primary sources with 10 exact response snapshots, every cited manual fragment, unchanged hashes of 22 earlier evidence files, and all five four-note packets. It also rejects the removed EQ parameter appendix in corrected guidance. `verification.json` records the successful run and the hashes of the audit receipt and source registry.

Local artifacts under the new runtime directory:

- `before/` and `after/`: 20 exact byte snapshots each.
- `note-audit-receipt.json`: all 20 findings, references, classifications, hashes, historical metadata and explicit absent owner approvals.
- `inventory-before.json` and `frozen-metadata-before.json`: reconciliation and unchanged-old-evidence checks.
- `source-registry.json` and `primary-source-snapshots/`: source URLs and retrieval evidence.
- `review-packets/01-source-audit.md` through `05-source-audit.md`: four numbered records per page, full hashes, references, version scope and approval fields.
- `verify_audit.py` and `verification.json`: repeatable local evidence checks and resulting receipt.

Factual owner review remains pending for all 20 exact after hashes. Rights, shared-weight reuse and any newly derived target approval must be recorded separately before those inputs cross an approval gate.
