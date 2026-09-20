# KENN Known Issues

Audit date: 2026-09-01. Source SHA at audit start: `fd2b483` (branch
`develop`, created as `beta-audit-2026-09-01` from `main`). This document lists concrete,
verified issues found during the standalone-boundary and product audit.
"Fixed" means fixed and tested in this branch; "Open" means documented but
not fixed in this sprint, with a reason.

## Fixed in this sprint

### ISSUE-01 -- Mix Review crashed at import without an external checkout
**Severity:** Critical. **Status:** Fixed.
`mix-review/adapter.py` raised `RuntimeError` at module import time unless
an external `Audio_Too` checkout existed at a sibling path. This made Mix
Review, and every test that imported it, completely unusable standalone.
Fixed by adding a KENN-owned, stdlib-only analysis engine
(`mix-review/core/local_engine.py`) as the default, with the legacy engine
preserved as an explicit non-default opt-in. See
`docs/KENN_BETA_GAP_MATRIX.md` for qualification status.
Evidence: `mix-review/tests/` -- 24/24 passing, 0 before this fix (test
collection itself failed).

### ISSUE-02 -- `apps/backend/src/kenn/main.py` REPO_ROOT pointed above the repo
**Severity:** High. **Status:** Fixed (partially unblocks; see ISSUE-08).
`REPO_ROOT = ROOT.parent.parent.parent` (3 levels up from
`apps/backend/src/kenn/main.py`) resolved to the directory *containing* this repo,
not the repo itself -- a leftover from the old monorepo's deeper nesting.
Fixed to 2 levels up. The same bug existed in `autonomous_agent.py`
(`parents[3]` instead of `parents[2]`); fixed there too.

### ISSUE-03 -- `chat/requirements.txt` and `apps/backend/src/kenn/requirements.txt` pointed outside the repo
**Severity:** High. **Status:** Fixed.
`chat/requirements.txt` referenced
`../../../Audio_Too/studio/kenn/kenn/requirements.txt` (a sibling repo path
that does not exist). `apps/backend/src/kenn/requirements.txt` referenced
`../../../requirements.txt`, which resolves one directory above this repo's
root. `pip install -r <either file>` failed immediately on a clean
checkout. Fixed both to point at real, local files, and added a
root-level `requirements.txt`.

### ISSUE-04 -- `main.py` imported a nonexistent `repo_python` module
**Severity:** High. **Status:** Fixed.
`main.py` imported `repo_python.python_executable` from what was meant to
be a shared umbrella-repo utility. It does not exist anywhere in this repo
or on disk. Added a minimal KENN-owned replacement
(`scripts/repo_python.py`) that returns `sys.executable` -- the correct
standalone behaviour, since there is no shared umbrella virtualenv to
resolve.

### ISSUE-05 -- `automix/adapter.py` had the same REPO_ROOT bug as ISSUE-02
**Severity:** Medium. **Status:** Fixed.
Same off-by-one-directory-level bug as ISSUE-02, in the AutoMix adapter's
default path resolution. Automix is beta-disabled regardless (ISSUE-07),
but the bug is fixed for correctness and in case a future contributor
re-enables the optional legacy engine path.

### ISSUE-06 -- `chat/app.py` defaulted to an external engine checkout
**Severity:** High. **Status:** Fixed (partially unblocks; see ISSUE-09).
`chat/app.py`'s `ENGINE_ROOT` defaulted to
`REPO_ROOT / "Audio_Too" / "studio" / "kenn"`, an external sibling
checkout. This repo's own `source/` tree is the structural equivalent (the
old `Audio_Too/studio/kenn/` outer directory and this repo's `source/`
directory both wrap an inner `kenn/` package). Repointing the default
took `chat/`'s test suite from 0 passing (blocked at import) to 35/38
passing.

### ISSUE-10 -- `.gitignore` header described a monorepo layout this repo doesn't have
**Severity:** Low (documentation/hygiene). **Status:** Fixed.
The top comment described "the NITE DSP umbrella repo" linking product
repos in as submodules. Corrected to describe this standalone repo. The
ignore rules below it were left as-is (several reference directories that
don't exist in this repo, e.g. `archive/legacy-layout/`; they are harmless
no-ops, not actively misleading, so left alone to avoid unrelated churn).

### ISSUE-09 (RESOLVED 2026-09-01) -- Knowledge base ships with zero content
**Severity:** Was Critical. **Status:** Resolved.
The knowledge/notes content (244 markdown files after excluding 2
personal business/pricing notes at the owner's request and 6 unapproved
auto-generated draft stubs (session-report/feedback-repair templates, one
of which named what may be a real client/track), 5 source-citation JSON
files, 1 generated PDF checklist, 8 evaluation case files) was deliberately
excluded from the original extraction. With explicit owner approval, the
non-private, non-copyrighted portion of this content was copied from the
old estate's working tree (`NITE_DSP/Audio_Too/studio/kenn/kenn/`) into
`apps/backend/src/kenn/Training_Data_Notes/`, `Training_Data_Sources/`,
`Training_Data_PDF/`, and `evals/`. Explicitly **not** copied: raw
third-party video transcripts (`Training_Data_Transcripts/`, copyright
risk -- the Notes are KENN's own paraphrased, cited derivatives of these,
which is what's safe to keep), user session history (`chats/`, 92MB,
private data), the shared business database (`Audio_Too/data/audio_too.db`,
likely contains cross-product/customer data), fine-tuning data
(`finetune/`), the prebuilt binary artifacts/index (`artifacts/`,
1.1GB -- regenerated locally instead, see below), and (after a second
review pass, at the owner's request) 2 notes containing the owner's
personal business pricing/rate information
(`jack-pricing-revisions.md`, `client-mix-pricing-and-quotes.md`) --
those are the owner's own business specifics, not generic audio-
engineering knowledge, and weren't meant to be in a repo shared with
collaborators.
Running `python3 apps/backend/src/kenn/main.py build` now builds a real BM25 keyword
index (1104 chunks from 232 approved notes + 1 PDF; 12 notes were
correctly excluded for not being `Status: Approved`) and chat now answers
real, in-scope mix-engineering questions with cited sources -- verified
live (see ISSUE-15). Semantic (embedding-based) search still degrades
gracefully to BM25-only, since the ~90MB ONNX model weights are not
fetched (`scripts/fetch_embedding_model.py`, referenced in
`onnx_embedder.py`, does not exist in this repo) -- this is a real,
disclosed limitation, not a blocker: BM25 alone already produces accurate,
cited answers in every case tested.

### ISSUE-15 (found and fixed 2026-09-01) -- second, unguarded `audio_too` import crashed index builds
**Severity:** High. **Status:** Fixed.
`apps/backend/src/kenn/retrieval/onnx_embedder.py` had an unguarded, module-level
`from audio_too.model_runtime import ONNX_SESSION_INIT_LOCK`. One caller
of this module (embedding generation during indexing) already caught the
resulting `ModuleNotFoundError` and degraded gracefully; a second caller
(`build_index.py::build_manifest_metadata`, which records the embedding
model's identity in every index manifest for provenance) did not, and
crashed the entire index build with exit code 1 after processing all 252
notes. `ONNX_SESSION_INIT_LOCK` is just a `threading.Lock()` used to
serialize ONNX session creation -- replaced with a local, KENN-owned
`threading.Lock()` instead of importing it from a package that doesn't
exist in this repo. No behaviour change when the model is actually
available; this was purely a spurious external dependency for something
that never needed to be external.

## Open (documented, not fixed this sprint)

### ISSUE-07 -- AutoMix has no functioning render engine
**Severity:** High. **Status:** Open; explicitly beta-disabled.
`automix/adapter.py` calls `Audio_Too/scripts/automix_local.py`, which does
not exist in this repository. The adapter's safety boundary (approval gate,
receipt contract, output-path checks) is real, KENN-owned, and tested
(4/4 passing) -- calling it with `approved=True` returns a clear
`status: "failed"` receipt rather than crashing. No KENN-owned render
pipeline exists. **Replacement plan:** build a minimal KENN-owned render
path (even a conservative gain/limiter-only automated pass) behind the
existing approval-gate contract, or formally retire AutoMix from the
product surface until one exists. Not attempted this sprint: audio
rendering/mutation is high-risk, high-effort, and out of scope for a
read-only-analysis-first beta.

### ISSUE-08 (substantially resolved 2026-09-01) -- `server.py` and `tool_registry.py` were blocked by multiple missing external packages
**Severity:** Was Critical. **Status:** Substantially resolved.
Beyond the path bug (ISSUE-02, and the same class of bug in `server.py`
itself -- `REPO_ROOT = PROJECT_ROOT.parent.parent` resolved one directory
above this repo; fixed to `PROJECT_ROOT.parent`), these entry points
imported external top-level packages that exist nowhere in this repo:
`audio_too` (in `server.py` and `response_contract.py`) and
`thursday.confirmation` (in `tool_registry.py`).

Each was investigated individually in the old estate's working tree
(read-only reference, per this repo's operating rules) rather than assumed
unrecoverable. All were small (24-930 lines), self-contained, stdlib-only
utility/contract modules with no real coupling to anything else in
Audio_Too or Thursday -- exactly the "smallest KENN-owned implementation"
case the mission calls for. Ported as KENN-owned code: `core/platform_contracts.py`,
`core/endpoint_policy.py`, `core/request_validation.py`,
`core/action_policy.py`, `core/path_safety.py`, `core/confirmation.py`
(replaces `thursday.confirmation`; same HMAC-signed algorithm, no
Thursday-specific coupling), and `scripts/log_setup.py`.

`server.py` now imports and starts standalone. Live-verified: `/api/health`
responds; `/api/ask` returns a real, cited diagnostic answer through the
full production server (not just `chat/app.py`'s narrower public wrapper).
The remaining specialist imports found by static analysis --
`ableton_bridge`, `agents`, `audiogen_bridge`, `automix_jobs`,
`automix_public`, `db`, `demo_feedback`, `song_projects`,
`stem_separation_bridge`, `stem_uploads` -- were checked individually by
reading each call site (not assumed): every one is already wrapped in
`try`/`except` at either module load or the enclosing route handler in the
*original* code, degrading to a clean error response (e.g. `503 Mix Review
Lab is unavailable`) rather than crashing the request or the server. These
remain unimplemented (stem separation needs an isolated Demucs ML venv,
`ableton_bridge`/hardware control needs a running Ableton instance,
`thursday.voice_output` needs the Thursday TTS pipeline) -- genuinely
complex subsystems appropriately out of scope for this sprint, and already
safe to leave unresolved because they fail cleanly.

`apps/backend/src/kenn/main.py`'s deeper subcommands (`build-checklist`,
`download-pdfs`) still reference scripts (`scripts/build_audio_too_checklist.py`,
`scripts/setup/download_training_pdfs.py`) that don't exist in this repo;
the default `build`/`ask`/`chat` commands work (see ISSUE-09/GAP-03). Not
fixed this sprint -- low priority, non-core commands.

Added `apps/backend/src/kenn/tests/` -- this package's first-ever test coverage: 22
tests covering every ported module plus a live smoke test that starts the
real server and hits `/api/health` and `/api/ask` end-to-end. Full repo:
89/89 tests passing.

**Test material pointer (not copied into this repo):** real AutoMix test
material already exists locally at
`<LOCAL_VOLUME>/testing-for-NITE-DSP/` -- `testing_track_stems/`
(13GB of real song stems plus a prior `_automix_out/` run with
`VALIDATION_SUMMARY.json`/`.md` and a `MATCH_GENERALIZATION.json`, evidence
an AutoMix validation pass was run before) and `sample_pack_testing/`
(43GB of licensed third-party commercial sample packs). Neither should be
copied into this repo (size, and the sample packs are licensed content not
owned for redistribution) -- reference by path when AutoMix work resumes,
via an environment variable pointing at that directory, the same pattern
`KENN_AUDIO_TOO_ROOT` already uses.

### ISSUE-09 -- Knowledge base ships with zero content
**Severity:** Critical. **Status:** Open.
`apps/backend/src/kenn/knowledge/` contains only management code (contradiction
detection, trust scoring, maintenance scheduling, reasoning traces) -- no
knowledge items, no notes corpus, no built retrieval index. Calling
`kenn.core.chat.answer_payload(...)` raises `SystemExit("Index not
found...")` because `chat_retrieval.py` cannot find an index to search.
The retrieval/ranking code itself (`apps/backend/src/kenn/retrieval/retrieval.py`,
~940 lines) is real, substantial, and does not depend on any external
package. It has nothing to retrieve. **Replacement plan:** see
`docs/KENN_BETA_GAP_MATRIX.md` Phase 5 section -- a scoped, provenance-
tagged starter knowledge base needs to be authored and indexed before chat
can answer anything beyond an abstention.

### ISSUE-11 (RESOLVED 2026-09-01) -- Three `chat/` tests were failing due to missing eval fixture data
**Severity:** Was Low (test coverage, not a code defect). **Status:** Resolved.
Fixed as a side effect of ISSUE-09's resolution: `chat/tests/test_app.py::test_specialist_keyword_stays_retrieval_only`
and two tests in `test_eval_runner.py` needed `apps/backend/src/kenn/evals/*.json`
case files that are now present. All three pass with the real, migrated
eval data (no fabricated content). Full suite: 67/67 passing.

### ISSUE-12 -- Desktop companion requires locating an external Audio_Too repository by design
**Severity:** High. **Status:** Open; blocked for beta.
`apps/desktop/macos/KENNDesktopCompanion.swift` builds cleanly
standalone (verified: `build_macos_app.sh` succeeds with no Audio_Too
dependency in the *build*), but its first-run flow's entire purpose is to
locate and launch against an `Audio_Too` checkout
(`"Choose the Audio_Too repository to start KENN"`). Not in scope for this
sprint to redesign; document as blocked for beta and exclude from the
tester guide.

### ISSUE-13 (resolved 2026-09-01) -- `plugins/kenn-vst3-au/` was not build-verified
**Severity:** Was Medium. **Status:** Resolved -- built, tested, and
integration-verified against the live server this sprint.
`plugins/kenn-vst3-au/CMakeLists.txt` fetches JUCE 8.0.2 from GitHub via CMake
`FetchContent`; only a stray comment mentions "Audio Too plug-ins," no
actual source dependency. Configured and built cleanly with only Xcode
Command Line Tools (no full Xcode needed, despite the README's caveat that
AU requires it -- both `KENNMixAssistant_VST3` and `KENNMixAssistant_AU`
targets built successfully). Zero build errors; only pre-existing upstream
JUCE/harfbuzz compiler warnings, not KENN code.

Verified three ways, not just "it compiled":
1. **Existing concurrency stress test** (`TestRealtimeThreadSafety`,
   already in the CMakeLists, previously never run): 1 audio-thread writer
   + 3 concurrent reader threads hammering `AudioTooRealtimeCore::analyse()`/
   `snapshot()` across 5 sample rates -- zero torn/NaN reads. Re-run under
   `-fsanitize=thread` (`-DKENN_ENABLE_TSAN=ON`): clean pass, no TSan
   report -- a tool-verified absence of data races, not just "didn't crash."
2. **New integration test** (`TestServerIntegration`, added this sprint,
   `Source/test_server_integration_main.cpp`): links against the
   already-compiled `KENNMixAssistant` shared-code library (recompiling
   `PluginProcessor.cpp` directly in a plain `add_executable` would miss
   the `JucePlugin_*` macros `juce_add_plugin()` injects only for its own
   target) and constructs the *real* `KENNMixAssistantAudioProcessor` --
   the same class `createPluginFilter()` hands to a DAW -- then calls its
   actual `testKennConnection()`/`askKenn()` methods against a live
   `apps/backend/src/kenn/server.py`. Live-verified: health check succeeded, and a
   real mix-engineering question returned a genuine, cited 1557-character
   diagnostic answer through the compiled plugin binary.
3. Code review of `askKenn`/`testKennConnection`/`sendHandoffToKenn`
   confirms they target exactly the real routes and response shapes
   `server.py` serves (`/api/ask`, `/api/health`, `/api/plugin-handoff`) --
   not a guess, matched field-for-field against the live server responses
   captured during this sprint's `server.py` work (see ISSUE-08).

**Not verified this sprint:** loading the built `.vst3`/`.component`
bundles inside an actual DAW (Ableton Live), or Apple's `auval` AU
validator -- the latter requires installing the bundle into
`~/Library/Audio/Plug-Ins/Components/`, which would alter the user's live
plugin list; not done without being asked. AutoMix-related routes
(`startAutoMix`/`fetchAutoMixStatus`) were not integration-tested since
that feature is explicitly beta-disabled (ISSUE-07) and will correctly
report unavailable.

### ISSUE-14 -- Historical evaluation reports mix reproducible and unreproducible claims
**Severity:** Medium. **Status:** Open; documented, not a code defect.
`evaluation/reports/` contains ~30 reports (V2A-V2D). The clipping/headroom/
L-R-imbalance detector numbers on the synthetic 88-case holdout are
reproducible today by running `evaluation/benchmark/run_audio_holdout_v2c.py`
directly (verified live during this audit). The "real product decoder"
parity numbers in V2D and the V2A baseline are not reproducible in this
repo -- `evaluation/benchmark/run_golden_benchmark.py` and
`product_adapter_v2d.py` both hard-import `audio_analysis.*` from a sibling
`Audio_Too` checkout that doesn't exist here. See
`docs/KENN_BETA_GAP_MATRIX.md` for the full breakdown and
`docs/KENN_CURRENT_STATE_SUMMARY.md` for what this means for current
product claims.

### ISSUE-16 (2026-09-01) -- Integrated a colleague's UX redesign, front-end only
**Severity:** N/A (feature integration, not a defect). **Status:** Done.
A colleague sent a full copy of the old "velvet_thunder" monorepo checkout
(`.venv/`, `business/`, `studio/`, tests, migrations -- 702MB) specifically
to hand off a UX redesign of KENN's chat/dashboard front-end. Per explicit
instruction, only the front-end was integrated (`studio/kenn/kenn/static/{app.js,
index.html,styles.css}`, compared against and found to be a redesigned,
non-identical version of this repo's now-superseded `apps/backend/src/kenn/static/`),
into a new top-level `UX/` folder -- everything else (backend Python,
`.venv`, business logic, DB migrations, `.env`) was explicitly excluded per
the "ignore all backend" instruction, and the entire source folder was
removed after integration.

Every API endpoint the new front-end calls (grepped from `kennFetch`/`fetch`
call sites: `/api/ask`, `/api/mix-review`, `/api/mix-review-step`,
`/api/automix-upload`, `/api/stem-separate-upload`, `/api/audiogen/*`,
`/api/session*`, `/api/ableton/osc/*`, `/api/speak`, `/api/ask-attachment`,
`/api/mixing-doctor/alerts`, and more) matches an already-implemented
`server.py` route -- confirmed by code comparison, not assumed. The
front-end's own `API_ORIGIN` detection already handles being served
directly from `server.py` (port 8090, no CSRF) vs. proxied through a
larger business dashboard at `/kenn` (CSRF required) -- no changes needed
there. `server.py`'s `STATIC_ROOT` was repointed from `apps/backend/src/kenn/static/`
(now removed, fully superseded) to `<repo>/UX/`.

Adapted before integrating: the nav originally linked to `/hub`,
`/audio-analysis`, `/automix`, `/creative-lab` -- pages in the larger
multi-product "Thursday" business dashboard that isn't part of this
standalone repo and would 404. Removed those links and the "Thursday"
branding/title (`KENN · Thursday` -> `KENN`); Mix Review, AutoMix, and
AudioGen are already reachable as inline widgets on the same page, so
nothing was lost.

Live-verified end-to-end, not just served: `/`, `/app.js`, `/styles.css`
(both bare and `/kenn/`-prefixed) all serve correctly; a POST to `/api/ask`
using the exact JSON body shape the new front-end sends (`stream: true`
included) returned a real SSE-streamed answer with correct citations
through `server.py`'s existing `answer_payload_stream` handling.

- No secrets, API keys, `.env` files, or credential files are committed to
  this repository (`.env.example` only, correctly listing variable names
  with no values).
- No absolute local filesystem paths (`/Users/...`, `/Volumes/...`) are
  hardcoded in source, docs, config, or build files.
- No `Nite_DSP_01` / `Thursday` product-name references were found outside
  the three evaluation report titles noted in ISSUE-14 (report titles only,
  not runtime code).
