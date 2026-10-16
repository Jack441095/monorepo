# Teaching/grading foundations and product patterns for a local mix-education assistant

Lane 04. Research date: 15 October 2026. Re-run of the lane destroyed by the ~12:28 runtime restart; all previous conclusions re-verified against primary sources where reachable. A same-day takeover review pass then re-checked every licence and standard value that gates a decision — its corrections are recorded in the dated entries in §1, §2, §3, §5, §6, §10 and §11.

Marker convention: `[V]` verified against the cited URL/API on 15 Oct 2026 · `[R]` carried from the 14 Oct docs or the earlier 15 Oct pass without re-opening · `[I]` inferred · `[?]` unverified / not reproducible.

Context: KENN is a closed-source, local-first assistant for Ableton Live. This lane covers the education/grading layer (KENN_PLAN E1–E11): datasets and papers for mix critique, citable grading conventions, teaching-tooling OSS, spaced repetition, and product UX patterns.

Headline claims (details per section below):

1. MixAssist (COLM 2025, arXiv 2507.06329) is the best phrasing reference: 431 turns, 12 producers, fine-tuned Qwen top-ranked in 50.4% of judge evaluations. Two cc-by-4.0 Zenodo records exist, not one; the Hub datasets and one fine-tuned model repo declare no licence (§1). [V]
2. MED is on HuggingFace, not Zenodo, and the live mirror declares no licence; only the DAFx-17 six-song CC BY 4.0 subset is citable (§1). [V]
3. Only loudness/peak claims have open citable standards (EBU R128 family / Tech 3343, AES TD1006 and TD1008). Headroom, mono-compat thresholds and gain staging are house rules and must be labelled as such (§2). [V]
4. Teaching OSS shortlist for E8: music21 (BSD-3, corpus caveat), partitura (Apache-2.0), tonal (MIT per npm), VexFlow (MIT per file text; API detector disagrees), and the MIT FSRS stack. No open mixing curriculum exists; permissive ear-training projects are thin and stale. "OpenEar" and "fet/pure-ear" failed re-verification and are dropped (§3, §8). [V]
5. FSRS ecosystem is uniformly MIT; ship-clean. Correction: fsrs 6.3.2 was uploaded 2026-08-09, not "fresh 14 Oct" (§4). [V]
6. 0–100 grading with written reasoning is now shipped by competitors: Rate My Song AI and TrackScore.AI both score a bounced stereo file and write measurement-referenced feedback; TrackScore adds a conversation grounded in the user's own measurement history. The earlier "no product ships a numeric grade out of 100" finding is falsified. None of them found ships: grading a live DAW session, a public standard-vs-house-rule taxonomy, or a curriculum. The differentiator narrows to in-session, source-labelled, teaching-first grading (§5, §9). [V]
7. Output Co-Producer's earlier quotes ("listens, curates & lets you decide"; "AI should power your workflow, but not make choices for you") and the "Re-imagine 2.0 shipped 16 Sep 2026" date failed re-verification — the page is client-rendered and yields no body text to non-JS or archived fetches. Replacements: page title + meta description (raw HTML) and Output's company line via MusicRadar ("support human artistry, never replacing it"); Re-imagine dates to July 2025 (§5). [V]
8. Staleness deltas vs the 14 Oct docs are in §6; both grade products are missing from that comparable-products table entirely. [V]

## §1 Mix-feedback datasets and papers

### MixAssist — the phrasing reference

- **Paper:** "MixAssist: An Audio-Language Dataset for Co-Creative AI Assistance in Music Mixing", Michael Clemens & Ana Marasović, arXiv 2507.06329v1, submitted 8 Jul 2025, published at COLM 2025. Licence CC BY 4.0 (arXiv licence line re-checked 15 Oct 2026). [V]
- **Shape:** 431 audio-grounded expert responses from 7 one-hour sessions with 12 producers (two participants swapped roles, so 14 pairings across 7 sessions). Each instance is a prior-session summary plus the dialogue up to the amateur's last utterance plus the audio segment being discussed; the target is the expert's reply. Splits: 241 train / 34 dev / 156 test; the two held-out test sessions are ID 5 Hard Rock (the shortest session) and ID 2 Pop Rock (the second-longest), so evaluation runs against unseen producer pairs. [V]
- **Results:** fine-tuned Qwen-Audio-Instruct-7B achieved the top rank in 50.4% of LLM-as-judge evaluations against fine-tuned LTU and MU-LLaMA (listwise ranking; judges gemma3:4b, qwen3:8b, llama3.1:8b, o3-mini). Human check: 10 producers, 100 comparisons — the fine-tuned Qwen reply was preferred 40% of the time, the original human expert 33%; the paper calls this preliminary. [V]
- **Real-time study:** 10 producers, ~5 minutes each; 70% rated the interaction "Somewhat/Very natural", 70% got ideas they had not considered, and 60% rated their own creative contribution higher than the agent's. The named limits: audio-analysis depth and suggestion creativity. [V]
- **Design lessons the paper states outright:** producers want an "explainable teacher and assistant", feedback shown visually inside the DAW, and guidance that stays on the right side of creative control. Attribution and consent around training data were raised without prompting. That is the E4 brief in external words. [V]
- **Code:** github.com/mclemcrew/MixAssist — MIT (GitHub API), 19★, last push 2026-07-24. The repo carries a reconstructed training pipeline: the original fine-tuning script was lost; the reconstruction matches the original release in side-by-side evaluation but the weights are not bit-identical. [V]
- **Trained artefacts:** LoRA adapter `mclemcrew/Qwen2-Audio-MixAssist-LoRA` is apache-2.0 (HF API: created 2026-07-24), base `Qwen/Qwen2-Audio-7B-Instruct` apache-2.0 — the only licence-clean MixAssist artefacts found. Card details: QLoRA 4-bit nf4, r=8, α=32, dropout 0.05, LR 2e-4, ~11 minutes on one GB10, final eval loss 2.81. Decode with sampling plus repetition_penalty=1.1 — greedy decoding loops. [V]
- **Data on the Hub:** `mclemcrew/MixAssist` (created 2025-03-13; 39 downloads, 5 likes) and `mclemcrew/MixParams` (created 2024-06-02; 40 downloads, 2 likes). Both declare **no licence** (HF API re-pulled 15 Oct). A fine-tuned model repo, `mclemcrew/Qwen-Audio-Mix-Instruct`, also declares **no licence** (created 2025-03-16; 17 downloads, 0 likes). All three: reading material only, never shipped content. [V]
- **Raw audio/transcripts — two Zenodo records, both cc-by-4.0 (Zenodo API re-pulled 15 Oct):**
  - 15571750 — the record the paper cites; published 2025-06-02; 47 files; 3,841,882,881 bytes (~3.84 GB). DOI 10.5281/zenodo.15571750. [V]
  - 15848443 — the record the model card cites; published July 2025; 8 files; 2,461,168,869 bytes (~2.46 GB). DOI 10.5281/zenodo.15848443. [V]
- **Correction vs the destroyed run:** the earlier notes recorded only 15848443. The paper itself cites 15571750. Both are cc-by-4.0, so the conclusion holds; the notes must name both. [V]
- **15 Oct takeover review:** HF API re-pulled for all mclemcrew repos plus the Qwen base model — dataset licences null as recorded, LoRA pair apache-2.0 as recorded, and the unlicensed `Qwen-Audio-Mix-Instruct` model repo is new to these notes (now on the §10 no-ship list). Both Zenodo records re-pulled with identical licence, dates and byte sizes. Paper statistics carry from the morning re-run (arXiv HTML read earlier the same day), not re-read in the takeover pass.

### MED — Mix Evaluation Dataset

- Confirmed again: MED is **not on Zenodo**. The live copy is HuggingFace `sparrowreivun/Mix-Evaluation-Dataset-2.0`; created 2026-09-24, last modified 2026-10-05, 907 downloads, 1 like, **no licence declared** (only a `region:us` tag; HF API re-pulled 15 Oct). Recorded size 187.5 GB. [V licence/API; R size — the file listing was not re-summed]
- The DAFx-17 paper (De Man & Reiss, 2017) data-availability text, verbatim: "Six of the ten songs are made available in their entirety under a Creative Commons BY 4.0 license"; "Songs with an asterisk (*) are copyrighted and not available online." [V]
- Listening interface: rd-conx.github.io/med-web — MUSHRA-style A/B with ±1 SE whiskers. [V]
- KENN use: offline calibration and listening-test material, restricted to the six CC BY tracks; never redistribute from the Hub mirror. [I decision]

### Adjacent papers (new this run unless noted)

- **SPHERE** — "SPHERE: Automatic Music Upmixing via Audio Language Model Post-Training with Spatial Heuristic Rewards", arXiv 2608.30559v1, 31 Aug 2026, EMNLP 2026 (Zixun Guo et al.). A deterministic reward suite "inspired by music mixing conventions", six perceptually-motivated sub-rewards that push output mixes to be "centered, balanced and spacious". The task is upmixing, not grading; the transferable claim is that expert domain knowledge can be encoded as verifiable rewards. [V]
- **MEGAMI** — "Automatic Music Mixing using a Generative Model of Effect Embeddings", arXiv 2511.08040v1, 11 Nov 2025, submitted to ICASSP 2026 (Eloi Moliner et al.). Frames mixing as "characterized by subjectivity where multiple valid solutions exist for the same input" and criticizes automatic mixers that treat it as deterministic regression. One-line support for KENN's ranges-and-reasons stance. [V]
- **Sequential Stem Blending** — "Rethinking Automatic Music Mixing as Sequential Stem Blending", arXiv 2608.05506v1, 6 Aug 2026 (Yen Tung Yeh et al.). Models mixing the way engineers work: blending one stem into a growing submix. [V]
- **AI TrackMate** — "AI TrackMate: Finally, Someone Who Will Give Your Music More Than Just 'Sounds Great!'", arXiv 2412.06617v1, 9 Dec 2024, NeurIPS 2024 Creative AI Track (authors Yi-Lin Jiang, Chia-Ho Hsiung, Yen-Tung Yeh, Lu-Rong Chen, Bo-Yu Chen). Training-free pipeline: Music Analysis Module → LLM-Readable Music Report → Music Production-Oriented Feedback Instruction; pilot study with one producer. [V — earlier note credited only "Bo-Yu Chen et al."; full author list now recorded]
- **PardonMix** — CHI EA '26 poster, doi 10.1145/3772363.3798647. Ten professional engineers' parameter vectors; the abstract argues expert disagreement "is not random noise but a structured" signal. Abstract page only; full text paywalled. Keep as a citation stub for the disagreement-is-structured point. [V abstract; ? full text]
- Older, still referenceable: adoption survey arXiv 2304.03407; reference-song communication arXiv 2309.03404; "Semantic Music Production", JAES 2022, doi 10.17743/jaes.2022.0023. [V]

### Net

No public dataset pairs acceptable ranges with explanations. MixAssist is the phrasing set, MED the listening set, SPHERE the reward-design precedent. Nothing here changes E2's structure; all of it supports "measure first, phrase second". [V]

## §2 Citable grading conventions vs house rules

Rule for the whole grading layer: every number KENN prints in a grade or a lever either cites a public document or is labelled a house rule. This section is that audit. Unless marked otherwise, every document below was opened in the takeover pass and the quotes were extracted from the PDF text.

### Citable

| Claim | Source | Verified wording / value | Mark |
|---|---|---|---|
| True-peak ceiling | EBU Tech 3343-2023, tech.ebu.ch/docs/tech/tech3343.pdf | Main text (§3.4, §3.5.1): "The True-Peak Level for generic PCM signals in production shall not exceed −1 dBTP". Appendix 2 (§11.2.3): "The Maximum True-Peak Level in production shall not exceed −1 dBTP. For data reduction systems (like MPEG 1L2 and Dolby AC-3) the limit is −2 dBTP" | [V] |
| Loudness target + tolerances | EBU R 128-2023 (V5, Nov 2023), tech.ebu.ch/docs/r/r128.pdf | "the Programme Loudness Level shall be normalised to a Target Level of −23.0 LUFS"; live programmes ±1.0 LU; ±0.2 LU is the QC measurement tolerance (measurement errors), not a production allowance | [V] |
| Digital alignment level | EBU R68-2000 | Alignment level 18 dB below the maximum possible coding level (ratio 1:8 = 18.06 dB); the earlier 9 dB (or 8 dB) practice is obsolete as a permitted-maximum reference (R 128-2023 recital d) | [V] |
| Downmix convention | EBU Tech 3343-2023 §7.1 | "the EBU recommends the Downmix method Lo/Ro as the default setting for the relevant Metadata parameter ('Preferred Downmix Method')"; surround downmix coefficient is −3 dB by default (vs the +1.5 dB surround weighting in BS.1770 metering) | [V] |
| OTT/OVD content maximum loudness (not a broadcast recommendation) | AES TD1006.1.17-10 (Oct 2017), Annex D Table 3 | Short Form Content: −16 ± 1 LKFS/LUFS maximum (footnote 9: "Not applicable for Japan"); Long Form Content: −16 ± 1 LKFS/LUFS (footnote 8: "Permitted for wide dynamic range Content"); Maximum True Peak: −1 dB TP | [V] |
| Music and speech targets (streaming era) | AES TD1008.1.21-9, 24 Sep 2021, "(supersedes TD1004)" | Track-normalized music −16 LUFS (+0.2 LU); album: "normalize the loudest track of an album to −14 LUFS, per Table 1" — "typically results in an integrated album loudness of -16 LUFS"; speech −18 LUFS (+1 LU when dialog measurable); "Maximum True Peak level not exceed -1 dBTP at the codec input of lossy-encoded streams" | [V] |
| Spotify platform target | Spotify support, "Loudness normalization on Spotify" | "Target the loudness level of your master at -14dB integrated LUFS"; "Keep it below -1dB TP (True Peak) max"; "If your master is louder than -14dB integrated LUFS, keep True Peak below -2dB"; playback normalization to −14 LUFS; albums normalized whole | [V] |

- AES77-2023 exists; the full title is now known from the AES listing: "AES Recommended Practice Loudness Guidelines for Internet Audio Streaming and On-Demand Distribution". Values remain behind the AES paywall — cite the title only, never values we have not read. [V title; ? values]
- ITU-R BS.1770-5 (11/2023), "Algorithms to measure audio programme loudness and true-peak audio level", is the underlying measurement standard referenced by the EBU and AES documents; we rely on their restatements. [V]

### House rules (no open citable source — must be labelled as ours)

- Headroom targets (mix bus, stems): no public standard states them; ours. [I]
- Mono-compatibility and correlation thresholds: only the sign of correlation has a published basis (recorded in the E2 note: 3 of 16 deductions published, 13 house rules); the thresholds are ours. [R]
- Gain-staging baselines (e.g. fader above unity): ours; the 14 Oct E2 work already converted the name/fader-derived ones to advice-only. [R]

### Copy implications for E2–E4

- E2 already carries this split; keep the `source` field on every deduction as the logic moves into E3. [R]
- E3 levers: each one either names its standard ("EBU R128 −23 LUFS") or says "our measured range". [I]
- E4 explanations: cite the standard by name where one exists, otherwise use "we measured" phrasing. Never dress a house rule as a standard. [I]

### 15 Oct takeover review (§2)

- **EBU R 128 version corrected.** The earlier row said "R128 rev 3 (2020)"; the in-force document opened this pass is R 128-2023, V5, November 2023 (history in the PDF: V2 Aug 2011, V3 June 2014, V4 Aug 2020, V5 Nov 2023). The tolerances were also flattened: ±1.0 LU is the live-programme tolerance and ±0.2 LU the QC measurement tolerance — the row now carries both. [V]
- **Tech 3343 attribution sharpened.** "The Maximum True-Peak Level…" phrasing is the Appendix 2 (§11.2.3) form; the main-text forms (§3.4, §3.5.1) are now quoted alongside, and the −2 dBTP data-reduction clause is confirmed verbatim. [V]
- **Downmix row kept, on evidence.** A mid-review worry that "Lo/Ro is the default downmix" was unsupported is dismissed: §7.1 states the EBU "recommends the Downmix method Lo/Ro as the default setting for the relevant Metadata parameter". The row now also carries the −3 dB default surround coefficient so nobody re-reads it as a loudness rule. [V]
- **TD1006 relabelled.** It is the OTT/OVD guideline ("Loudness Guidelines for OTT and OVD Content"), not a broadcast recommendation; Table 3 values (short and long form −16 ±1 LKFS/LUFS, −1 dB TP, Japan footnote) confirmed from Annex D. [V]
- **TD1008 album row made precise.** Loudest track → −14 LUFS (footnote 6, Album Normalization); "typically results in an integrated album loudness of -16 LUFS"; speech carries a +1 LU allowance when dialog is measurable; the true-peak clause is "at the codec input of lossy-encoded streams". [V]
- **Spotify row aligned** to the live page's exact conditions (including the "louder than -14dB → keep TP below -2dB" branch). [V]
- **R68 row widened** with the 1:8 = 18.06 dB ratio and the R 128-2023 recital d) statement that the BS.645 permitted maximum is no longer appropriate. [V]
- **Reference note:** R 128-2023 itself defers production detail to Tech 3343 (lettered recommendation u), so production-level wording should keep quoting Tech 3343, not R 128. [V]

## §3 Teaching tooling OSS

Verified 15 Oct 2026; star counts and push dates via GitHub API, npm where noted. Star counts carry from the morning API batch — the takeover pass re-read raw licence files only (unauthenticated API budget).

| Library | Licence | Vitality | Notes for KENN | Mark |
|---|---|---|---|---|
| music21 | BSD-3-Clause | 2,600★, pushed 2026-10-13 | Theory and score analysis. Corpus caveat verbatim: "Some encodings included in the corpus may not be used for commercial uses or have other restrictions… please see the licenses embedded in individual compositions or directories" — the library is clean, bundled corpora are not automatically | [V] |
| partitura | Apache-2.0 | 377★, pushed 2026-10-11 | Score/performance alignment, symbol maps | [V] |
| tonal (npm) | MIT (npm registry, v6.5.1) | active | Theory primitives in TS/JS. The GitHub API licence field reads null — cite npm, not the API | [V] |
| VexFlow | MIT per LICENSE text (GitHub API reports NOASSERTION because the copyright preamble defeats the detector) | 4,397★, last push 2025-03-05 | Notation rendering; quietly maintained | [V] |
| audiate (cjbayron/audiate) | Apache-2.0 | 11★, last push 2021-09-18 | Ear-training structure reference only; too stale to depend on | [V] |
| birdears | AGPL-3.0 | 78★, pushed 2026-02-16 | Avoid (copyleft) | [V] |
| nootka | GPL-3.0 | 45★, pushed 2025-08-18 | Avoid (copyleft) | [V] |

Corrections vs the destroyed run:

- "OpenEar = MIT" could not be reproduced in any re-check → dropped. Do not re-add without a licence file in hand. [V]
- "fet/pure-ear = MIT" resolves to no single project: the name splits into DimitriosLisenko/fet (5★, MIT, last push 2024-05-16) and alex-kooper/pure-ear (0★, MIT) — two unrelated tiny repos, neither an ear-training curriculum. Dropped as a named recommendation; the components stay unlisted until a concrete repo with scope and licence is in hand. [V]
- VexFlow's star count was recorded as 247★; the actual repo (0xfe/vexflow) shows 4,397★. The licence conclusion (MIT) survives, from the raw LICENSE text. [V]

Gap: there is no open mixing curriculum or tutor to reuse, and permissively licensed ear-training projects are thin (one 11★ project, last touched 2021). Theory, alignment and notation tooling is healthy and permissive. For E8 this means: reuse utilities, author the curriculum content ourselves — see §8. [V]

### 15 Oct takeover review (§3)

- Second look at "OpenEar"/"fet"/"pure-ear" confirmed the drop and produced the precise wording above (two unrelated repos; no curriculum in either). No new permissive ear-training or curriculum project surfaced in the takeover searches. [V]
- music21 corpus caveat re-confirmed verbatim including its continuation ("please see the licenses embedded in individual compositions or directories"). [V]

## §4 Spaced repetition / progress tracking

- fsrs (PyPI) 6.3.2 — MIT. Uploaded 2026-08-09T04:36 (PyPI JSON API). Correction: the destroyed run called this "a fresh 14 Oct release"; the date was wrong. [V]
- py-fsrs (open-spaced-repetition/py-fsrs) — MIT, 512★, pushed 2026-08-09. [V]
- fsrs4anki — MIT, 4,108★, pushed 2026-08-14; the reference implementation for parameter fitting and desired-retention behaviour. [V]
- SuperMemo2 (Python, alankan886/SuperMemo2) — MIT but archived 2024-06-23; do not depend on it. [V]
- Conclusion: everything in the FSRS stack is MIT — ship-clean for a closed-source product. Use fsrs (PyPI) as the scheduler; mirror fsrs4anki's retention/parameter behaviour only if per-user optimisation is ever added. [V/I]

## §5 Product patterns

Pattern map (pattern → who ships it → where it lands in KENN; E2 grade, E3 levers, E4 explanation). Quotes read from live pages on 15 Oct 2026: mixcheckstudio.roexaudio.com; izotope.com product pages and official Neutron docs; sonible.com/smarteq4 (rendered fetch); ratemysong.ai; trackscore.ai. Output Co-Producer's body copy is client-rendered and was not obtainable — that row uses the raw-HTML title/meta description plus MusicRadar coverage. LivePilot and phantom checked via their raw GitHub licence files; LivePilot positioning via its raw README.

| Pattern | Who | Verified anchor | Maps to | Mark |
|---|---|---|---|---|
| Free instant mix report, no account; per-category verdicts (tone/EQ, dynamics, loudness, stereo) with suggested fixes | RoEx Mix Check Studio | mixcheckstudio.roexaudio.com answers 200; genre-adapted feedback across EQ balance, dynamics, loudness, stereo/tonal; "Over 1.1 million tracks analyzed"; reports savable/shareable; no numeric grade on the page | E2 surface, E3 category-shaped levers | [V] |
| 0–100 score with written reasoning, segment feedback, ranked fixes, revision tracking | Rate My Song AI (ratemysong.ai, page last modified 8 Oct 2026) | "Upload a track and get a 0–100 score, 3 concrete fixes, and a V2 comparison"; four-factor model (Production Quality, Catchiness, Distinctiveness, Genre Competitiveness) shown as Sound Quality / Hit Potential / Broad Appeal / Overall; "Top 3 Fixes" quotable down to units ("bring the vocal forward 2 dB in the chorus"); timestamped segment feedback; 15 free credits; positioned at release-ready songs ("tracks you actually want to release"), not DAW sessions | direct competitor to E2/E4: number + reasons + revision deltas is a shipped pattern | [V] |
| Genre-scored mix analysis plus an AI "engineer" conversation grounded in your measurements and history | TrackScore.AI (trackscore.ai) | multi-dimension scores (Mix Quality, Freq Balance, Danceability, Hit Potential; "6 dimensions"); "Klaus™" written feedback — "Every answer cites your numbers … names the target it was scored against, and tells you when something is fine and should be left alone"; conversational follow-up that remembers your previous tracks; Bounce Check version deltas; first analysis free, $2.99 pay-per-track; DSP stack: librosa, Essentia, pyloudnorm, NumPy/SciPy; electronic-music focus (60+ subgenres) | closest shipped analogue of E2+E3+memory; study its phrasing and its stated refusal to invent reasons when a reading looks wrong | [V] |
| "Starting point, not verdict" — assistant proposes, producer keeps or rejects; do-no-harm framing | iZotope Neutron 5 Mix Assistant | official docs: "tweak to taste, or reject" and "do no harm" (Neutron Elements Track Assistant docs); Neutron 5 page frames the assistant as a "starting point" with reference-track support ("or your own references"); the current page no longer shows the older "Target Library" wording | E3 (reversible levers), E5 (Apply/Undo), E4 (tone) | [V] |
| Genre mix profiles plus custom profiles built from the user's own reference track; multi-track group view (10 tracks) | sonible smart:EQ 4 | "load up a reference track to create a custom profile and have smart:EQ 4 emulate its spectral character and balance on your channel or buss"; multi-track unmasking by drag and drop of "up to 10 tracks"; smart:filter modes Track / Group / Track and Group | E2 (declared target, reference match), E6 | [V] |
| Create-tools that deliberately do not grade | Output Co-Producer | Page title: "The fastest way to find samples that fit"; meta description: "Output Co-Producer is a new plugin that listens to your track & helps you find premium, musician-made, royalty-free samples that fit right into your music"; Output company line via MusicRadar (Jul 2025): "Output builds creative tools that support human artistry, never replacing it"; Re-imagine feature covered July 2025 | E4 (division-of-labour copy); contrast for our grade | [V] |
| Massive tool-count DAW agent | dreamrec/LivePilot | 82★, BSL-1.1 (raw LICENSE: "Business Source License 1.1"), pushed 2026-10-15; README: "474 tools · 57 domains", tagline "Make the change. Hear what happened. Keep what works." | pattern-only; the tool-sprawl trap | [V] |
| Automated mixing/mastering agent plus skills | fadelabs/phantom | 39★, AGPL-3.0 (raw LICENSE: GNU Affero GPL v3 header), pushed 2026-10-05; "MCP server + Claude Code skills for automated mixing/mastering" | avoid as dependency; agents want to do, KENN teaches | [V] |

Corrections vs the destroyed run:

- sonible: "reference zone" not found in the live copy → replaced with the verbatim "load up a reference track to create a custom profile". [V]
- CoMix (~640 conversations) could not be located in any re-check → claim dropped, recorded as a gap. [V]
- LivePilot and phantom licences re-verified from raw LICENSE files (BSL-1.1 / AGPL-3.0); the GitHub API reports NOASSERTION for both, so API-only checks would have misreported them. [V]

### 15 Oct takeover review (§5)

- **Output Co-Producer row rewritten on evidence.** The quotes "listens, curates & lets you decide" and "AI should power your workflow, but not make choices for you" could not be re-produced: the page is a client-rendered app whose body never appears to non-JS fetches (raw HTML carries only title/meta), the Wayback replay fails on a missing JS module, and web search surfaces no such sentences. Replaced with the raw-HTML meta description, the page title, and Output's company line as reported by MusicRadar (Jul 2025): "support human artistry, never replacing it". "Re-imagine 2.0 shipped 16 Sep 2026" also failed — MusicRadar's Re-imagine coverage is 17 Jul 2025; no "2.0" or 16 Sep 2026 release exists in any source found. [V]
- **sonible row verbatim confirmed** by rendered fetch: "load up a reference track to create a custom profile"; the 10-track group view confirmed as "up to 10 tracks". [V]
- **New competitors documented (the headline change of this pass).** The earlier claim "no product found ships a numeric grade out of 100 with reasoning" is false: Rate My Song AI and TrackScore.AI both ship scores plus written, measurement-referenced reasoning, and TrackScore adds a conversational follow-up grounded in the user's own measurement history. Adjacent: MixGrade (iOS) scores DJ sets 0–100 with five sub-scores and per-transition feedback. [V for the first two; ? MixGrade — App Store listing wording seen in search results, page not opened]

Net (rewritten in the takeover pass): the number is no longer a differentiator — two shipped products give numbers and reasons, one of them with the user's measurement history in its answers. What none of the products found ships: (a) grading a live DAW session — all of them grade a bounced stereo file in the cloud; (b) a published source taxonomy on every number (standard vs house rule — TrackScore cites "the target it was scored against" but publishes no taxonomy); (c) a curriculum or spaced-repetition layer. KENN's differentiator narrows to in-session, source-labelled, teaching-first grading; the "why this number" affordance and the E8 curriculum remain unshipped elsewhere. [V facts; I positioning]

## §6 Staleness check vs 14 Oct docs

Re-checked via GitHub API on 15 Oct 2026 against `docs/research/KENN_COMPARABLE_PRODUCTS_AND_OPEN_SOURCE_RESEARCH_2026-10-14.md`.

- The re-checked 14 Oct repo rows are unchanged except adamjmurray/producer-pal: 328→329★, pushed 2026-10-14. GitHub reports NOASSERTION for its licence; the raw LICENSE reads GPL-3.0-or-later, so the 14 Oct row's "GPL-3.0" is substantively right — add "-or-later" when next edited. [V]
- Still missing from the 14 Oct table: ahujasid/ableton-mcp — 3,190★, MIT, last push 2026-09-22. It is the most-starred Ableton MCP integration, and the table's conclusions about the Ableton MCP space should not be read without it. [V]
- kuanish-dev/dawcraft (created 2026-10-14): 1★, pushed 2026-10-15. GitHub reports NOASSERTION, but the raw licence file reads MIT for the app plus an addendum: the test fixture plugins in `test-plugins/synth` and `test-plugins/distortion` are GPL-3.0-or-later (nih-plug / vst3-sys) and "are not distributed with the app". Correction chain: "no licence" (earlier note) → "licence file present, unrecognised" (morning re-run) → "MIT + non-distributed GPL test fixtures" (takeover). Treat bundling as unclear until the fixture question is moot. [V]
- Newcomers since 14 Oct (all tiny): cavi-ai/ableton-mcp 3★ MIT; AxidentDK/ai-bridge-for-ableton-live 0★ Apache-2.0; romanstark/live-maestro 1★ AGPL-3.0 (avoid); rremedio-web/composing-sidekick 0★ MIT (created 14 Oct); user1303836/kumi 17★ NOASSERTION (LICENSE.md present). [V]
- Cadence note: five tiny Ableton-agent repos appeared in about one day. Any comparable-products table older than a week is candidate staleness; re-check licence and last push before citing. [V]

### 15 Oct takeover review (§6)

- The 14 Oct comparable-products table does not contain Rate My Song AI or TrackScore.AI. Both are now relevant to E2/E4 positioning (see §5) and should be added with the next edit of that doc — same class of omission as abujasid/ableton-mcp. [V]
- No other row changes beyond those above; star counts were not re-pulled in the takeover pass to conserve the unauthenticated GitHub API budget. [V]

## §7 Citable sources table

Claim area → source → terms. All checked 15 Oct 2026 unless noted.

| Claim area | Source | Terms | Mark |
|---|---|---|---|
| Dialogue phrasing for mix advice | MixAssist paper, arXiv 2507.06329 (COLM 2025) | CC BY 4.0 (quote with attribution); code MIT; HF copies unlicensed | [V] |
| Mixing dialogue raw data | Zenodo 15571750 and 15848443 | cc-by-4.0 both; prefer the Zenodo copies over HF | [V] |
| Listening-test material | MED (De Man & Reiss, DAFx-17) and rd-conx.github.io/med-web | 6/10 songs CC BY 4.0; Hub mirror declares no licence | [V] |
| Loudness target and true-peak ceiling | EBU R 128-2023 (V5, Nov 2023) and EBU Tech 3343-2023 | Free public PDFs | [V] |
| Alignment level, downmix default | EBU R68-2000; Tech 3343-2023 §7.1 | Free public PDFs | [V] |
| OTT/OVD content loudness limits | AES TD1006.1.17-10 | Free AES PDF | [V] |
| Music track/album/speech targets | AES TD1008.1.21-9 (24 Sep 2021) | Free AES PDF | [V] |
| Internet-streaming loudness practice | AES77-2023 | Paywalled; title citable, values not read | [V title; ? values] |
| Spotify platform target | Spotify support, "Loudness normalization on Spotify" | Public page | [V] |
| Expert disagreement is structured | PardonMix, CHI EA '26, doi 10.1145/3772363.3798647 | Abstract public; full text paywalled — cite narrowly | [V abstract; ? full text] |
| Measure-then-phrase pipeline | AI TrackMate, arXiv 2412.06617 | arXiv; check the licence before reusing figures | [V] |
| Convention-encoded reward design | SPHERE, arXiv 2608.30559 (EMNLP 2026) | arXiv; upmixing task, transfer only the idea | [V] |
| Multiple valid mixes per input | MEGAMI, arXiv 2511.08040 (ICASSP 2026 submission) | arXiv | [V] |
| Theory/notation/alignment OSS | music21 (BSD-3), partitura (Apache-2.0), tonal (MIT), VexFlow (MIT per file) | Permissive; music21 corpus caveat applies to bundled encodings | [V] |
| Spaced repetition | fsrs 6.3.2, py-fsrs, fsrs4anki | MIT across the stack | [V] |
| Product pattern quotes | RoEx Mix Check Studio, iZotope, sonible smart:EQ 4, Output Co-Producer (title/meta only), ratemysong.ai, trackscore.ai | Marketing copy, quoted as observed 15 Oct 2026 | [V] |
| Output company AI stance | MusicRadar, 17 Jul 2025 ("Output builds creative tools that support human artistry, never replacing it") | Press quote of an Output statement — attribute to MusicRadar | [V] |

## §8 OSS shortlist for E8

E8 = "Learning path versus one-off help: keep a formal curriculum separate from ad-hoc questions."

Ship-candidates — each entry now states what we reuse, the licence basis, effort, and the first step (takeover pass concretised this section):

- **fsrs (PyPI, MIT).** Reuse: the scheduler for curriculum review items; we do not adopt the Anki data model. Effort S. First step: a 10-card spike behind a flag — wrap `Card`/`Scheduler` in a thin adapter over the existing progress store; done when a weekly review queue round-trips without touching the review algorithm. [V licence]
- **music21 (BSD-3, active).** Reuse: theory and analysis answers; keep bundled corpus files out unless each file's terms are checked (corpus caveat, §3). Effort M. First step: pick one likely E8 lesson (interval/scale drills) and generate its drill items in a throwaway script; done when one lesson's items render. [V]
- **partitura (Apache-2.0, active).** Reuse: score/performance alignment if ear-training modules use scores. Effort M. First step: only after the E8 outline names a score-alignment module; spike one audio-to-score alignment on a public-domain excerpt. [V]
- **tonal (MIT, npm).** Reuse: theory primitives if any curriculum UI is TS/JS. Effort S. First step: settle the language of the curriculum surface first, then port one drill's interval logic; done when the drill runs from npm package code. [V]
- **VexFlow (MIT per file).** Reuse: notation rendering. Effort S–M. First step: render two bars of a cadence from music21 output in a prototype page; done when the score matches the drill item. [V]

Read-only references (patterns or data, not shipped code):

- fsrs4anki (MIT) — parameter fitting and desired-retention behaviour. [V]
- audiate (Apache-2.0, stale) — ear-training interaction patterns to borrow, not a dependency. [V]

Excluded: birdears (AGPL-3.0), nootka (GPL-3.0), SuperMemo2 (archived), LivePilot (BSL-1.1), phantom (AGPL-3.0). [V]

Content gap: no open mixing curriculum exists to import; E8's content must be authored in-house (E11 expert network is its natural source of record). The utilities above are infrastructure, not pedagogy. Skeleton-marker audit from the takeover pass: the 12:41 backup of this file contained 11 "(expand)" markers, all filled in the 12:48 live version; no literal skeleton marker remains. The only "skeleton" left in this lane is the E8 curriculum content itself, which is a scope item, not a missing citation. [V]

## §9 Ranked recommendations (effort S/M/L)

Each recommendation now carries a first step, so it can be picked up without re-reading this lane (takeover pass made this section actionable).

1. **S — Carry the `source` tag from E2 into E3/E4 copy.** Every lever and numeric claim names its standard or says "house rule, measured". The 3-of-16 published basis in mix_doctor is the precedent to keep. First step: add the `source` field to the E2 deduction struct and back-fill one deduction end-to-end. [R]
2. **S — Adopt fsrs (PyPI, MIT) as the E8 scheduler.** Start with a fixed desired-retention value; add per-user parameters only if needed. First step: the 10-card spike in §8. [V]
3. **S — Update the comparable-products doc:** add ahujasid/ableton-mcp (3,190★, MIT); fix the licence wording for producer-pal (raw LICENSE GPL-3.0-or-later) and dawcraft (MIT + non-distributed GPL test fixtures); add Rate My Song AI and TrackScore.AI (§6). First step: one table edit; done when the doc's Ableton-MCP and AI-grading rows match §5/§6 of this note. [V]
4. **S–M — Record the competitive reframe (takeover addition, gated on orchestrator).** The "no product ships a grade" premise is gone; the E2 note should state the new differentiator sentence: in-session multi-track grading, source-labelled numbers, curriculum — none of them shipped by ratemysong.ai or trackscore.ai. First step: run one free TrackScore report and write down what it does not do (session context, standards sourcing, teaching over time); done when the E2 note carries the positioning paragraph. [I]
5. **M — Build the E4 style sheet from MixAssist dialogues (CC BY 4.0):** name the measurement → give the range → say what to listen for. Attribution required; no redistribution of the unlicensed HF copies. First step: tag 20 expert replies against that structure. [V data; I method]
6. **M — Author the E8 curriculum skeleton:** measurement literacy (what LUFS, true peak and correlation mean), reference discipline (what a reference can and cannot settle), conventions per production stage. Content in-house; cite standards where they exist. First step: headings-only outline of the three modules with the first lesson of each named. [I]
7. **M — Add a "why this number" affordance to every displayed E2/E4 value,** linking to the §7 source table. This remains the teach-instead-of-do feature no product found ships. First step: wire one E2 deduction end-to-end as the reference implementation. [I]
8. **L — MED-based calibration for E9 tolerances:** A/B listening tests using the six CC BY songs; keep the Hub mirror out of the pipeline. First step: pick the six tracks and define one tolerance question. [V data; I method]
9. **L — Theory modules (music21/partitura/VexFlow)** only if the E8 outline pulls them in; defer until then. [I]

## §10 Avoid list

Licence-blocked (do not vendor or copy code):

- birdears (AGPL-3.0), nootka (GPL-3.0) — copyleft ear training. [V]
- fadelabs/phantom (AGPL-3.0), romanstark/live-maestro (AGPL-3.0) — copyleft DAW agents. [V]
- dreamrec/LivePilot (BSL-1.1) — source-available, not open source; pattern reading only. [V]
- SuperMemo2 (Python) — MIT but archived; dead code. [V]

Data that must not ship:

- MixAssist HF datasets (`mclemcrew/MixAssist`, `mclemcrew/MixParams`) — no licence declared. [V]
- `mclemcrew/Qwen-Audio-Mix-Instruct` (model repo) — no licence declared (added in the takeover pass). [V]
- MED Hub mirror (`sparrowreivun/Mix-Evaluation-Dataset-2.0`) — no licence declared; only the DAFx-17 CC BY six-song subset is clear. [V]
- CoMix "~640 conversations" — unverifiable; do not cite anywhere. [V]

Claims that failed re-verification (do not repeat):

- Output Co-Producer quotes "listens, curates & lets you decide" and "AI should power your workflow, but not make choices for you" — not reproducible from any fetch; replaced with meta-description and MusicRadar wording (§5). [V]
- "Re-imagine 2.0 shipped 16 Sep 2026" — no source found; MusicRadar's Re-imagine coverage is July 2025. [V]
- "No product ships a numeric grade out of 100 with reasoning" — falsified: ratemysong.ai and trackscore.ai ship exactly that. [V]
- sonible "reference zone" — not in the live copy; the real phrase is "load up a reference track to create a custom profile". [V]
- "OpenEar MIT", "fet/pure-ear MIT" — not reproducible as named projects; fet/pure-ear splits into two unrelated tiny repos (§3). [V]
- fsrs "fresh 14 Oct" — actual PyPI upload 2026-08-09. [V]
- dawcraft "no licence" — MIT text plus a GPL-3.0-or-later addendum for non-distributed test fixtures (GitHub NOASSERTION). [V]
- AES77-2023 values — paywalled; cite the title only (full title now known, §2). [V]

## §11 Verified vs inferred

Verified this run (primary source or API, 15 Oct 2026). The takeover pass added: both Zenodo records; all mclemcrew HF repos plus the Qwen base model; the arXiv licence line; EBU R 128-2023, R68 and Tech 3343 from the PDFs; AES TD1006 and TD1008 from the PDFs; the Spotify support page; the rendered sonible page; the Output raw-HTML title/meta and the MusicRadar article; the dawcraft raw licence; the LivePilot raw LICENSE and README. [V]

- §1: arXiv metadata and licences for MixAssist, SPHERE, MEGAMI, Stem Blending, AI TrackMate (pages read); the 50.4% and 40%-vs-33% figures re-read from the paper HTML (morning pass); GitHub MIT for mclemcrew/MixAssist; both Zenodo records (titles, cc-by-4.0, sizes, dates via Zenodo API); HF records re-pulled (no licence declared on the two datasets and on Qwen-Audio-Mix-Instruct; apache-2.0 on the LoRA and its base). [V]
- §2: EBU Tech 3343 quotes and values from the extracted PDF text; EBU R 128-2023 tolerances; R68 alignment; AES TD1006/TD1008 values from the PDFs; Spotify from the live page; AES77 paywall (403) with title from the AES listing. [V]
- §3: licences and vitality via GitHub API (morning batch); VexFlow licence read from the raw LICENSE; tonal licence from the npm registry; fet/pure-ear resolution from repo listings. [V]
- §4: PyPI upload date for fsrs 6.3.2; GitHub licences throughout. [V]
- §5: raw LICENSE files for LivePilot (BSL-1.1) and phantom (AGPL-3.0); marketing copy from live pages (sonible rendered); Output title/meta from raw HTML; MusicRadar article for Output's company line; ratemysong.ai and trackscore.ai pages read in full. [V]
- §6: GitHub API staleness deltas for every repo listed. [V]

Carried from the earlier 15 Oct pass, not re-opened in the takeover: [R]

- The MED 187.5 GB size figure — the Hub file listing was not re-summed.
- The star counts and push dates in §3 and §6 (conserve the unauthenticated GitHub API budget; the takeover re-read raw files only).
- Individual product-page sentences read in the morning pass (RoEx "1.1M+ tracks", Neutron quotes, PardonMix abstract wording) — the pages re-answered 200, but only sonible and the two grade products were re-quoted in the takeover.
- Paper statistics in §1 (§ shape/results/real-time) — re-read in the morning pass, not re-read again.

Inferred (judgement, not fact): [I]

- Effort sizes S/M/L in §8–§9 are estimates.
- Transferring SPHERE's reward-design idea to grading is our reading; the paper itself targets upmixing.
- The §5 net positioning ("the differentiator narrows to in-session, source-labelled, teaching-first grading") is our interpretation of the competitor facts, not a competitor's statement.

Unverifiable / dropped: [?]

- CoMix (~640 conversations).
- OpenEar and fet/pure-ear as named projects.
- sonible "reference zone".
- The old Output Co-Producer quotes and "Re-imagine 2.0, 16 Sep 2026".
- MixGrade's exact screen wording (App Store listing seen in search results only).
- AES77-2023 values (title only; keep quoting Tech 3343 for production-level wording — see §2).

### 15 Oct takeover review (§11)

- Skeleton-marker audit: the 12:41 backup contains 11 "(expand)" markers, all filled by the 12:48 live version (md5 ca3c79025d3c24b7c30bbbf13d7f4951). No literal skeleton marker exists in this file; the thin sections identified before the pass were §8 (now concretised with reuse/licence/effort/first step) and §9 (now carries first steps). The remaining content gap is the E8 curriculum itself (§8).
- Marker convention switched to the research-pass standard `[V]/[R]/[I]/[?]` on every load-bearing claim. [V]
- The falsification of the "no product ships a grade" claim is the material change of this pass; everything else is precision work on licences, dates and standard wording. [V]
