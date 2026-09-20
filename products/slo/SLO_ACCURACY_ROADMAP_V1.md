# SLO Classification Accuracy Roadmap V1

**Purpose:** answer "how do we get to classifying all sounds correctly?" honestly, as a real long-term plan, not just the near-term stages. Short version on the ceiling: literal 100% isn't achievable or even the right target — this doc explains why — but the plan below is the real, sequenced path to get as close as the data, the model, and the product's own design philosophy allow, and it doesn't stop at "recalibrate the classifier."

## Why 100% is the wrong target, not just a hard one

Three separate, real things this session found make "100%" an incoherent goal, not just an ambitious one:

1. **Ground truth itself is not 100% clean.** Twice this session, a "classifier error" turned out to be a labeling bug in the benchmark corpus, not the classifier: the Vocal Loop "BVs" abbreviation fix, and the FX ground-truth fix (individually-named instrument stems like `Sentient - Kick.wav` blanket-labeled "FX" by a folder-keyword match, plus two `Percs & Fx` folders that openly mix two categories). If the yardstick has errors in it, no classifier can score 100% against it — fixing this raises the *ceiling*, but the ceiling is still below 100%.
2. **Some content is genuinely ambiguous, not under-measured.** A one-shot that's acoustically halfway between Kick and Percussion, or a pad that's halfway between Atmosphere and Synth, doesn't have one true answer a better model would find — it has two defensible answers. `AbletonTaxonomy.h`'s own design principle already says this out loud: *"Deliberately does NOT attempt distinctions the current DSP feature set can't actually support with real confidence... inventing those would mean presenting a guess as a classification, which the design explicitly rejects."* Forcing a confident single label onto genuinely ambiguous content isn't more accurate — it's more confidently wrong.
3. **The taxonomy is finite; real sounds aren't.** SLO has 17 classes. Guitar loops, orchestral instruments, world instruments, spoken word, field recordings — none of these have a home today (confirmed directly: `AcousticClassifierWeights.h`'s linear head has exactly 16 output classes, and doesn't even include Atmosphere as one of them — that's not a threshold problem, it's architectural). "Classify all sounds correctly" requires an explicit, ongoing product decision about how much to expand the taxonomy versus how much to lean on an honest "Unknown, here's my best guess" for what's left outside it. That's a product call, not something engineering resolves on its own.

**The real target**: maximize accuracy on the content that genuinely has a confident right answer, keep expanding what counts as "confident" through real data and real model investment over time, and make "Unknown / low-confidence" a trustworthy, useful outcome for whatever's left — not a target percentage that pretends ambiguity and taxonomy limits don't exist.

## Where the numbers stand today (V2 benchmark, 5,157 files, 15 vendors, all 17 classes measured)

| Metric | Full evidence (real filenames+folders) | Audio-only (DSP/ML alone) |
|---|---|---|
| Accuracy | 71.5% | 39.0% |
| Macro F1 | 0.527 | 0.395 |

Full-evidence accuracy is dominated by FILENAME/FOLDER evidence winning (81.2%/77.9% accurate when they win) — a realistic proxy for everyday use, since most producers' own files have *some* naming signal. DSP-only accuracy (no naming help) is the real bottleneck, and recalibration (Stage 2 below) is the first thing that's actually moved it.

## The sequencing question that matters most

The single biggest planning mistake available here is building the expensive, high-effort parts (a full training pipeline, a correction-aggregation backend) before there's a live userbase to make them worth anything. The active-learning/correction loop — the mechanism that actually gets this system closer to "classify everything correctly" over time, rather than through one-time manual data-hunting sessions like this one — only generates value once real users exist and correct real mislabels. Based on this codebase (beta readiness docs, no evidence of a live userbase yet), that hasn't happened. The plan below is ordered so cheap, no-user-needed work happens first, and the expensive infrastructure investment happens only once shipping unlocks it.

## Staged plan

### Stage 0 — done this session
Decay-time envelope-follower bug fix; Long/Short Decay and Wide/Mono predicted-tag attributes; Vocal Loop "BVs" and FX ground-truth fixes; real-corpus benchmark expanded 620→5,157 files, 14→15 vendors, all 17 classes now measured — all using data already owned, no acquisition needed.

### Stage 1 — clean what we can measure for free (no sign-off needed, low risk) — mostly done
- Done: closed the Synth/Synth Loop/Vocal Loop/Music Loop measurement blind spot (all four score well above the corpus average).
- Done: FX ground-truth fix; Atmosphere's ground-truth issue documented (not yet fixed — see below).
- Still open: apply the same forensic method that found the Vocal Loop and FX bugs to every remaining class, starting with Atmosphere (same repeating "pad one-shot mislabeled" pattern already spotted).
- Still open: map real, currently-untapped vendor volume where folder structure allows it (Mike Shinoda Drums 5,144 files, IMANU 301, Organic Electronics 2 304, Drum Breaks 132) — real engineering effort, no product-risk decision.
- **Judgment call already made**: DSP-only accuracy didn't move at all across every Stage 1 fix (stuck at 7.3-7.4%) — that's the evidence that said Stage 2, not more Stage 1 work, was next.

### Stage 2 — recalibrate the classifier's centroids/thresholds -- ATTEMPTED, REVERTED (null result)
- Rebuilt per-class centroids and OOD thresholds against the 5,157-file, 15-vendor, full-17-class corpus, replacing the original single-vendor 1,607-file calibration. Isolated Python validation looked like a clear win (known recall 30.9%→44.2%, false-unknown 40.7%→10.9%), at the cost of OOD-negative false-known rising 53.7%→82.4%.
- **The isolated validation was wrong about the net effect.** Real end-to-end benchmarking at the recommended 25% budget showed a *regression* (39.0%→35.5% real audio-only accuracy), not an improvement. A further sweep of stricter budgets (35/40/50/60/75%) found every single one worse than baseline, plateauing around 30% — ruling out "wrong threshold" as the explanation.
- **Root cause**: the isolated validation didn't model the real pipeline's fallback to the DSP heuristic when the OOD gate rejects a sample. A more permissive gate routes more marginal samples into ML override, some of which the DSP heuristic may have already gotten right by chance — replacing a lucky-correct DSP guess with a less-reliable ML one can net-decrease real accuracy even when the ML path's own isolated numbers improve. Full detail, methodology, and all sweep numbers in `docs/classification/OOD_RECALIBRATION_V1_REPORT.md`.
- **Fully reverted**: `AcousticClassifierCentroids.h` confirmed byte-identical to its pre-recalibration state, real benchmark re-confirmed at exactly 39.0%/71.5%, full regression suite (28 binaries) clean. No production code changed.
- **Lesson for next time**: any future recalibration attempt must be validated against the real end-to-end pipeline (DSP-fallback interaction included) from the start, not an isolated ML-path simulation.

### Stage 3 — cheap, model-untouching wins (no users needed, can start immediately, ranked above active learning by the existing research baseline)
These come *before* the expensive infrastructure below because they're cheap, don't require a live userbase, and the research baseline (`docs/SLO_CLASSIFICATION_V5_RESEARCH_BASELINE.md`) ranks them higher than active learning specifically because of that:
- **Energy-based OOD experiment** (research baseline §5) — **recommended next**, following Stage 2's null result. An alternative OOD signal (derived from the linear head's own logits, e.g. `E(x) = -T*logsumexp(logits/T)`, rather than embedding-centroid cosine similarity) that might rank samples by reliability differently enough to avoid Stage 2's specific failure mode. Validate against the real end-to-end pipeline from the start this time, per the lesson above. Untried so far.
- **Per-class confidence instrumentation** (research baseline §3's cheap alternative to a full hierarchical retrain) — surfaces category-vs-subcategory ambiguity in the UI without touching the model at all. This is also most of what Stage 5's "graduated confidence" UX needs on the backend side.
- **Build the graduated-confidence result bundle** (likely category + possible subtype + attributes + confidence, surfaced together, instead of today's single-best-guess-or-Unknown binary) — already flagged as a real UX gap in `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md`. This is the honest product-level endpoint for genuinely ambiguous content, and it needs no new data or model work, just using confidence signals that mostly already exist.
- **Extend correction-capture plumbing now, before shipping.** `SampleItem::tagUserOverridden`/`tagSource` already exist locally (to stop re-overwriting a user's manual edit) but capture nothing beyond that. Extend this to optionally log the *embedding* (not the raw audio — a 512D float vector doesn't reveal the actual sound content, a real privacy win) alongside the corrected label, opt-in, stored locally until Stage 6 gives it somewhere to go. Cheap, buildable now, unlocks everything in Stage 6-7 the moment there are real users.

### Stage 4 — taxonomy completeness (an ongoing product decision, not a one-time engineering task)
Revisit periodically, informed by what real usage actually contains: does covering more of the real world (guitar, orchestral, world instruments, spoken word) mean adding primary categories, or is a good "Unknown, likely X" answer sufficient for content outside the current 17? This is explicitly Jack's call each time it comes up, not something to decide unilaterally by adding categories as convenient.

### Stage 5 — ship to real users
A prerequisite gate for everything below, not something scoped or built here — tracked in SLO's own beta-readiness docs (`SLO_PRIVATE_BETA_PLAN_V1.md` etc.), a separate workstream from classification accuracy.

### Stage 6 — correction aggregation backend (build only once Stage 5 is real)
Real infrastructure that doesn't exist yet: a way to receive the opt-in embedding+correction data Stage 3 started capturing locally, across many users, with real privacy/consent handling (this is the point where "opt-in" needs to be a genuine, clearly-communicated user choice, not a checkbox nobody reads). Not worth building before there's a userbase to generate the data it would aggregate.

### Stage 7 — a real training pipeline (build only once Stage 6 has accumulated real data)
This repo has no training code today — only inference/ONNX-export tooling. Building this means: a data pipeline from Stage 6's aggregated corrections, an actual training script, an evaluation harness (the same leakage-free discipline used throughout this session, not a shortcut), and a safe model-update/rollout mechanism to ship new weights to installed copies without breaking anyone mid-session. This is real ML engineering, comparable in scope to everything else in this roadmap combined — don't start it speculatively.

### Stage 8 — embedding-space investment (only after Stage 7 exists and only with evidence it's needed)
Run the t-SNE/UMAP + per-class silhouette-score audit the research baseline recommends before touching the embedding model itself — so far there's no direct evidence that embedding separation (as opposed to decision logic around it) is the dominant error source. Only if that audit shows a real separability problem: fine-tune the embedding backbone on the by-then-much-larger real correction dataset, or evaluate a stronger backbone entirely. Both are the highest-cost, lowest-current-evidence items on this whole roadmap.

## What "done" looks like

Not 100%, and not a single finished state — an ever-improving system with a live feedback loop, honest uncertainty communication (graduated confidence, not a confident wrong guess), a taxonomy whose scope is a deliberate, periodically-revisited product decision rather than an accident of which vendor packs happened to be on hand, and real training infrastructure so it gets better because it's used, not because someone runs another manual recalibration pass every few months. That's the real target. Getting there is a multi-stage, multi-month-or-longer investment — this roadmap is the order to do it in, not a single project with an end date.
