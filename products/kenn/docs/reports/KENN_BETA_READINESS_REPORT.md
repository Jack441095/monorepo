# KENN Beta Readiness Report

Audit date: 2026-09-01. Branch: `develop` (created as `beta-audit-2026-09-01`
from a clean `main` at commit `fd2b483`, renamed to `develop` for ongoing
team collaboration once its fixes were verified). Auditor: Claude
(Sonnet 5), acting as product owner/lead engineer/QA/release manager per
the mission brief. No prior report, filename, or historical claim was
accepted as proof without current-code verification -- including this
report's own earlier drafts, corrected below where they overclaimed.

## 1. Executive summary

KENN's standalone repository extraction was structurally incomplete: Mix
Review, chat, and AutoMix all hard-depended on an external `Audio_Too`
checkout not reachable from this repo's default code paths, and Mix Review
crashed immediately on import as a result. This audit found that
dependency web larger than previously documented (a `thursday` package and
roughly a dozen further sibling modules), and found the knowledge base
shipped with zero actual content in the extraction, despite having real,
substantial retrieval code.

This sprint fixed all three. **Mix Review** now runs entirely standalone
with a KENN-owned, dependency-free analysis engine covering 7 measured
fault families (24 tests). **Chat** now genuinely answers real, in-scope
mix-engineering questions with cited sources: with explicit owner
approval, the real notes corpus (244 files after excluding 2 personal
business/pricing notes and 6 unapproved auto-generated draft stubs, 232
approved) was brought in from the old estate's working tree (the
non-private, non-copyrighted portion only -- see Section 3), a real BM25
keyword index was built locally from it, and a second previously-
undocumented `audio_too` import bug (in the ONNX embedder, unrelated to
the first) was found and fixed along the way. **`server.py`** (the full
local companion server -- Ableton control, specialist tools, and the
route the VST3/AU plugin's "Ask KENN" feature depends on) was also
unblocked: its `audio_too`/`thursday.confirmation` imports and its own
`REPO_ROOT` path bug were fixed the same way, and `/api/ask` was
live-verified returning real, cited answers through the production server.
All 89 tests across `mix-review/`, `automix/`, `chat/`, and (now, for the
first time) `apps/backend/src/kenn/` pass -- up from effectively zero runnable tests
at the start of this audit. AutoMix's render safety boundary was confirmed
sound and the feature was left explicitly disabled, since no render engine
exists to safely enable.

**Correction on an earlier draft of this report:** it originally claimed
Mix Review was "verified with the old estate genuinely absent from disk."
That was an overclaim -- the old `Audio_Too` monorepo is not absent from
this machine, it exists at `<LOCAL_VOLUME>/NITE_DSP/Audio_Too`
(a dirty, in-progress working tree). It is simply not on the sibling path
this repo's default code looks for, so nothing in this audit's runs
accidentally reached it -- see GAP-02 in the gap matrix for the corrected,
narrower claim.

**Product direction note:** the repository owner's near-term goal is a
VST3/Audio Unit plugin for Ableton Live built on this codebase (see also
`docs/KENN_CPP_ARCHITECTURE_NOTES.md`, the owner's hybrid C++/Python
architecture decision). The `plugins/kenn-vst3-au/` scaffold already targets both
formats from one JUCE target and already has real, working, standalone
C++ logic: allocation-free real-time metering (peak, RMS, stereo
correlation/width, crest factor, clipped samples) with zero Python or
network dependency. Its deeper features ("Ask KENN," Mix Review upload,
AutoMix handoff) call a local companion server (`apps/backend/src/kenn/server.py`)
-- **now unblocked and live-verified** (this sprint). **Update: the plugin
was then built and wired up to that server this same sprint.** Both VST3
and AU targets compile cleanly (Xcode Command Line Tools alone, no full
Xcode needed); the existing real-time concurrency stress test passed
under ThreadSanitizer (tool-verified, zero data races); and a new
integration test proved the *compiled plugin binary* -- not just its
source -- reaches a live `server.py` and receives a real, cited diagnostic
answer through its actual `askKenn()` code path. See GAP-12. Not yet done:
loading the built bundle inside an actual DAW (Ableton Live) or Apple's
`auval` validator.

**Recommendation: beta with restrictions.** See Section 10.

## 2. Current architecture

```
KENN/ (standalone repo; default paths need no external checkout)
├── mix-review/        Mix Review: KENN-owned local_engine.py (default) +
│                       optional non-default legacy Audio_Too adapter
├── automix/            AutoMix approval-gate boundary; no render engine
├── chat/               Retrieval-only HTTP wrapper around apps/backend/src/kenn's
│                       chat core; scope/abstention + real cited answers
│                       both working (BM25 index built from real content)
├── apps/backend/src/kenn/        Full KENN engine: retrieval (now indexed), chat
│                       templating, LLM client (disabled by default),
│                       knowledge management, autonomous agent, server,
│                       tool registry. server.py/tool_registry.py/main.py's
│                       deeper commands still blocked by ~15 missing
│                       sibling modules. Zero test coverage of its own.
│   ├── Training_Data_Notes/    232 approved knowledge notes (new)
│   ├── Training_Data_Sources/  citation/source metadata (new)
│   ├── evals/                  evaluation case fixtures (new)
│   └── data/index/              built BM25 index (generated, gitignored)
├── apps/desktop/macos/  Swift macOS app; builds cleanly; first-run
│                       flow requires locating an external Audio_Too repo
├── plugins/kenn-vst3-au/        JUCE-based VST3/AU plugin; builds clean, real-time
│                       metering + server integration both live-verified
├── evaluation/          ~30 historical reports (V2A-V2D) + benchmark
│                       scripts; 5 scripts run standalone and reproduce
│                       deterministically, 2 hard-depend on external
│                       audio_analysis and cannot run here
└── docs/                This audit's deliverables (new this sprint)
```

## 3. Completed audit findings

Full detail in `docs/KNOWN_ISSUES.md`, `docs/KENN_CURRENT_STATE_SUMMARY.md`,
and `docs/KENN_BETA_GAP_MATRIX.md`. Headlines:

- Mix Review, AutoMix, and chat's default engine path all hard-required an
  external `Audio_Too` checkout at import time; none of this was reachable
  from a clean checkout of this repo alone.
- `apps/backend/src/kenn/main.py` and `autonomous_agent.py` computed their own repo
  root one directory level too high, a leftover from the old monorepo's
  deeper nesting, and `main.py` additionally imported a module
  (`repo_python`) that doesn't exist anywhere on disk.
- Two `requirements.txt` files pointed at paths entirely outside this
  repository; `pip install` failed immediately on a clean checkout.
- The knowledge base shipped zero content in the original extraction: real
  retrieval/ranking code, no notes, no index. **Resolved this sprint**
  (see below) with owner approval to selectively bring in real content.
- A second, previously-undocumented `audio_too` import
  (`onnx_embedder.py`'s `ONNX_SESSION_INIT_LOCK`, just a threading lock)
  crashed the *entire* index build after processing all 252 notes -- found
  only by actually attempting a build, not by static analysis. Fixed with
  a local `threading.Lock()`.
- Beyond the previously-documented `Audio_Too`/`audio_too`/`audio_analysis`
  references, this audit found a previously-undocumented dependency on a
  `thursday` package (confirmation/tool-dispatch layer) and roughly a
  dozen further missing sibling modules reachable from `server.py` and
  `tool_registry.py`. **Update (2026-09-01):** the two hard-blocking ones
  (`audio_too`, `thursday.confirmation`) were investigated individually in
  the old estate's read-only working tree, found to be small, self-
  contained, stdlib-only modules, and ported as KENN-owned code (see
  Section 3 below and ISSUE-08/GAP-04). `server.py` now starts standalone
  and its `/api/ask` route returns real, cited answers -- live-verified.
  The remaining ~10 specialist-feature imports were each checked
  individually and confirmed to already fail safely (clean error response,
  not a crash) in the original code; they remain unimplemented.
- **Knowledge content sourcing (explicit owner approval obtained):** the
  old estate's working tree at `<LOCAL_VOLUME>/NITE_DSP/Audio_Too`
  was used as a read-only source for exactly four items: 252 knowledge
  notes (232 marked `Status: Approved` and indexed), their source-citation
  metadata, one generated PDF checklist, and evaluation case fixtures
  (~1.2MB total). Explicitly **not** brought in: raw third-party video
  transcripts (copyright risk -- the notes are KENN's own cited,
  paraphrased derivatives, which is what's safe to keep), 92MB of user
  chat/session history (private data), the shared cross-product business
  database, fine-tuning data, and a 1.1GB prebuilt binary artifacts/index
  directory (regenerated locally instead, from the copied source content,
  so it's reproducible and fresh rather than an opaque binary import). A
  second review pass, at the owner's request, additionally removed 2 notes
  containing the owner's personal business pricing/rate information
  (`jack-pricing-revisions.md`, `client-mix-pricing-and-quotes.md`) --
  those aren't generic audio-engineering knowledge and weren't meant to be
  in a repo shared with collaborators. Final corpus: 244 notes, 232
  approved and indexed (1104 chunks).
- No secrets, credentials, or hardcoded absolute local paths were found
  anywhere in the repository.
- The historical evaluation reports are largely honest about their own
  limits (repeatedly flagging synthetic-only scope, deferred live-provider
  qualification, explicit "not a claim of generalised production
  performance" language) -- but their headline numbers split into
  genuinely reproducible (5 scripts, verified live) and currently
  unreproducible (2 scripts requiring the absent external package).

## 4. Critical and non-critical issues

**Critical** (blocking beta claims beyond the current restricted scope):
- No human or real-mix qualification exists yet for Mix Review's fault
  families -- only synthetic unit tests (GAP-01).
- No formal retrieval-relevance/citation-correctness benchmark exists for
  chat's new index -- only live spot-checks and unit tests (GAP-03).
- `server.py`'s ~10 remaining specialist-feature imports (Ableton hardware
  bridge, stem separation/upload, voice synthesis, AutoMix web upload)
  have no KENN-owned implementation -- each fails safely (clean error, not
  a crash), but none of those features actually work (GAP-04).

**Non-critical** (documented, not blocking the restricted beta):
- Semantic (embedding) search in chat isn't active yet -- BM25-only, by a
  missing model-download step, not a design flaw (GAP-03).
- AutoMix has no render engine (explicitly disabled, not a beta blocker
  since it's excluded from scope).
- Desktop companion excluded from beta scope (blocked by design, ISSUE-12).
  VST3/AU plugin builds clean and its server integration is live-verified
  (GAP-12) but hasn't been loaded inside an actual DAW yet -- excluded
  from beta scope pending that manual step.
- A few knowledge-item metadata fields (per-item confidence, evidence
  class) aren't populated yet, though most of the required schema already
  is (GAP-06).
- No dedicated adversarial (prompt-injection-style) test suite for
  filename/metadata handling, though the current design has no LLM in the
  retrieval-only chat path and Mix Review never interprets filenames as
  content.

## 5. Recommended improvements (ranked)

1. **Load the built VST3/AU plugin inside Ableton Live** -- the plugin
   builds clean and its network integration is proven against the real
   server (GAP-12); the one remaining step is an actual DAW load-test with
   `apps/backend/src/kenn/server.py` running alongside it, plus optionally Apple's
   `auval` validator for the AU bundle (not run this sprint -- would
   require installing into the user's live plugin folder).
2. **Real-mix, human-reviewed benchmark for Mix Review** -- move fault
   families from "unit-tested" to "qualified" with actual precision/
   recall/false-flag measurement, following the V2B/V2C methodology but
   against the new local engine.
3. **Formal chat retrieval/citation benchmark** using the now-available
   `evals/` case files -- move chat from "live-verified to work" to
   "measured to work well."
4. **Fetch the ONNX embedding model** (`scripts/fetch_embedding_model.py`
   doesn't exist in this repo -- needs porting or rewriting) to enable
   semantic search on top of the already-working BM25 index.
5. **Scoped follow-up per specialist `server.py` route** (Ableton hardware
   bridge, stem separation, voice synthesis, AutoMix upload) --
   remove/replace/adapter/disable each individually, now that the routes
   fail safely and aren't blocking the core server.
6. **Adversarial input test suite** for Mix Review (malformed metadata,
   crafted filenames, oversized files).
7. **KENN-owned AutoMix render path** (or formal retirement of AutoMix) --
   lower priority since it's already safely disabled.

## 6. Changes implemented this sprint

On branch `develop` (formerly `beta-audit-2026-09-01`), commits each
independently revertable (see `git log`):
- KENN-owned Mix Review engine (`mix-review/core/local_engine.py`), 24
  tests, adapter rewired to use it by default with the legacy engine kept
  as an explicit non-default opt-in.
- Fixed repo-root path bugs in `main.py`, `autonomous_agent.py`, and
  `automix/adapter.py`.
- Fixed two broken `requirements.txt` paths and added a root-level one.
- Added a minimal KENN-owned `scripts/repo_python.py` replacing a missing
  monorepo utility.
- Rewired `chat/app.py`'s default engine path to this repo's own `source/`
  tree, and hardened it to fail honestly (not crash) when the knowledge
  index is missing.
- Corrected a misleading `.gitignore` header and updated `README.md`,
  `mix-review/README.md`, and `automix/README.md`.
- This documentation set (`docs/`), including a self-correction of an
  earlier overclaim (Section 1).
- **With explicit owner approval:** brought in the real knowledge-base
  content (notes, source citations, eval fixtures) from the old estate,
  fixed a second `audio_too` import bug found while building the index
  (`onnx_embedder.py`), built a real BM25 index locally, and live-verified
  chat answering real questions with cited sources.
- Ported six small, self-contained modules as KENN-owned code
  (`core/platform_contracts.py`, `core/endpoint_policy.py`,
  `core/request_validation.py`, `core/action_policy.py`,
  `core/path_safety.py`, `core/confirmation.py`, `scripts/log_setup.py`)
  to remove `server.py`/`tool_registry.py`/`response_contract.py`'s hard
  `audio_too`/`thursday` dependencies, fixed `server.py`'s own
  `REPO_ROOT` path bug, and added `apps/backend/src/kenn/tests/` -- this package's
  first-ever test coverage (22 tests, including a live server smoke test).
- Added a scoped `.claude/settings.json` permission rule (at the owner's
  request) so future sessions don't hit avoidable friction copying from
  the already-approved external reference path used during this audit.
- **Built the VST3/AU plugin and wired it to the real server** (GAP-12):
  configured and built `plugins/kenn-vst3-au/` clean with only Xcode Command Line
  Tools; ran the existing (previously never-run) real-time concurrency
  stress test plain and under ThreadSanitizer, both clean; added
  `Source/test_server_integration_main.cpp` (a new `TestServerIntegration`
  CMake target) that constructs the actual compiled
  `KENNMixAssistantAudioProcessor` and calls its real network methods
  against a live `server.py` -- live-verified end-to-end.
- Set up the GitHub remote (`https://github.com/Jack441095/kenn-standalone`,
  renamed from a typo at the owner's request) and pushed `main`/`develop`
  for team collaboration.

## 7. Tests and evidence

```
python3 -m pytest mix-review/tests automix/tests chat/tests apps/backend/src/kenn/tests -q
# 89 tests: 89 passed, 0 failed
```

- `mix-review/tests`: 24/24 passing.
- `automix/tests`: 4/4 passing (safety boundary only).
- `chat/tests`: 39/39 passing (was 0/38 collectible at audit start).
- `apps/backend/src/kenn/tests`: 22/22 passing (was 0 -- no tests existed anywhere
  under `apps/backend/src/kenn/` at audit start).
- Live verification beyond unit tests:
  - Mix Review CLI run end-to-end against a synthetic WAV, default engine
    confirmed to resolve to `mix-review/core/local_engine.py`.
  - `python3 apps/backend/src/kenn/main.py build` run end-to-end: 1104 chunks
    indexed from 232 approved notes + 1 PDF (12 notes correctly excluded
    for not being `Status: Approved`).
  - Three real mix-engineering questions asked through `chat/app.py`'s
    actual answer path (not mocked): all three returned `found: true`,
    `confidence: "high"`, and correct, specific cited sources (e.g. a
    mono-compatibility question cited `stereo-width-mono-compatibility.md`).
  - `apps/backend/src/kenn/server.py` started standalone and `/api/ask` returned a
    real, cited diagnostic answer through the full production server
    (distinct from and in addition to the `chat/app.py` verification
    above -- proves the full server, not just the narrow public wrapper).
  - Desktop companion build script (`build_macos_app.sh`) confirmed to
    compile cleanly.
  - `evaluation/benchmark/run_audio_holdout_v2c.py` confirmed to run
    standalone and reproduce its recorded output deterministically.
  - `plugins/kenn-vst3-au/` built clean (VST3 + AU targets); its real-time
    concurrency stress test passed plain and under ThreadSanitizer
    (tool-verified, zero data races); a new integration test proved the
    *compiled binary* reaches a live `server.py` and gets a real, cited
    diagnostic answer through its actual `askKenn()` code path (GAP-12).

## 8. Remaining blockers

See `docs/KENN_BETA_GAP_MATRIX.md` for the full list with exit conditions.
Summary: ~10 specialist `server.py` routes (Ableton hardware bridge, stem
separation/upload, voice synthesis, AutoMix web upload) have no
KENN-owned implementation, though each fails safely (GAP-04); no real-mix
human qualification for Mix Review (GAP-01); no formal chat retrieval
benchmark (GAP-03); no AutoMix render engine (GAP-05); no evaluation
harness for the new local engine beyond its unit tests (GAP-07); desktop
companion blocked by design (ISSUE-12); VST3/AU plugin built and
integration-verified against the server this sprint, but not yet loaded
inside an actual DAW or run through Apple's `auval` validator (GAP-12).

## 9. Beta risks

- **Overclaiming risk**: treating "Mix Review/Chat/server run standalone
  and pass tests" as "results are qualified/benchmarked." None have been
  through formal human/quality review yet -- tester-facing docs say so
  explicitly.
- **Chat scope risk**: chat only knows what's in its 232 indexed notes
  (mostly Ableton devices, mixing/mastering fundamentals, and Wwise game
  audio) and only via keyword (BM25) matching, not semantic understanding
  -- a real but narrower/less flexible tool than "ask it anything." This
  applies equally whether reached via `chat/app.py` or `server.py`, since
  both call the same underlying answer engine.
- **Dependency-surface risk**: the `thursday` package and ~15 other
  missing modules found this sprint (plus a second `audio_too` bug found
  only by actually running an index build, and a third found only by
  actually starting the server) confirm static analysis alone keeps
  under-counting this repo's real dependency surface -- each fix this
  sprint came from actually running the code, not just reading it. Expect
  the same pattern in the remaining ~10 specialist routes if they're ever
  brought into scope.
- **Data-handling risk**: knowledge content was sourced from a
  dirty/in-progress external working tree with explicit owner approval and
  a deliberately narrow, documented selection (Section 3) -- re-running
  this process for any *other* content from that estate should get the
  same explicit, scoped approval, not be assumed blanket-authorized.
- **Safety risk: low.** Mix Review, chat, and the server's `/api/ask`
  route are all read-only/no-mutation, and every claim in this report was
  verified against running code, not documentation.

## 10. Recommendation: **beta with restrictions**

Ship an internal-only beta covering the Mix Review CLI
(`mix-review/adapter.py`) and Chat, both for testers explicitly told which
parts are unit-tested-but-not-formally-qualified (see
`docs/KENN_BETA_TESTER_GUIDE.md`). For Chat, `chat/app.py`'s narrow public
wrapper remains the recommended tester-facing surface (deliberately scoped
request/response boundary, rate limiting, source-text stripping);
`apps/backend/src/kenn/server.py` is now also verified working and is the right
integration target for VST3/AU plugin development, but it is a
loopback-only local companion aimed at developers building that
integration, not at internal testers directly -- keep that distinction in
any beta communication. Do **not** expose AutoMix, the desktop companion,
or any of `server.py`'s ~10 unimplemented specialist routes (Ableton
hardware control, stem separation, voice synthesis) in this beta -- they
remain blocked and are not what `server.py`'s newly-verified status covers.

This is not "beta now" because several definition-of-done criteria from
the mission brief are unmet (measured retrieval quality, human-qualified
Mix Review results, a fully standalone specialist-tool surface, semantic
search). It is not "not ready" because multiple real, safe, standalone,
tested capabilities exist today and running them carries low risk (no
audio mutation, no LLM, explicit abstention, easy rollback). Restricting
the beta to exactly those capabilities, explicitly and in writing, is the
honest middle ground this repository's own operating rules call for -- and
this sprint materially advanced the concrete next step for the VST3/AU
plugin direction, since its "Ask KENN" feature now has a working server to
integrate against.
