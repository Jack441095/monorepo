# KENN product and open-source research

Research date: 2 October 2026. Source-review base commit: `f060bf54fa4732af922755763b4785622ed45f7b`. The checkout also contained uncommitted work; that commit alone does not reproduce every source observation. Public product documentation, repositories, model cards and release metadata were checked during this pass. Competitor software was not installed or independently benchmarked.

This is research evidence and planning input. [KENN_PLAN.md](../../KENN_PLAN.md) remains the sole roadmap and work queue. Recommendations below refer to its existing task IDs. The capacity scenario and experiments are proposals, not a second execution plan or claims of completed qualification.

Follow-up review at `835c8be8`: the main HTTP/UI background path now retains session/plugin/correlation identifiers, avoids a second session-memory update, scopes polling and discards superseded or cleared results. [The background-context receipt](../evidence/KENN_BACKGROUND_CONTEXT_2026-10-02.md) records its tests and limits. The broader route, context, cancellation and status audit remains open; the original source-review base above is retained for the other observations.

## 1. Main finding

KENN's strongest opportunity is a useful local conversation that leads to an inspectable, verified Ableton change. The repository already contains much of the necessary infrastructure. Its next gains are more likely to come from correct context delivery, less wasted inference work, better evidence selection and honest audio findings than from another agent framework or a larger model.

Here GLM means a general language model assistant. The plan specifies local Qwen3 8B chat and Qwen3 4B planning, with an Apple M3/16 GB target. The Python/C++ division and AbletonOSC transport ownership also remain fixed.

Five priorities, in order:

1. **Qualify the whole conversation path.** Complete the remaining context, late-answer, cancellation and status audit before expanding features. The main HTTP/UI background fix is recorded above; it does not close the whole audit. Map to A2–A5 and C3.
2. **Measure and reduce local inference waste.** Keep the chosen models; separate queueing, retrieval, prefill, generation, validation and final UI delivery. Map to C1–C2.
3. **Improve evidence relevance without relaxing grounding.** Audit current retrieval failures first; trial a small ONNX query–passage reranker only if it beats the existing hybrid/source reranking. Map to L2 and C4–C5.
4. **Make listening and reference advice demonstrably trustworthy.** Validate loudness/true-peak measurements, abstain on missing references, and distinguish measured differences from musical suggestions. Map to B1 and B4.
5. **Make existing proposals, memory and MIDI previews easy to use.** Borrow editable controls and A/B workflows, then qualify Apply/readback/Undo. Add voice or transcription only after the core journey works. Map to L3/L5 and B2–B4.

The most suitable additional tools to investigate are **a small cross-encoder exported to ONNX**, **libebur128 as a measurement comparison**, and **whisper.cpp for optional local push-to-talk**. Basic Pitch is a later, bounded audio-to-MIDI candidate. None should be added merely because it appears in this report.

## 2. What KENN already has

Source presence establishes implementation, not current product qualification. Historical receipts establish their recorded build, corpus and environment. This distinction matters because the plan and inference code changed during this research pass.

| Area | Observed implementation | Qualification or gap | Implication |
|---|---|---|---|
| Local language model | Ollama transport, bounded generation, grounding, background upgrades; an MLX engine also exists. | Current M3 end-to-end delivery needs a fresh baseline. The MLX default selects a different, smaller model. | Profile the selected Qwen3 8B path before comparing backends. |
| Retrieval | BM25, dense embeddings, reciprocal-rank fusion, source heuristics, optional learned source scoring and official-manual candidate handling. | A learned source scorer is not the same as a query–passage relevance cross-encoder. Index freshness and independent recall remain open. | Improve failed questions; do not schedule “add hybrid retrieval” as new work. |
| Dialogue | Session/world models, reference binding and recent track choices. | Two-choice follow-up evidence covers a specific 300 s window. Five-turn model/UI qualification remains open. | Extend demonstrated journeys, including project switches and corrections. |
| Live actions | Typed action service, proposals, backend abstraction, recipes, confirmation/readback/Undo paths. | Cross-surface ownership, stale identity, timeout outcomes, serialization and exact Undo need qualification. | Reuse the action owner. Extra MCP tools must not gain separate write authority. |
| Memory | Scoped SQLite-backed preferences, history and restore APIs/services. | Human inspect/edit/delete/restore and UI/API parity remain open. | Build understanding and control around existing memory, rather than add another memory framework. |
| Audio analysis | Peak/clipping, stereo/correlation, spectral analysis, loudness analysis and local mix review. | Some measurements are approximations; broader causal/musical interpretation requires human review. | Expose uncertainty and qualify the meter before asserting mastering advice. |
| Reference comparison | Backend and mix-review reference implementations exist. | Static tracing shows two HTTP handlers and agent paths can construct synthetic reference evidence from missing input. The current reference UI uses a separate multipart comparison path. | Fix missing-input behavior with caller fixtures; establish one finding contract without assuming every reference surface shares the defect. |
| MIDI/artifacts | Typed note/artifact validation, bounded notes, preview/import contracts and provenance hooks. | Owner listening review and verified insertion/Undo remain open. | Editable ideas can build on existing artifacts. |
| Voice | The current voice-copilot module classifies text. | It explicitly does not implement microphone capture or ASR. | Voice input is an optional new integration, not a completed capability. |
| Release evidence | Monthly measures, a 15-check release qualifier, tests and dated evidence. | The plan records a known order-dependent structural-repair test failure. | Keep missing/unmeasured gates visible; a research report does not certify release readiness. |

### Load-bearing local evidence

- [Current plan and acceptance definitions](../../KENN_PLAN.md): useful conversation, local inference and Ableton integration take precedence over source-count expansion. A2/A3 continue through remaining request owners after the bounded background-context fix.
- [Query embedding evidence](../evidence/KENN_QUERY_EMBEDDING_LATENCY_2026-10-02.md): CPU ONNX query embedding measured about 1.14–1.15 ms p50 versus 12.43–12.72 ms for CoreML, with 240/240 ordered top-four parity. This saves approximately 11 ms in that scope, not seconds of generation time.
- [Track-choice evidence](../evidence/KENN_TRACK_CHOICES_2026-10-02.md): the “other one” behavior already has session/identity tests. This is a useful example of a narrow, evidenced conversation feature.
- [Recorded brain-latency review](../reviews/KENN_BRAIN_ANSWER_LATENCY_2026-10-01.md): different routes, caches, model digests and revisions produced very different results. The older 13/30 acceptance result is 43%, not a passing 70% result. The plan's later 22/29 and 23/29 sample is still too small to establish 90%. Neither is today's complete-path qualification.
- [LLM transport](../../apps/backend/src/kenn/llm/llm_rewrite.py): native Ollama thinking-off behavior and the general 384-token output cap are already implemented; quick-fix/command and voice caps are smaller. Recommending these as new optimizations would duplicate completed work.
- [Existing MLX engine](../../apps/backend/src/kenn/llm/mlx_inference_engine.py): its default `Qwen2.5-1.5B-Instruct-4bit` would change the product model. An MLX trial needs an explicit, traceable conversion of the selected 8B model and a comparable quality test.
- [Retrieval implementation](../../apps/backend/src/kenn/retrieval/retrieval.py): existing fusion and reranking make a new vector database a weak immediate proposal. The recorded 4,642 × 384 float32 embedding matrix is approximately 6.8 MiB, calculated from dimensions; that is not process RAM.
- [Reference matcher](../../apps/backend/src/kenn/core/reference_matcher.py): empty spectra trigger 40 synthetic bands and can produce an EQ recipe labelled with a default commercial-reference name. A pure-function replay of the empty-object validation and matcher call produced 40 bands, four EQ recipe entries and 0.26 dB RMS delta under the label “Commercial Reference”, without any supplied measurements. Missing measurements should produce an unavailable result.
- **Static caller trace:** [HTTP handlers](../../apps/backend/src/kenn/server.py) for `/api/reference/analyze` and `/api/reference/match-curve` default both spectra to `[]`, call the matcher and return `ok: true`; the [JSON validator](../../apps/backend/src/kenn/core/request_validation.py) accepts `{}`. The registered [agent tool and objective branch](../../apps/backend/src/kenn/autonomous_agent.py) also substitute synthetic spectra or call with empty arrays. This proves source-level paths, not observed use in a deployed server. The current [reference UI](../../apps/frontend/src/components/KennReferenceMatcher.vue) instead submits actual mix/reference files through the separate [multipart helper](../../apps/frontend/src/api/mixReview.ts). No running HTTP service or Live session was exercised.
- [Loudness analysis](../../apps/backend/src/kenn/core/loudness_analysis.py): windowed calls to integrated loudness and approximate LRA need conformance checks before being labelled standards-equivalent momentary/short-term/LRA. Four-times resampling is not, by itself, proof of true-peak conformance.
- [Audio analysis](../../apps/backend/src/kenn/core/audio_analysis.py): an FFT peak proximity warning already acknowledges that it cannot prove two-source masking. Preserve that separation between measurement and hypothesis.
- [Voice module](../../apps/backend/src/kenn/speech/voice_copilot.py) and [artifact contracts](../../apps/backend/src/kenn/core/audiogen_artifacts.py): voice input and musical generation are distinct providers around existing typed services.

## 3. Products worth studying

These are references for behavior and interface patterns. A vendor page establishes what its publisher claims; it does not establish quality, latency or suitability for KENN. “Local DSP” below does not imply that activation, licensing or every account feature works offline.

| Reference and primary evidence | Useful pattern for KENN | Local/cloud boundary | Fit and limitation |
|---|---|---|---|
| [LIA Ableton assistant](https://liaplugin.com/ableton-ai-assistant/), [documentation](https://liaplugin.com/docs/), [privacy](https://liaplugin.com/privacy/) | Natural follow-ups that create editable MIDI/track changes; show the result inside the producer's workflow. | A local Ableton bridge connects to a service; its privacy policy describes external inference providers. | High workflow relevance. Borrow bounded creation and correction, not its cloud architecture. Vendor claims, untested here. |
| [FL Studio Gopher](https://support.image-line.com/action/knowledgebase?ans=901) | Ground replies in the DAW manual; state the limits of hearing, memory and controlled operations clearly. | Documentation describes external services and query logging. | Strong reference for knowledge UX and capability honesty, not proof of autonomous mix engineering. |
| [iZotope Neutron 5](https://www.izotope.com/products/neutron?tab=features), [feature explanation](https://www.izotope.com/community/blog/whats-new-in-neutron-5) | Turn an assistant's suggestion into editable module controls; use Delta/audition to explain the audible change. | Plugin DSP; complete activation/offline conditions unverified. | High fit for recipe cards. Do not imitate a “correct mix” score or claim its proprietary inference can be embedded. |
| [iZotope Ozone](https://www.izotope.com/en/products/ozone/engineers), [Advanced features](https://www.izotope.com/products/ozone-advanced?tab=features) | Reference-guided mastering suggestions with visible processing modules and audition controls. | Plugin DSP; network/account details unverified. | Useful mastering UX reference. Edition-specific features and source/genre bias make a universal target inappropriate. |
| [sonible smart:EQ 4](https://www.sonible.com/smarteq4/), [reference workflow](https://www.sonible.com/blog/smarteq4-reference-tracks/) | Explicit front/middle/back priorities, grouping and constrained spectral adaptation. | Local plugin processing; licensing-network behavior unverified. | Good way to ask producer intent before suggesting EQ. A priority model is more useful than assuming every track needs equal prominence. |
| [sonible smart:comp 3 guide](https://www.sonible.com/blog/smartcomp3-user-guide/) | Editable compression behavior and group-aware dynamics rather than a bare text instruction. | Plugin DSP; full offline lifecycle unverified. | Translate broad intent into inspectable parameter suggestions. Compression choice still needs listening and device-specific limits. |
| [ADPTR Metric AB](https://adptraudio.com/product/metric-ab/), [manual](https://files.plugin-alliance.com/products/adptr_metricab/adptr_metricab_manual.pdf) | Loudness-matched reference A/B, aligned sections/cues, and separate spectrum/stereo/dynamics views. | Local audio comparison; activation unverified. | Highest-value reference for B1/B4. Match comparable sections and playback level before explaining tonal differences. |
| [Sononym similarity search](https://www.sononym.net/docs/manual/similarity-search/) | Search by timbre/spectrum/pitch/amplitude with explicit weighting and filters. | Local sample analysis/search. | Strong SLO reference. Expose why a sample matches and let users weight the dimensions. Audio embeddings are a separate problem from manual retrieval. |
| [XLN XO](https://www.xlnaudio.com/products/xo) | A sonic map, quick sample swaps and audition in a running beat. | Local plugin/standalone sample workflow; installer/account requirements unverified. | Useful sample-discovery interaction. Integrate with the existing sample owner rather than build a duplicate library index. |
| [Output Co-Producer guide](https://support.output.com/en/articles/10628997-co-producer-user-guide) | Bounded four/eight-bar captures, tempo/key-aware search, previews, history and drag-and-drop. | The guide describes uploading captured audio for cloud analysis. | Borrow section selection and preview. Do not reproduce its network dependency in KENN's local assistant. |
| [RoEx Mix Check help](https://mixcheckstudio.roexaudio.com/help), [Tonn SDK](https://tonn-portal.roexaudio.com/sdk), [SDK examples](https://tonn-portal.roexaudio.com/sdk/docs/examples) | Present measured issues with explanations; separate a settings-returning engine from rendering. | Mix Check is an upload service. Tonn SDK is advertised as offline C++ processing. | Possible future build-versus-buy reference, not an open-source dependency. Commercial terms, redistribution and actual performance require direct evaluation. |
| [Ableton Live MCP](https://github.com/wstierhout/ableton-live-mcp), [product](https://abletonmcp.com/) | Typed capability discovery and read-only inspection of Live files; tool inventory as a coverage reference. | Local bridge; connected model client can be hosted. | Compare capability gaps and file-summary UX. A large tool count does not establish action accuracy or safety. |
| [Ableton ControlDeck](https://github.com/remymazmanian/ableton-control-deck) | Authenticated local transport, identity/readback patterns, dashboard and sample-library integration. | Local bridge and storage; upstream platform focus is macOS. | KENN already has a read-only adapter. Audit that integration before adding a second transport. Its optional hosting/M4L features need separate qualification. |
| [freekmurze/ableton-ai](https://github.com/freekmurze/ableton-ai) | Broad command inventory, MCP/REST surfaces and explicit limits around audio perception. | Local server with optional local-model path; model choice determines external data flow. | Useful implementation reference. Its same-user socket and native Undo assumptions are not substitutes for KENN's confirmation and exact Undo contract. |
| [NeuralNote](https://github.com/DamRsn/NeuralNote) | Background transcription, visible piano-roll progress, cancel, source-versus-result audition and MIDI export. | Current v2 development docs describe local MuScriptor inference; online model download/update checks. | Excellent creation UX reference. v2 has no prebuilt installers and limited hardware testing; its model weights are non-commercial. Older Basic Pitch-based descriptions do not describe current v2. |

### Specific product ideas to carry forward

**An answer becomes a small, editable object.** “The hats are harsh” should lead to evidence, a target clarification if needed, and a recipe card with bounded options. The existing recipe card already exists; research suggests improving its audition, explanation and corrections, not rebuilding it. Keep conversational help available when no action is warranted.

**A reference comparison starts with a fair listen.** Ask for an owned/authorized reference file, choose corresponding sections, match playback loudness, and show exactly which regions were analysed. “The selected chorus has 2 dB more energy in this band” is a measurable claim. “Your master needs more warmth” is an interpretation requiring producer intent. Avoid copyrighted reference bundles and universal streaming/mastering prescriptions.

**Creation remains editable.** Show note range, length, tempo assumptions and whether output is generated or transcribed. Allow preview/cancel/revise before selecting a Live target. A user should be able to say “half as many notes,” “keep the rhythm,” or “the other track,” and inspect the revised proposal.

**Capability and progress text comes from receipts.** Distinguish selected model/runtime, connected transport, available measurements, proposed changes and verified applied changes. Product inspiration cannot justify a reply that says “done” when only a plan or artifact exists.

## 4. Open-source tools and licence boundaries

“Open source” applies to a particular artifact. Runtime code, model weights, voice assets, training data and a downloadable binary can have different terms. The licence labels below are research findings, not a redistribution clearance. Before packaging any new dependency, inspect the pinned LICENSE/NOTICE, transitive native libraries, exact weight revision and asset terms. No dependencies were added in this pass.

### 4.1 Reuse now: existing foundations

| Tool / evidence | Licence and deployment | Recommendation for KENN |
|---|---|---|
| [ONNX Runtime](https://github.com/microsoft/onnxruntime), [current embedding model card](https://huggingface.co/Xenova/all-MiniLM-L6-v2) | Runtime MIT; model card Apache-2.0. Native wheels/binaries differ by Python, OS and architecture. | Keep the measured CPU query path. Reuse this runtime for a small reranker if approved, instead of shipping PyTorch solely for retrieval. Preserve exact tokenizer/model/index versions. |
| [Ollama](https://github.com/ollama/ollama), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs) | MIT runtime; weights have their own licence. Local operation is a selected deployment mode, not a promise about every Ollama feature. | Keep the native local path and instrument its actual response. JSON-schema output can constrain shape; application validation still owns identity, units, ranges and permission. |
| [MLX-LM](https://github.com/ml-explore/mlx-lm) | MIT; Apple-focused native runtime plus separate weights. | Existing candidate backend, not a new feature. Compare the same selected 8B lineage, tokenizer, prompt and output budget. Never enable the smaller default and call the result a backend-only speed improvement. |
| [llama.cpp](https://github.com/ggml-org/llama.cpp), [grammar documentation](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md) | MIT; GGUF weights separate. Native builds support several CPU/GPU backends. | Packaging or inference alternative only after a measured need. Its supported JSON-schema subset does not validate every semantic constraint. Keep deterministic validation even when grammar output is valid. |
| [SQLite](https://sqlite.org/copyright.html) | Public-domain core; extensions/bindings may differ. Local file storage. | Keep existing scoped memory and transactions. Another memory/vector database has no demonstrated need at this corpus size. |
| [pyloudnorm](https://github.com/csteinmetz1/pyloudnorm), [librosa](https://github.com/librosa/librosa) | MIT and ISC respectively; scientific-Python dependency stacks. Both already present or optional in KENN. | Reuse for offline analysis with explicit approximations. Benchmark actual package/runtime compatibility before updating; a new release is not an instruction to upgrade. |

The [Qwen3-8B card](https://huggingface.co/Qwen/Qwen3-8B) identifies Apache-2.0 weights. The exact KENN Ollama model/template/conversion still needs a manifest, not inference from a display name. An ideal packed four-bit 8B tensor is approximately 4 GB; 4B is approximately 2 GB. Those are arithmetic lower bounds, excluding quantization metadata, KV cache, activations, copies and runtime. They are not measured download sizes or resident-memory budgets. Keeping both models loaded alongside Live needs measurement.

### 4.2 Suitable experiments, ordered by current value

| Candidate and evidence | Code, weights and commercial packaging | Platform, resource and integration facts | Experiment / alternative |
|---|---|---|---|
| **Small relevance reranker:** [cross-encoder/ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2), [Sentence Transformers](https://github.com/UKPLab/sentence-transformers), [ONNX efficiency guide](https://sbert.net/docs/cross_encoder/usage/efficiency.html) | Apache-2.0 model card and toolkit. Export tooling need not become a production dependency; preserve notices and conversion provenance. | Score query–passage pairs only for the top 12–20 retrieved chunks, using existing CPU ONNX Runtime. Roughly tens of millions of parameters; model file/RAM and DAW-language benefit need measurement. | Experiment 2. It must beat current hybrid plus source scoring on independent cases within a declared latency budget. Alternative: improve chunk boundaries, source applicability and existing heuristics without a new model. |
| **Loudness comparison:** [libebur128](https://github.com/jiixyj/libebur128), [EBU Tech 3341](https://tech.ebu.ch/publications/tech3341) | MIT library; official test materials require their own asset-terms check. No learned weights. | Small portable C library with a CMake build and its own FIR true-peak resampler. Native bindings/build choices need qualification; maintenance is sparse. | Experiment 3 as an independent implementation comparison, checked against official vectors. Adopt a native kernel only if it improves correctness or a measured bottleneck. Alternative: correct existing Python algorithms and retain labelled approximations. |
| **Local ASR:** [whisper.cpp](https://github.com/ggml-org/whisper.cpp), [original Whisper licence](https://github.com/openai/whisper#license) | MIT implementation; original Whisper explicitly releases code and weights under MIT. Converted files still need origin/hash/notice verification. | CPU/Apple backends and Windows builds. Upstream estimates: `base` about 142 MiB model and 388 MB memory, `small` about 466 MiB and 852 MB; these are not KENN M3 measurements. | Later B4 push-to-talk `base.en` trial. Route text through the same intent/policy service; confirm uncertain names, negative numbers and units. Alternative: text input or sherpa-onnx. Never auto-Apply a transcription. |
| **Offline speech alternative:** [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Apache-2.0 code; every ASR/TTS/VAD model and voice has independent terms. | Broad local platform support; streaming/non-streaming options. No single model-size or RAM figure applies. | Consider if streaming ASR or one speech runtime is a demonstrated requirement. Choose a model first, then measure. Avoid bringing in a whole model catalogue for an unspecified voice feature. |
| **Bounded audio-to-MIDI:** [Spotify Basic Pitch](https://github.com/spotify/basic-pitch) | Apache-2.0 repository; packaged model artifacts and third-party dependencies need a pinned asset inventory before redistribution. | ONNX/CoreML/TFLite/TensorFlow versions exist. README compatibility predates KENN's Python 3.13; default install/runtime selection can pull unwanted TensorFlow. Start with an isolated, explicit ONNX adapter. | Later B4: short, isolated instrument clips into the existing typed artifact contract, with piano-roll/source audition. Measure note/onset quality and human usefulness. Alternative: existing symbolic note generation or manual MIDI. Full-mix transcription is not its initial KENN promise. |
| **MIDI file utility:** [Mido](https://github.com/mido/mido) | MIT code, no model assets. Optional port backends have separate dependencies. | Cross-platform Python MIDI serialization/parsing. File operations differ from opening MIDI ports. | Add only if existing artifact/file code cannot satisfy a concrete case. Keep Live insertion in the current action service; do not introduce another port-writing authority. |

A reranker is the only proposed new model with a direct route to the current core priority. ASR and transcription are deliberately later: they add workload, ambiguity and packaging while conversation and delivery remain unqualified.

### 4.3 Defer or exclude from the default bundle

| Tool / evidence | Decision and reason | What could change the decision |
|---|---|---|
| [FAISS](https://github.com/facebookresearch/faiss), MIT | Defer. The recorded exact-search embedding matrix is small; native packaging adds cost without a measured retrieval bottleneck. | A much larger authorised corpus and a benchmark showing exact search dominates latency. |
| [CLAP](https://github.com/LAION-AI/CLAP), CC0-1.0 repository code | Defer. Audio–text search may help SLO, but checkpoint rights, training-data restrictions, PyTorch packaging and M3 memory are not resolved here. Code licence does not establish checkpoint clearance. | A failed semantic sample-search journey, licensed exact checkpoint, bounded local benchmark and improvement over existing acoustic features. |
| [Essentia licensing](https://essentia.upf.edu/licensing_information.html), [model catalogue](https://essentia.upf.edu/models.html), [repository](https://github.com/MTG/essentia) | Exclude from an assumed permissive bundle. Library is AGPL-3.0; model pages report differing non-commercial Creative Commons variants. Both need artifact-specific review. | A compatible distribution design or explicit commercial agreement, selected models, and a demonstrated feature gap. Do not interpret AGPL itself as a blanket commercial-use ban. |
| [Pedalboard](https://github.com/spotify/pedalboard), GPL-3.0 | Defer default integration. Native plugin hosting and effects duplicate some existing JUCE responsibilities and add plugin/crash/licence boundaries. | A defined offline-rendering need with an appropriate GPL distribution analysis and isolated host. Third-party plugin licences remain separate. |
| [Demucs](https://github.com/facebookresearch/demucs), MIT code | Defer. Upstream is archived, and PyTorch/model workload competes with the assistant on 16 GB. Separated stems are estimates with artifacts, not evidence of the original mix's exact sources. | A licensed maintained distribution, selective offline opt-in and demonstrated listening benefit within the resource budget. |
| [Piper maintained fork](https://github.com/OHF-Voice/piper1-gpl), [old fork](https://github.com/rhasspy/piper) | Do not assume the historical MIT project is the maintained option. Current OHF runtime is GPL-3.0; voices have separate licences. Old upstream is archived. | An approved distribution design and exact voice/model-card clearance. GPL permits commercial activity with obligations; it is not a permissive closed-bundle shortcut. |
| [MuScriptor C++ port](https://github.com/DamRsn/muscriptor.cpp), [small model card](https://huggingface.co/MuScriptor/muscriptor-small) | Exclude current weights from an ordinary commercial KENN bundle: port code MIT, weights CC BY-NC 4.0 with additional access/use conditions. Current NeuralNote is Apache-2.0 code but that does not change model rights. | Separate commercial model permission or a suitable permissive replacement. Study preview/cancellation UX regardless. |
| New generic agent framework, vector service or whole C++ backend | Defer. The repo already owns routing, jobs, policy, retrieval and memory. Another control abstraction risks divergent context and write rules. | A measured operational limit that a narrow change cannot solve. No such limit was established in this research. |

For MuScriptor, the upstream C++ performance notes report a 209 MB small F16 file plus approximately 218 MB KV cache; medium is 618 MB plus approximately 499 MB KV cache. These exclude other allocations. Its M1 Pro runs are single idle-machine tests, not M3/Live qualification. The native port also requires C++23 and has limited platform testing. [Upstream performance and memory notes](https://github.com/DamRsn/muscriptor.cpp/blob/main/docs/PERFORMANCE.md).

### 4.4 Maintenance evidence, not popularity scores

The accompanying [public repository snapshot](KENN_PUBLIC_REPOSITORY_SNAPSHOT_2026-10-02.json) records 20 repositories' public metadata, captured on the research date. It contains latest returned releases, dates, commit hashes when available, archive flags and open issue/PR counts. These counts do not measure unresolved defects or security risk. No response-time or defect-severity study was performed.

| Candidate | Latest returned release in snapshot | Maintenance interpretation |
|---|---|---|
| ONNX Runtime | v1.30.0, 10 September 2026 | Active foundation; compatibility with KENN's pinned environment still controls updates. |
| MLX-LM | v0.31.3, 22 April 2026; commits observed in October | Active development; benchmark pinned versions, not a moving main branch. |
| llama.cpp | b11345, 2 October 2026 | Frequent builds make revision pinning and reproducibility essential. |
| Ollama | v0.35.1-rc2, 29 September 2026 | Returned release is a prerelease; not a recommendation to replace the installed version. |
| Sentence Transformers | v6.1.0, 18 September 2026 | Active toolkit; avoid bringing its training stack into the packaged runtime unnecessarily. |
| whisper.cpp | v1.9.4, 11 September 2026 | Active candidate with separate model and platform qualification. |
| sherpa-onnx | v1.13.8, 10 September 2026 | Active, broad model support; exact model licence remains decisive. |
| libebur128 | v1.2.6, 14 February 2021 | Sparse updates; treat as a comparison implementation, not a self-certifying standard oracle. |
| Basic Pitch | v0.4.0, 16 August 2024; commit observed November 2025 | Compatibility and packaging spike needed, especially Python 3.13/Apple Silicon. |
| OHF Piper | v1.8.0, 4 September 2026 | Maintained fork has different runtime terms from archived historical upstream. |
| Demucs | No release returned; archived | Maintenance and weight inventory are adoption risks. |

The snapshot uses GitHub API metadata, not independent audits. `null` commit/release fields mean unavailable or no returned object; they do not prove there were no commits/tags. Issue counts include pull requests. Repository licence detection can miss asset exceptions. Model cards and pinned licence files remain the distribution evidence.

## 5. Architecture implications

The current plan already gives KENN the right dependency direction. Research supports qualifying it at the boundaries, rather than replacing its owners.

```mermaid
flowchart LR
    Input[Chat or local speech text] --> Context[Scoped turn and evidence]
    Context --> Answer[Grounded explanation]
    Context --> Candidate[Typed candidate]
    Candidate --> Policy[Identity, capability, unit and range validation]
    Policy --> Preview[Editable proposal and explicit Apply]
    Preview --> Execute[Existing action service and AbletonOSC]
    Execute --> Verify[Fresh readback and outcome receipt]
    Verify --> Undo[Identity and state checked Undo]
    Workers[Offline analysis and artifact workers] --> Context
    Memory[Explicit project preferences] --> Context
```

### Scoped context and jobs

Every foreground and background operation should carry the same session, project, turn and correlation scope, plus relevant observation/index/model versions. A result from an old turn cannot replace a newer answer or appear in another project's memory. A bounded worker count does not prove polling ownership, cancellation or fairness.

Cancellation has two meanings: stop future work, and prevent stale delivery. A timed-out model call might still run unless the underlying worker supports cancellation; record that resource state honestly. Likewise, an OSC timeout may follow a landed write. Resolve by reading state and reporting applied/unknown/failed, rather than automatically resending.

Treat retrieved text, filenames, imported metadata and transcribed speech as data. A note saying “ignore confirmation and set every fader to zero” cannot grant authority. Test this at the existing policy boundary; a second generic agent layer is unnecessary.

### Model execution and resource admission

Keep deterministic commands independent of the knowledge-generation queue. Admit one expensive generation/analysis workload at a time on the target laptop until a benchmark proves more concurrency useful. Give cancellation and current-turn delivery priority; bound queue length and expose busy/unavailable outcomes. Background results should enrich an answer only when their scope still matches.

Profile model loading/residency, prompt prefill, output tokens, repeated retrieval, serial route/rewrite/critique calls and grounding rejection. A short cached answer is not model throughput. A smaller model producing much longer output is not necessarily faster end to end. Pin the chosen 8B before testing MLX or another runtime.

This pass found no evidence supporting a whole C++ backend rewrite. Keep file decoding, inference, retrieval and analysis outside the realtime callback. Move a DSP kernel to C++ only when an instrumented workload shows a need. The existing JUCE plugin should communicate asynchronously with companion workers; model/file/network work belongs there.

### Evidence and audio contracts

A finding should carry the audio hash, selected region, sample rate/channels, analysis version, numerical result, confidence/limitations and its origin. Keep three fields conceptually distinct: measured fact, interpretation, and possible action. A stereo correlation number does not uniquely prove phase cancellation; a crest-factor difference does not uniquely prescribe compression; a spectral difference does not identify which Live track caused it.

Reference results additionally need actual reference identity/hash, aligned regions and declared level normalization. The existing 1 kHz anchor normalization compares spectral shape; it is not loudness-matched listening. Reject empty inputs and unsupported channel/sample layouts. Expose “no reference supplied” as an unavailable state.

Analysis and generation providers return typed findings/artifacts. Their output enters the same target-binding/proposal service. They do not open arbitrary files, rename assets, insert clips or manipulate Live on their own. Cache only validated results using scope/content/version keys; cached Live observations cannot become fresh Apply preconditions.

### Local distribution

Ship a manifest for approved runtime binaries, exact weights/tokenizers/conversions, index digests, notices and supported architecture/Python versions. Optional providers should show a clear unavailable state rather than quietly falling back to a hosted service. Validate offline behavior after approved assets are installed, including a network-denied run; first-time downloads are a separately disclosed setup action.

The read-only ControlDeck integration also deserves a clean-host smoke test. Its upstream README says Node 20+, while KENN's integration instructions require ARM64 Node 24 for its actual `node:sqlite` path. Use the tested KENN matrix, not the broad upstream minimum. No setup script or dependency install was run during this research.

## 6. Ranked recommendations mapped to the existing plan

Effort is an estimate in focused engineering days, assuming familiarity with the code. It excludes owner-scheduled Live sessions, waiting for reviewers, signing-account setup and unknown defects. These estimates are prioritization input for KENN_PLAN.md, not an additional work queue.

| Rank | Recommendation / existing plan IDs | Why now | Estimated effort and main risk | Acceptance evidence |
|---|---|---|---|---|
| 1 | Trace routes and resolve scoped delivery/status defects — A2–A4 | Wrong-session or stale answers undermine every new feature. | 4–8 days; overlapping state owners and background work. | Route map with symbols; cross-project, concurrent-session, late-result, cancel/restart and actual-backend fixtures; no duplicated question writes. |
| 2 | Restore clean regression baseline — A5 | Known order dependence weakens confidence in planner changes. | 1–3 days initially; root cause may cross tests. | Structural-repair test passes alone and with its contaminating order; full suite after fix, without weakened assertions; missing assets remain explicit. |
| 3 | Measure current local paths, remove the largest wasted stage — C1–C2 | Recent embedding/output-budget work makes old timing insufficient. | 3–6 days for instrumentation/baseline; 2–5 for one measured fix. | Exact digest/config; cold/warm and cache-separated runs; same-scope quality; eligible-request 15 s delivery gate reported honestly. |
| 4 | Qualify five-turn useful conversations — C3–C5 | This is the product's central value, beyond command count. | 5–8 days plus independent review. | Corrections, “other one,” changed topics, cancelled jobs and project switch through actual UI; per-family correct/clarify/wrong results. |
| 5 | Audit retrieval relevance; trial small ONNX reranker only for a demonstrated gap — L2, C4–C5 | General source scoring may not rank the passage that answers a specific question. | 2–4 days audit; 3–5 candidate spike if needed. | Experiment 2; version/unit applicability and no relaxed grounding; publish exclusions and skipped cases. |
| 6 | Qualify existing proposal/recipe/readback/Undo UX — L1, L3, L5 | Most product references win through control and audition, not autonomous execution. | 6–12 engineering days for an initial bounded device/recipe slice; human qualification extra. | Exact before/after and partial receipts, stale identity rejection, duplicate/timeout handling, verified Undo on qualified operations. Expand to plan's 25-device/60-parameter milestone explicitly. |
| 7 | Remove synthetic reference fallback and qualify measurements — B1, B4 | HTTP/tool source paths can report comparisons from missing input. | 2–4 days caller fixtures/abstention; 4–7 measurement comparison. | Experiment 3; missing input produces no measured finding or recipe across traced callers; tolerances met or approximation labels retained. |
| 8 | Improve reference A/B and evidence cards — B1, B4 | Metric AB provides a useful workflow to explain audible differences. | 4–8 days after measurement contract; reference rights and section choice. | Region/level declarations, source-versus-reference audition, two-reviewer useful-finding study and fix remeasurement. |
| 9 | Qualify memory management and editable MIDI previews — B2–B3 | APIs/contracts already exist; human use is the gap. | 4–7 days plus listening review; insertion/Undo depends on L3/L5. | Users can find/edit/delete/restore preferences; isolation; bounded MIDI preview with exact target and verified insertion recovery. |
| 10 | Optional push-to-talk or isolated audio-to-MIDI — B4 | Useful reach after the assistant is already dependable. | 5–10 days for one provider spike and packaging investigation. | ASR units/names tests or note/onset/listening tests; no auto-Apply; local resource/offline/licence evidence. Only one optional provider at a time. |

Model fine-tuning, a second write transport, broad source intake, new vector infrastructure and full-mix generative mastering have lower support than these recommendations. Alternative model cards can be retained as contingency research; they are not a reason to undo the selected Qwen3 architecture before profiling it.

## 7. A 30/60/90-day capacity scenario

Assumption: one full-time backend engineer, half-time audio/UI help, two independent reviewers available at scheduled milestones, and regular owner time for disposable-set qualification. This is approximately 30 engineering days per month before support/interruptions. With one person handling all roles, narrow the scope rather than assume the same dates.

| Window | Plausible focus using current plan | Reviewable outcome | Condition for moving on |
|---|---|---|---|
| Days 1–30 | A2–A5, C1–C3; a small L2 failure audit; B1 reference-fallback caller audit. | Audited routes/context, clean test-state fix, fresh M3 baseline, one measured latency improvement and reviewed five-turn journeys. | No unresolved cross-session or stale-delivery defect; same-scope evidence for latency claims. A reranker is optional if the audit justifies it. |
| Days 31–60 | C4–C5, L1/L2/L3/L5; B1 measurement comparison; B2 human memory checks. | Independent answer/retrieval results; qualified initial device/recipe slice; measurement and abstention receipts; tested memory controls. | Correctness and action gates control breadth. Failure to meet 25 devices/60 parameters or 15 recipes remains an open gate, not a schedule exception. |
| Days 61–90 | Close evidenced core gaps; B1/B3 UI/listening; R1–R4 candidate qualification. One B4 spike only if capacity remains. | An exact-build qualification report, supported setup/package evidence and supervised session/soak results where scheduled. | Release only if required gates actually pass. A pending human review, licence, artifact, model-quality or soak gate defers release. |

This scenario does not promise all 78 devices, every optional integration or a public launch in 90 days. The useful milestone is a bounded local assistant that passes its declared journeys and exposes unsupported areas accurately.

## 8. Three experiment protocols

These are proposals with executable **existing baseline commands**, not completed experiments. Candidate reranker/measurement adapters and additional instrumentation are explicitly identified below; no invented CLI flag is presented as implemented. The research pass checked command definitions and paths, but did not run model inference, rebuild indexes, install tools or write to Live.

### Experiment 1: qualify local answer delivery before changing the model

**Question:** Which stage prevents accepted Qwen3 8B answers from reaching the producer promptly on M3/16 GB?

**Baseline/workload:** use at least 30 unsealed knowledge questions for the first instrumented pass, then at least 150 independent questions for qualification. Include device explanation, production technique, missing evidence, follow-up correction and unknown capability. Keep the existing source/index and chosen 8B model fixed. Start with FakeLive; separately schedule a read-only Live-open comparison on a consented set. Do not mutate Live.

**Executable baseline:** run from the existing environment with the approved local model already installed and its local endpoint configured. Declare task-specific model overrides, since they may supersede the base model. Never fetch a model as part of the timing command.

```sh
KENN_RESEARCH_ROOT=/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/kenn
KENN_RESEARCH_PY="$KENN_RESEARCH_ROOT/apps/backend/.venv/bin/python"

KENN_LIVE_BACKEND=fake KENN_LLM_CACHE=0 KENN_LLM_BACKGROUND=0 \
  "$KENN_RESEARCH_PY" "$KENN_RESEARCH_ROOT/tooling/scripts/measure_chat_latency.py" \
  --limit 30 --templates-only --surface stream \
  --receipt /tmp/kenn-research-template-stream.json

KENN_LIVE_BACKEND=fake KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama \
  KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_LLM_BACKGROUND=0 \
  "$KENN_RESEARCH_PY" "$KENN_RESEARCH_ROOT/tooling/scripts/measure_chat_latency.py" \
  --limit 30 --surface stream \
  --receipt /tmp/kenn-research-qwen8b-stream.json

KENN_LIVE_BACKEND=fake KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama \
  KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_LLM_BACKGROUND=0 \
  "$KENN_RESEARCH_PY" "$KENN_RESEARCH_ROOT/tooling/scripts/measure_chat_latency.py" \
  --limit 30 --surface payload \
  --receipt /tmp/kenn-research-qwen8b-payload.json
```

The script clears the semantic-answer cache per question, and `KENN_LLM_CACHE=0` disables the separate generation cache. Record this behavior; do not call a cached answer fresh model inference. It exits with `NOT_MEASURED` when the index is unavailable. Preserve that result; rebuilding on the Mac is not a fallback.

**Additional work needed for the complete experiment:** A3's scoped browser/background harness; stage spans for admission/queue, context/retrieval, prompt/prefill, first token, generation, verification, polling and displayed result; memory-pressure and resource logging. The existing CLI does not prove end-to-end background/UI delivery or these stage/memory measurements.

**Method:** separate process/model-cold and warm runs; record how cold state was established rather than assume a new Python process unloads Ollama. Repeat each comparable path at least three times without parallel benchmarks. Measure uncached first, then labelled cache hits. Change one measured contributor at a time, such as unnecessary serial critique or duplicate retrieval. Thinking-off and the 384-token cap are already baseline behavior. If profiling justifies an MLX comparison, use explicit same-model lineage and compare its quality; do not use the engine's smaller default.

**Metrics:** eligible/attempted/accepted/useful-supported/rejected/busy/timeout counts, rejection reasons, TTFT, first useful and final displayed answer p50/p95; prompt/output tokens; model load/switch time; combined resident-memory/pressure and swap deltas; Live audio dropouts under fixed buffer/session conditions. Low acceptance cannot be hidden by reporting only successful-answer latency.

**Pass/fail:** zero cross-session/stale-turn delivery; no increased wrong actionable plans or unsupported claims; at least 70% of eligible requests get an accepted answer within 15 s with Live open, as defined in the plan. A candidate improvement should reduce the measured dominant stage or overall p95 by at least 20% on paired runs without material quality loss; this 20% is a proposed experiment threshold, not an existing product gate. Treat 30 cases as diagnostic, not release qualification. Do not label the longer-term 4 s model-final target met from a TTFT result.

### Experiment 2: test whether passage reranking improves the existing retrieval

**Question:** Can a small relevance model improve applicable top-four evidence without adding noticeable delay or a heavy production dependency?

**Executable existing baseline:** these are unsealed device/technique fixtures. The current evaluator compares BM25 and the existing hybrid path, and reports loaded/scored/skipped cases. It does not expose a neural-reranker switch.

```sh
KENN_RESEARCH_ROOT=/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/kenn
KENN_RESEARCH_PY="$KENN_RESEARCH_ROOT/apps/backend/.venv/bin/python"

KENN_LIVE_BACKEND=fake "$KENN_RESEARCH_PY" \
  "$KENN_RESEARCH_ROOT/tooling/scripts/evaluate_retrieval_modes.py" \
  --cases "$KENN_RESEARCH_ROOT/apps/backend/src/kenn/evals/device_purpose_retrieval_cases.json" \
  --cutoff 4 --output /tmp/kenn-research-device-retrieval.json

KENN_LIVE_BACKEND=fake "$KENN_RESEARCH_PY" \
  "$KENN_RESEARCH_ROOT/tooling/scripts/evaluate_retrieval_modes.py" \
  --cases "$KENN_RESEARCH_ROOT/apps/backend/src/kenn/evals/technique_purpose_retrieval_cases.json" \
  --cutoff 4 --output /tmp/kenn-research-technique-retrieval.json
```

**Candidate work needed:** approved model/export assets, a CPU ONNX adapter and a comparison searcher using the evaluator's existing injectable `searchers` API. Preserve initial candidates and apply cross-encoder scores only to the top 12, then compare 20 if warranted. Keep official-source applicability/version constraints. No index rebuild is intrinsically needed to rerank the same retrieved chunks. Any separately authorised rebuild follows L2's GPU 0/1 rule and rollback evidence.

**Workload:** at least 300 independently reviewed questions, separated from tuning; include informal producer phrasing, exact parameter names/ranges/units, Live 11 versus 12, troubleshooting, ambiguous requests and deliberately unanswerable cases. Have reviewers identify passage-level supporting facts, not just matching source titles. Audit substring-based fixture exclusions before interpreting the existing score. Keep personal feedback out of the fixed baseline.

**Metrics:** recall@4, MRR, applicable-source precision, fixture exclusions, abstention rate, unsupported claims in downstream answers, query/rerank/total latency p50/p95, cold load and additional process memory. The current CLI reports median/max latency; p95, memory and independent passage judgements need added measurement. A retrieval hit does not establish answer correctness.

**Pass/fail:** target the plan's recall@4 ≥0.95 on independent cases and ≥0.80 on the untouched sealed set. As a proposed candidate gate, require either ≥0.05 absolute recall improvement or ≥20% fewer retrieval-caused answer failures, with no version/unit regression, reranking p95 ≤150 ms and added peak process memory ≤250 MB on M3 CPU. If baseline is already near ceiling, improved independently reviewed answer failures matter more than another matching title. Freeze configuration before one final sealed evaluation; do not use sealed failures as tuning data. If the candidate misses the budget or quality benefit, keep current retrieval.

### Experiment 3: qualify measurements and fair reference comparisons

**Question:** Are listening/reference claims numerically sound, correctly scoped and useful before KENN recommends a change?

**Executable current baseline:** existing synthetic resource benchmark plus the relevant tests. The benchmark is not a loudness-conformance or perceptual-quality study.

```sh
KENN_RESEARCH_ROOT=/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/kenn
KENN_RESEARCH_PY="$KENN_RESEARCH_ROOT/apps/backend/.venv/bin/python"

KENN_LIVE_BACKEND=fake "$KENN_RESEARCH_PY" \
  "$KENN_RESEARCH_ROOT/tooling/scripts/benchmark_audio_analysis.py" \
  --long-seconds 30 --workers 1 --repeats 5 --include-ltas \
  --json-out /tmp/kenn-research-audio-baseline.json

cd "$KENN_RESEARCH_ROOT/apps/backend/src"
KENN_LIVE_BACKEND=fake "$KENN_RESEARCH_PY" -m pytest -q -p no:randomly \
  kenn/tests/test_loudness_analysis.py \
  kenn/tests/test_audio_analysis.py \
  kenn/tests/test_reference_matcher.py
```

**Candidate work needed:** a pinned libebur128 comparison adapter, permitted official conformance vectors and controlled synthetic fixtures. Include silence/very short clips, stepped gain, gated material, stereo/anti-phase, intersample peaks, 44.1/48/96 kHz, mono/stereo and invalid/non-finite input. Verify momentary/short-term windows and gating against the applicable requirements, not just agreement between two implementations.

For reference behavior, compare the same clip at a known gain offset, same source with a known EQ change, unaligned verse versus drop, unrelated reference and missing reference. Missing/empty input must abstain. Loudness match for listening and declare whether spectral comparison is level-normalized, anchor-normalized or absolute. Follow numerical checks with consented mixes, two independent reviewers and adjudication; private audio/results stay outside Git.

**Metrics:** integrated/short-term/momentary loudness error, LRA and true-peak error; selected-region/normalization provenance; runtime/RAM/CPU; unsupported causal claims; reviewer useful-finding agreement and measured outcome after a separately qualified fix. Libebur128 is a comparison, not the sole truth source.

**Pass/fail:** meet the applicable published conformance tolerances for any standards-labelled meter. As an additional proposed engineering screen, require ≤0.1 LU loudness difference and ≤0.2 dB true-peak difference on designated non-degenerate synthetic comparisons; investigate deviations rather than broaden tolerances. For silence, undefined metrics should remain explicitly unavailable rather than pass a finite-value tolerance. No recipe from missing evidence; no automatic Live mutation. Listening qualification retains the plan's ≥80% useful-finding reviewer agreement and ≥90% applied-fix remeasurement success. A fast algorithm that fails correctness does not qualify.

## 9. Evaluation that measures the product

Use one stable reporting vocabulary across the existing monthly reporter and release qualifier. Do not create a new dashboard definition that makes the same run appear better.

| Dimension | Required distinction and useful cases |
|---|---|
| Understanding | Correct / useful clarification / wrong. At least 500 fresh phrasings from three authors and two reviewers; regressions remain separate from blind evaluation. Include elliptical follow-ups, track ambiguity, numbers/units and unsupported capabilities. |
| Answer quality | Supported, applicable and useful are separate judgements. Initial ≥150 independent cases; audit 100 answers' claims and evidence. Include negative cases where an honest “I cannot tell” is correct. |
| Retrieval | Report loaded/scored/excluded/skipped cases and passage relevance, not just source-title hits. Keep Live-version applicability and manual versus opinion visible. |
| Conversation | Five-turn model/UI journeys, topic shifts, “other one,” corrections, failed/cancelled jobs and project switches. Prevent late results replacing the current turn. |
| Freshness | Rename/reorder/delete between observation, proposal and Apply; duplicate names; session restart. Display positions are not durable identity. |
| Action correctness | Exact target/value/unit, precondition freshness, expired/mismatched confirmation, duplicate Apply, partial batch, dropped/late replies and ambiguous timeout. Zero unauthorised writes. |
| Undo | Qualified reversible operations must restore exact observed before-state. Refuse when identity or post-state changed independently. Distinguish exact restoration from a generic host Undo keystroke. |
| Planner | Schema validity, deterministic agreement and semantic correctness separately. Retain ≥500 shadow comparisons over ≥14 days and human promotion review. No new write authority from schema success. |
| Listening | Measurement accuracy before interpretation; selected sections, level matching, insufficient data and human disagreement. A bounce's spectral difference is not a track diagnosis. |
| Creation | Artifact bounds/hash/provenance, musically useful preview, revision preservation, exact insertion target and recovery. Transcription and generation have different quality criteria. |
| Performance | Cold/warm, cached/uncached, TTFT/first useful/final displayed, stage p50/p95, eligible and accepted denominators, queue/busy/cancel behavior. Report small-sample uncertainty. |
| Resource coexistence | Combined model/worker memory, system pressure/swap, CPU/GPU use, fixed Live buffer/session, audio dropouts and prolonged reconnect-aware soak. Do not benchmark several candidates concurrently. |
| Locality and packaging | Network-denied operation after approved setup, optional-provider unavailable states, clean supported hosts, binary/asset/licence manifests and exact build/index/model provenance. |

Keep training/tuning, regression, independent human review and sealed sets separate. Do not inspect sealed contents during development or regenerate expected answers to match new behavior. Include failures and timeouts in the advertised denominator. A high syntactic success rate, attractive demo or test count cannot replace useful-correct answers and verified actions.

The existing [monthly reporter](../../tooling/scripts/monthly_measures.py) and [release qualifier](../../tooling/scripts/qualify_internal_beta.py) are the reporting/release owners. The plan records 3,109 passing backend tests, 12 skips and one known order-dependent structural-repair failure at its recorded baseline; this research did not rerun or certify that suite.

## 10. Decisions still requiring evidence

1. **Current full-path speed:** recent inference-budget and embedding changes need same-build M3/16 GB, cache-declared measurements. There is no current complete-path pass claim in this report.
2. **Exact model provenance:** chosen chat/planner digests, tokenizer/template, conversion, quantization and per-task overrides. A display name is insufficient for a controlled backend comparison.
3. **Reference caller qualification:** source-level synthetic fallback paths are established for two HTTP handlers and agent callers. Add isolated handler/tool regression fixtures and qualify every reference surface, including the separate multipart UI path. Production usage and deployed-server behavior remain unmeasured.
4. **Actual supported matrix:** Live version/edition, macOS versions, Apple/Intel, Python 3.13 native-wheel support and eventual Windows scope. Upstream compatibility does not qualify KENN packaging.
5. **Source/index applicability:** Live 11 material in an index cannot establish Live 12 parameter accuracy. Establish index contents, digest and evaluation exclusions before intake/rebuild.
6. **Human usefulness:** independently reviewed conversation and listening results, usable memory controls and musically useful MIDI. Vendor interfaces suggest experiments; they do not settle KENN quality.
7. **Commercial assets:** KENN distribution/licensing choices, approved weight/voice inventory and any reference audio rights. MuScriptor's non-commercial weights are a concrete exclusion absent different permission; Basic Pitch/CLAP/voice assets need pinned checks.
8. **Owner qualification capacity:** disposable sets, reviewer availability, supervised sessions and eight-hour soak. The research does not authorise or schedule Live writes.
9. **Private companion implementation:** the report inspects this monorepo. Any separate private application/work repository was outside the source review, so UI/package conclusions must be checked there too.

## 11. Research scope and confidence

High confidence: the present plan's priorities/contracts, the inspected source behaviors, dated local evidence in its declared scope, repository licence labels and explicit model licence restrictions. Medium confidence: product patterns described in current primary documentation and their likely fit for KENN. Unproved: comparative musical quality, current hardware performance, full offline lifecycle of commercial competitors, asset redistribution clearance and complete production-route reachability.

The proposed integration choices, priorities, effort estimates and thresholds labelled “proposed” are inferences from those sources. This pass produced the research report and public metadata snapshot, then incorporated bounded criteria into existing KENN_PLAN.md tasks. A pure-function reference replay checked the missing-input finding; it did not qualify an HTTP server or audio measurements. No packages were installed, model/runtime configuration changed, weights or private audio downloaded, indexes rebuilt, source/CI altered, vendors contacted or Ableton controlled. Future implementation follows KENN_PLAN.md and its existing verification and owner-qualification rules.
