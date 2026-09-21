# KENN Internal Beta — Frozen Scope

**Status:** DRAFT — owner-approved 2026-09-01 for the Mix Review scope decision (Option 1: scoped beta). Everything else in this document is grounded in verified repo state as of source SHA `e8470a4` and should be reviewed against current code before beta invites go out.

This is the single source of truth for what KENN's internal beta is. The plugin, chat surface, and any documentation must not describe capabilities beyond what is written here.

## 1. Primary beta user

Approved internal testers who are audio engineers (producers/mixers). This is **not** a public or customer-facing release. There is no role-based mode split yet — all testers get the same surface.

## 2. Supported journeys

Two independent journeys ship in this beta. There is no unified product surface combining them yet.

1. **Chat (Ask only)** — text question in, source-backed retrieval answer or explicit `out_of_scope` abstention out. Deployed as a public-reachable service (`products/kenn/chat`), LLM disabled (`AUDIO_TOO_LLM_ENABLED=0`), deterministic.
2. **Mix Review (Ask only, local)** — a local audio file path in, an evidence-backed receipt out, scoped to 3 qualified fault families (see §4). Runs via `products/kenn/mix-review/adapter.py`; **no public HTTP upload path exists in this beta.** Testers run it locally against their own files.

**Suggest / Assist / Auto modes are not part of this beta.** Chat only ever answers or abstains (Ask). Mix Review only ever reports evidence (Ask). AutoMix (`products/kenn/automix/adapter.py`) exists as an engineering boundary — human-approval-gated, local-only — but is explicitly **excluded from this beta**; it is not exposed to testers.

## 3. Supported inputs

**Chat:** free-text mix-engineering questions only.

**Mix Review:**
- A single local audio file path (not stems, not multi-file mixes, not an HTTP upload).
- Formats: `.wav`, `.aif`, `.aiff`, `.flac`, `.m4a`, `.mp3` (`DECODABLE_SUFFIXES` in `Audio_Too/studio/audio_analysis/audio_analysis/mix_review/mix_review_config.py`).
- Max file size: 150 MB (`MAX_UPLOAD_BYTES`).
- Sample rate / channel layout / duration ceilings: **not independently documented or tested for this beta** — do not claim broad support. Treat anything outside a standard stereo mixdown as unverified until the Work Package B test matrix covers it.

## 4. Qualified Mix Review fault families (the hard boundary)

Only these three are qualified, per the most recent evaluation (`KENN_V2D_FINAL_REPORT.md`, 2026-08-23 — still current, no later report exists):

- **Clipping** — 100% precision / 100% recall (target holdout)
- **Inadequate headroom** — 100% precision / 100% recall (target holdout)
- **Persistent L/R imbalance** — 100% precision / 100% recall (target holdout)
- **Healthy-mix false-positive rate: 0%** on the same holdout.

Everything else — masking, phase/polarity, mono compatibility, dynamics, arrangement, loudness beyond headroom/clipping, genre-specific advice — is **not qualified**. The engine abstains rather than fabricates on these (57.1% aggregate recall across the broader 232-case realistic corpus, honestly reported as not-qualified, not hidden). Beta copy, receipts, and any UI must never imply diagnostic competence beyond these three families.

**Human/blind review has not been completed** (an 80-case blind-review pack exists and is ready but unexecuted). Every Mix Review beta result must carry an explicit "not yet human-qualified" caveat until that pack runs.

**Implementation note (2026-09-01):** the qualified detector+gate logic that actually earned this evidence lived only in the evaluation submodule (`products/kenn-evaluation/benchmark/measured_candidates_v2c.py` + `recommendation_gate.py`), never wired into product code. It has now been promoted into `products/kenn/mix-review/qualified_detectors.py` as a frozen, provenance-documented copy, and the adapter runs only that path — see `mix-review/README.md`. Headroom specifically is only ever an actionable finding when the caller passes `scope="mix_in_progress"`; otherwise it always reports as observational, never as a false "no issue" or false finding.

## 5. Supported environments and latency

- **Chat:** runs as a deployable HTTP service (FastAPI, Railway-shaped Dockerfile in `products/kenn/chat/`). No latency SLA has been measured end-to-end for the wrapper; only the underlying retrieval engine has been benchmarked.
- **Mix Review:** local Python CLI only (`python3 products/kenn/mix-review/adapter.py <path>`), run on the tester's own machine against a checked-out `Audio_Too` read-only dependency. Analysis-only latency (engine-internal, not full adapter round trip): p50 3.49 ms / p95 35.54 ms, measured in V2-D against the product decoder — this is a narrow measurement segment, not a full-request SLA, and should not be quoted as one.

## 6. Unsupported cases (must abstain, not fail silently)

- Any Mix Review fault outside the 3 qualified families.
- Stems, multi-file, or non-listed audio formats.
- Files over 150 MB, corrupted, silent, or truncated inputs — these must return a `failed`/`rejected` receipt with an explicit error, never a fabricated finding.
- Chat topics outside mix-engineering advice (DAW scripting, Ableton session automation, audio generation, autonomous-agent requests, taste/ranking questions, anything with no source match).

## 7. Explicit non-goals for this beta

- No general-purpose mixing intelligence claim.
- No AutoMix / unattended rendering exposure.
- No public audio-upload path for Mix Review.
- No VST3/plugin GUI surface — this beta is text-chat and local-CLI only. (If the plugin is intended to be part of the beta, that is a separate, undecided scope expansion — not covered here.)
- No claim of "human-qualified" Mix Review results until the blind-review pack runs.

## 8. Known limitations (surface these to testers, don't bury them)

- `Audio_Too` (the read-only engine dependency) is pinned to `thursday/v2i-long-horizon` — an actively-developed branch owned by Thursday, not KENN. This is a live ownership-overlap risk flagged since V2-D; the beta adapters mitigate it by staying strictly read-only and local, but the underlying repo is not KENN-owned.
- Mix Review broader-family recall is 57.1% and unqualified — expect abstentions, not answers, outside clipping/headroom/L-R imbalance.
- No completed human review of Mix Review output quality.
- No rollback procedure has been proven for the Mix Review evaluation gate.

## 9. Beta status labels

- **KENN Chat** — Internal Beta (retrieval-only, deployed)
- **KENN Mix Review** — Internal Beta (scoped to 3 qualified fault families, local-only, not human-qualified)
- **KENN AutoMix** — Not in beta (engineering boundary only)

## 10. Feedback and escalation route

**Not yet defined.** No tester feedback channel (issue tracker, form, Slack channel, or email) currently exists in the repo for this beta. This must be decided by the owner before invites go out — flagging as an open item rather than inventing one.
