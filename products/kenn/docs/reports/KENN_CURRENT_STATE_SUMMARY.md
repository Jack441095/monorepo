# KENN Current State Summary

Audit date: 2026-09-01, branch `develop` (created as `beta-audit-2026-09-01`). This summarises
every surface's status against seven categories: **working**, **partially
working**, **demo-only**, **dependent on external/legacy code**, **tested
but not qualified**, **blocked**, **ready for beta**. A surface can carry
more than one label for different sub-parts. See `docs/KNOWN_ISSUES.md` for
the specific bugs behind each finding and `docs/KENN_BETA_GAP_MATRIX.md` for
the requirement-by-requirement gap analysis.

## Mix Review (`mix-review/`)

**Working, tested but not qualified for production claims.**

- The default engine (`core/local_engine.py`) is KENN-owned, uses an optional
  NumPy accelerator with a standard-library fallback, and runs standalone from
  this repo alone. Note (corrected 2026-09-01): the
  old `Audio_Too` estate is not actually absent from this machine -- it
  exists at `<LOCAL_VOLUME>/NITE_DSP/Audio_Too` (the dirty
  monorepo working tree the migration receipt excludes) -- it is simply not
  on the sibling path this repo's default code looks for, and was never
  reached during this audit's runs. See GAP-02 in the gap matrix.
- Measures 7 fault families with real evidence, confidence, and severity:
  clipping, headroom, silence/truncation, channel imbalance, phase/polarity
  & mono compatibility, DC offset, and an approximate (non-LUFS) loudness
  estimate. 6 further families (masking, tonal balance, arrangement/
  dynamics, genre context, calibrated BS.1770 loudness, true-peak) are
  explicitly marked "not evaluated" in every report rather than silently
  omitted.
- 28/28 Mix Review tests pass against synthetic WAV fixtures constructed to
  exercise each fault family (clipping, hot peaks, silence, imbalance,
  inverted polarity, mono input, sub-1-second input, 24-bit PCM, corrupted
  header).
- **Not qualified**: no human listening review, no real-mix benchmark
  corpus, no precision/recall/false-flag measurement on anything but
  synthetic fixtures constructed by this audit. The historical V2B/V2C
  evaluation reports measured similar fault families (clipping, headroom,
  L-R imbalance) on a different, larger synthetic corpus and reported
  100%/100% on their 88-case holdout -- reproducible today by running
  `evaluation/benchmark/run_audio_holdout_v2c.py` -- but those numbers
  apply to a *different* implementation (the historical `audio_analysis`
  engine) than the one now wired into this repo. Do not merge the two
  claims.
- **Legacy engine**: preserved as an explicit, non-default opt-in
  (`KENN_MIX_REVIEW_ENGINE=audio_too_legacy`) for future parity comparison;
  never reached by the default path.
- AutoMix invocation, report sharing, database persistence, and any
  Ableton action remain entirely out of this adapter's scope by design.

## AutoMix (`automix/`)

**Blocked; explicitly beta-disabled. Safety boundary working and tested.**

- The approval-gate contract (`adapter.py`) is KENN-owned, tested (4/4
  passing), and behaves safely: no engine call without explicit
  `approved=True`; output path checked to be outside both the source stems
  directory and any legacy Audio_Too checkout; engine failures are caught
  and reported as a `status: "failed"` receipt, never a crash or silent
  no-op.
- The actual render engine (`Audio_Too/scripts/automix_local.py`) does not
  exist in this repository. There is no KENN-owned replacement.
- Recommendation: keep disabled for beta. See ISSUE-07 in
  `docs/KNOWN_ISSUES.md` for the replacement plan.

## Chat (`chat/`)

**Working end-to-end, tested but not formally benchmarked. BM25-only
(semantic search pending a model download).**

- The HTTP boundary layer -- scope classification, out-of-scope
  abstention, rate limiting, request validation, source-text stripping,
  CORS allowlist enforcement -- is real, KENN-owned, and imports and runs
  standalone (previously blocked entirely: `RuntimeError` at import
  because the default engine path pointed at an external checkout).
  39/39 tests pass.
- **Update (2026-09-01):** with explicit approval, the real knowledge
  content (244 notes after excluding 2 personal business/pricing notes
  and 6 unapproved auto-generated draft stubs, 232 approved and indexed;
  source-citation metadata;
  evaluation case files) was brought in from the old estate's working tree
  and a real BM25 retrieval index was built locally
  (`python3 apps/backend/src/kenn/main.py build`). Chat now genuinely answers
  in-scope mix-engineering questions with cited sources -- live-verified
  with 3 real questions during this audit, e.g. "Why does my mix collapse
  when I check it in mono?" correctly returned `found: true`,
  `confidence: "high"`, and cited `mix-translation-checks.md`,
  `vocal-buried-in-mix.md`, `stereo-width-mono-compatibility.md`.
- Semantic (embedding) search still degrades gracefully to BM25-only --
  the ONNX model weights (~90MB) require a fetch script
  (`scripts/fetch_embedding_model.py`) not present in this repo. This is a
  disclosed limitation, not a functional blocker: BM25 alone produced
  accurate, well-cited answers in every question tested this sprint.
- No formal retrieval-relevance/citation-correctness benchmark has been
  run against the new index (only live spot-checks and the existing unit
  test suite) -- do not claim measured answer quality beyond "works and is
  cited" until that exists.
- LLM use is correctly disabled by default (`AUDIO_TOO_LLM_ENABLED=0`,
  enforced both by `.env.example` and hardcoded in `chat/app.py` before any
  KENN module import) and the retrieval-only boundary is also enforced in
  code (specialist dispatch hooks are monkeypatched to no-ops during every
  request), not just by convention.

## Full KENN engine (`apps/backend/src/kenn/`)

**Core server now working and tested. Specialist tool routes remain
unimplemented but fail safely. `main.py`'s deeper subcommands still
blocked.**

- **Update (2026-09-01):** `server.py` and `core/tool_registry.py` were
  blocked by unguarded imports of `audio_too` and `thursday.confirmation`
  plus a `REPO_ROOT` path bug. Each blocking import was investigated
  individually in the old estate's read-only working tree; all were small,
  self-contained, stdlib-only modules with no real coupling to anything
  else in those products, and were ported as KENN-owned code (see
  ISSUE-08, resolved). `server.py` now starts standalone and its core
  route works end-to-end: live-verified `/api/health` and `/api/ask`
  (the latter returning a real, cited diagnostic answer through the full
  production server, not just `chat/app.py`'s narrower public wrapper).
  This is the same "Ask KENN" capability the VST3/AU plugin's companion
  integration needs.
- The ~10 remaining specialist routes (Ableton hardware bridge, stem
  separation/upload, voice synthesis, AutoMix web upload) still can't
  function -- their dependencies (`ableton_bridge`, `stem_separation_bridge`,
  `stem_uploads`, `thursday.voice_output`, `automix_public`/`automix_jobs`,
  `song_projects`, `demo_feedback`, `agents`, `audiogen_bridge`, `db`) are
  not in this repo -- but each call site was individually verified (by
  reading the code, not assumed) to already be wrapped in `try`/`except`,
  so hitting one of these routes returns a clean error response rather
  than crashing the request or the server.
- `main.py`'s `build`/`ask`/`chat` subcommands work (the `repo_python`
  import bug is fixed); `build-checklist`/`download-pdfs` still reference
  scripts not present in this repo (low priority, non-core).
- `retrieval/retrieval.py` (hybrid BM25 + ONNX embedding search, reranking,
  topic synonyms) is real, substantial, self-contained code. It had one
  spurious external-package import (`onnx_embedder.py`'s
  `ONNX_SESSION_INIT_LOCK`, fixed this sprint -- see ISSUE-15) and, as of
  this sprint, real content to search: 232 approved notes, indexed via
  BM25 (semantic embedding search still pending a model download -- see
  ISSUE-09/GAP-03).
- `core/chat_answer.py` (~2400 lines of deterministic answer templating,
  diagnostic plans, grounding/quality gates) is real and working logic,
  reachable via both `chat/app.py`'s narrow path and now `server.py`'s
  full path.
- `llm/llm_rewrite.py` is a real, well-engineered, self-contained LLM
  client (caching, retry, streaming) that is correctly disabled by default.
  The separate local fine-tuned model path (`kenn_lm.py`) is deliberately
  gated off, noted in its own comments as rejected by an internal
  evaluation on 2026-07-14.
- `knowledge/` (reasoning traces, corrections, trust scores, contradiction
  detection, maintenance scheduling) is genuinely self-contained against
  its own local SQLite DB (auto-created, not the external `audio_too.db`)
  -- working code, currently empty of content since no `chats/` directory
  ships.
- **`apps/backend/src/kenn/tests/` now exists (22 tests, this package's first ever)**:
  unit tests for every module ported this sprint, plus a live smoke test
  that starts the real server and hits `/api/health` and `/api/ask`. Full
  repo: 89/89 tests passing.
- `m4l/` (Max for Live OSC listener) and `remote_script/KENN_Bridge/`
  (Ableton Remote Script) are small, plausible, self-contained surfaces;
  untested, not exercised by this audit's live checks.
- `vscode_extension/` is a thin JS client that talks to `server.py` --
  now reachable in principle, though the extension itself wasn't tested
  this sprint.

## Desktop companion (`apps/desktop/macos/`)

**Blocked for beta by design.** Builds cleanly standalone (Swift compiles
with no Audio_Too dependency in the build itself), but its first-run flow's
entire purpose is locating an external `Audio_Too` repository on disk. Not
part of the beta scope.

## VST3 plugin (`plugins/kenn-vst3-au/`)

**Built, tested, and integration-verified against the real server this
sprint.** Architecturally independent of Audio_Too (fetches JUCE 8.0.2
from GitHub via CMake; no source dependency found beyond a stray comment).
Configured and built clean with only Xcode Command Line Tools -- both
VST3 and AU targets, zero errors. The existing (previously never-run)
real-time concurrency stress test passed cleanly plain and under
ThreadSanitizer (tool-verified, zero data races in the shared
`AudioTooRealtimeCore`). A new integration test
(`Source/test_server_integration_main.cpp`, `TestServerIntegration`
target) constructs the actual compiled `KENNMixAssistantAudioProcessor`
and calls its real `askKenn()`/`testKennConnection()` methods against a
live `apps/backend/src/kenn/server.py` -- live-verified: health check succeeded,
and a real mix-engineering question returned a genuine, cited answer
through the compiled binary. See ISSUE-13 (resolved) and GAP-12.
Not yet done: loading the built `.vst3`/`.component` bundle inside an
actual DAW (Ableton Live), or Apple's `auval` validator (would require
installing into the user's live plugin folder -- not done without being
asked).

## Evaluation harness (`evaluation/`)

**Split status: partially reproducible, partially demo-only.**

- Scripts that only need stdlib + numpy (`run_audio_holdout_v2c.py`,
  `recommendation_gate.py`, `measured_candidates_v2c.py`,
  `run_v2b_calibration.py`, `build_blind_review_v2d.py`) run standalone
  today and were verified live during this audit to reproduce their
  recorded JSON output deterministically.
- Scripts that import the historical `audio_analysis` package
  (`run_golden_benchmark.py`, `product_adapter_v2d.py`,
  `run_product_qualification_v2d.py`) hard-depend on a sibling `Audio_Too`
  checkout and cannot run in this repo. The "real product decoder parity"
  and V2A baseline numbers in the reports are frozen JSON artifacts only --
  demo-only, not currently reproducible evidence.
- `evaluation/legacy-studio-artifacts/kenn/artifacts/` is an empty
  directory despite its name.
- The historical reports' own self-assessment is notably honest: multiple
  reports explicitly flag their numbers as narrow/synthetic-only and warn
  against generalising them (see `docs/KNOWN_ISSUES.md` ISSUE-14 and the
  gap matrix for direct quotes).

## Knowledge base

**Working, tested but not formally benchmarked.** 232 approved notes
indexed (1104 chunks), each carrying topic/explanation/recommendation/
conditions/source/review-status inline; a source-citation registry; and a
versioned index manifest with per-file SHA-256. See ISSUE-09 (resolved)
and GAP-03/GAP-06 in the gap matrix for exactly what's proven vs. still
open (semantic search, formal quality benchmark, a few missing per-item
metadata fields).

## Not ready for beta (no surface qualifies yet without restrictions)

No surface in this repository currently meets this repo's own beta
definition of done *without qualification*. Mix Review and Chat are both
real, standalone, tested, and (as of this sprint) demonstrated working
end-to-end from a clean checkout -- but neither has been through a formal
human-reviewed qualification pass (real-mix listening review for Mix
Review; retrieval-quality/citation-correctness benchmarking for Chat).
See `docs/KENN_BETA_READINESS_REPORT.md` for the full recommendation.
