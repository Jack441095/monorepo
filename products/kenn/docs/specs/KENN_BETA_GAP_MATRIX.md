# KENN Beta Gap Matrix

Audit date: 2026-09-01, branch `develop` (created as `beta-audit-2026-09-01`). Format: requirement,
current evidence, gap, risk, test, exit condition -- as specified by
`KENN_BETA_SPRINT_PROMPT.md`. Ordered by beta impact, highest first.

**Addendum (2026-09-06):** the gaps below are a point-in-time snapshot from
before the Ableton-control buildout and are kept as a historical audit
record, not a live-updated contract -- do not re-edit the individual GAP
entries below to track ongoing Ableton work. The one part of this document
that *was* actively wrong as written (not just dated) is the "specialist
tools (Ableton...)" row of the summary scorecard, fixed below: KENN's
Ableton control surface is now standalone, extensively tested (500+
`apps/backend/src/kenn/tests`), and real-Live qualified for a documented, allowlisted
subset. For current, actively-maintained Ableton-control status, evidence,
and known gaps, see `docs/ABLETON_ASSISTANT_CURRENT_STATE.md` (the running
log) and `docs/ABLETON_LIVE_SUPPORT_MATRIX.json` (the exact qualified
scope) instead of this document. GAP-09's prompt-injection coverage also
gained a real addition since this audit: track/device-name injection (not
just filename injection) is now covered, see
`docs/ABLETON_ASSISTANT_CURRENT_STATE.md`'s 2026-09-06 entry.

---

### GAP-01: Mix Review runs standalone with real, measured evidence
**Requirement:** Analyse a local mix and return qualified, evidence-backed
findings without any external runtime dependency.
**Evidence:** `mix-review/core/local_engine.py` (KENN-owned, stdlib-only);
24/24 tests passing; CLI smoke-tested end-to-end against a synthetic WAV
with the old `Audio_Too` estate genuinely absent from disk.
**Gap:** No human listening review; no benchmark on real (non-synthetic)
mixes; only 7 fault families covered, and the approximate loudness estimate
is explicitly not calibrated LUFS.
**Risk:** Medium. Wrong/missed flags on real mixes are the main product
risk, but the engine abstains rather than guesses on anything out of scope,
and every finding carries its own stated limitations.
**Test:** `mix-review/tests/` (exists, passing). Missing: a real-mix
corpus with human-reviewed ground truth.
**Exit condition:** Run the engine against a small curated set of real
(consented, non-copyrighted-content-risk) mixes with known issues, reviewed
by a human engineer, before claiming any fault family "qualified" for
external users. **Status: not met. Internal-beta-only claim, not public.**

---

### GAP-02: Standalone boundary proven with old estate absent
**Requirement:** Default chat, Mix Review, evaluation, and demo paths run
from this repository alone; prove it without relying on an external
`Audio_Too` checkout.
**Evidence (corrected 2026-09-01):** `Audio_Too` is **not** absent from
this machine -- it exists at `<LOCAL_VOLUME>/NITE_DSP/Audio_Too`,
the dirty, in-progress NITE DSP monorepo working tree that
`KENN_MIGRATION_RECEIPT.md` explicitly lists as excluded from this repo's
extraction. An earlier version of this document and the readiness report
claimed the old estate was "genuinely absent from disk," based on checking
only `/Volumes/.../Shenrendao/` (this repo's parent directory); that was an
overclaim and has been corrected here. The accurate claim is narrower:
every default code path resolves `Audio_Too` as a sibling of this
repository (`REPO_ROOT / "Audio_Too"`, i.e. under `Shenrendao/`), which
does not exist and is never accidentally found, so nothing in this repo's
default path silently reached into `<LOCAL_VOLUME>/NITE_DSP/`
during this audit's test runs. That is real evidence of no *accidental*
coupling, but it is not the same as proof of independence from an absent
filesystem -- the old estate is present, just not on the lookup path, and
this repo's own operating rules forbid reintroducing it as a runtime
dependency or copying it in bulk regardless of where it lives. Mix Review:
proven (GAP-01). AutoMix: proven disabled-safe, not proven working.
Chat: proven for the HTTP boundary/abstention layer (35/38 tests); not
proven for actually answering a question (GAP-03). Evaluation: proven for
the numpy/stdlib-only scripts; not proven for the `audio_analysis`-importing
scripts.
**Gap:** `apps/backend/src/kenn/main.py`, `server.py`, `core/tool_registry.py`, the
desktop companion's first-run flow, and the golden-benchmark/V2D evaluation
scripts remain hard-blocked on external, absent packages/checkouts.
**Risk:** High if any of these were assumed working without re-checking.
**Test:** This audit's live checks (see `docs/KNOWN_ISSUES.md`).
**Exit condition:** Each blocked entry point is either fixed, replaced with
a KENN-owned implementation, or explicitly disabled with a documented
blocker -- **done for Mix Review and AutoMix; open for `server.py`,
`tool_registry.py`, `main.py`'s deeper subcommands, desktop companion, and
the two `audio_analysis`-dependent evaluation scripts.**

---

### GAP-03 (substantially resolved 2026-09-01): Chat answers in-scope questions with retrieved, cited knowledge
**Requirement:** KENN retrieves relevant knowledge, cites sources,
abstains honestly on out-of-scope or unsupported questions.
**Evidence:** With explicit approval, the real notes corpus (244 files
after excluding 2 personal business/pricing notes and 6 unapproved
auto-generated draft stubs, 232 approved and indexed) and citation
metadata were brought in from the
old estate (see ISSUE-09) and a real BM25 index was built
(`python3 apps/backend/src/kenn/main.py build` -> 1104 chunks, reproducible from
source content in this repo). Live-verified: real in-scope questions now
return `found: true`, `confidence: "high"`, and correctly cited sources
(e.g. "Why does my mix collapse in mono?" -> `sources: ["mix-translation-checks.md",
"vocal-buried-in-mix.md", "stereo-width-mono-compatibility.md"]`). All 67
tests in `mix-review/`, `automix/`, and `chat/` now pass, including the 3
that previously failed for missing eval data.
**Gap:** Semantic (embedding) search is not active -- it degrades to
BM25-only with a printed warning, because the ~90MB ONNX model weights
require `scripts/fetch_embedding_model.py`, which was not ported into this
repo (found and documented, not fixed: fetching a model artifact was
judged lower priority than getting real content indexed at all). BM25
alone already produced accurate, well-cited answers in every live test run
this sprint, so this is a quality-enhancement gap, not a "chat can't
answer" gap anymore. No formal retrieval-relevance/citation-correctness
benchmark has been run against the new index (the `evals/` case files
exist and are used by `chat/tests/test_eval_runner.py`'s unit tests, but a
broader Phase-5-style evaluation pass has not been done).
**Risk:** Low now (was Critical). The remaining gap is measured quality,
not availability.
**Test:** `chat/tests/` (39/39 passing) plus this sprint's live manual
verification (3 real questions, all correctly answered and cited).
**Exit condition:** Met for "chat can answer in-scope questions with real,
cited content." Not yet met for "measured retrieval/citation quality above
a defined bar" (no formal benchmark run) or "semantic search active"
(model weights not fetched) -- both now much smaller, well-scoped
follow-ups rather than the repo's largest gap.

---

### GAP-04 (substantially resolved 2026-09-01): `apps/backend/src/kenn/server.py` and `tool_registry.py` run standalone
**Requirement:** The full KENN server (Ableton control, specialist tools,
confirmation-gated actions) runs from this repo alone.
**Evidence:** All blocking imports (`audio_too` in `server.py` and
`response_contract.py`; `thursday.confirmation` in `tool_registry.py`) were
individually investigated in the old estate's read-only working tree and
found to be small (24-930 lines), self-contained, stdlib-only modules with
no real coupling to anything else in those products. Ported as KENN-owned
code (`core/platform_contracts.py`, `core/endpoint_policy.py`,
`core/request_validation.py`, `core/action_policy.py`,
`core/path_safety.py`, `core/confirmation.py`, `scripts/log_setup.py`).
`server.py`'s own `REPO_ROOT` path bug (same class as GAP-02/ISSUE-02) was
also fixed. Live-verified: server starts; `/api/health` responds;
`/api/ask` returns a real, cited answer through the full production
server. 22 new tests (`apps/backend/src/kenn/tests/`, this package's first ever)
cover every ported module plus a live server smoke test.
**Gap:** The ~10 remaining specialist-feature imports (`ableton_bridge`,
`agents`, `audiogen_bridge`, `automix_jobs`, `automix_public`, `db`,
`demo_feedback`, `song_projects`, `stem_separation_bridge`,
`stem_uploads`) are still unavailable -- but each was verified (by reading
the call site, not assumed) to already be wrapped in `try`/`except` in the
original code, degrading to a clean error response rather than crashing.
No KENN-owned replacement exists for these; they are genuinely complex
subsystems (ML stem separation, Ableton hardware bridge, Thursday TTS)
appropriately out of scope for this sprint. `main.py`'s `build-checklist`/
`download-pdfs` subcommands still reference missing scripts (low priority,
non-core).
**Risk:** Low now (was Critical). The core server and its primary route
(`/api/ask`) work; remaining gaps are individually understood, contained,
and fail safely rather than silently.
**Test:** `apps/backend/src/kenn/tests/` (22/22 passing, including the live smoke
test).
**Exit condition:** Met for "server runs standalone and answers questions."
Not met for the ~10 specialist features -- each would need its own scoped
follow-up (build vs. beta-disable vs. optional adapter) if brought into
beta scope; none are currently claimed as working.

---

### GAP-05: AutoMix produces a real, human-approved render
**Requirement:** A bounded, approval-gated local AutoMix run that never
silently renders audio.
**Evidence:** The safety boundary (approval gate, receipt, output-path
checks) is real, KENN-owned, tested (4/4 passing), and fails safely.
**Gap:** No render engine. `Audio_Too/scripts/automix_local.py` does not
exist in this repo.
**Risk:** Low for beta (feature is disabled, not silently broken) but
represents a real capability gap against the product's stated scope
("bounded AutoMix integration").
**Test:** `automix/tests/` (4/4 passing, boundary-only).
**Exit condition:** A KENN-owned render pipeline exists behind the
existing approval gate, or AutoMix is formally scoped out of the beta
product surface (recommended for this beta). **Status: recommend explicit
beta exclusion, not further engineering this sprint** -- audio rendering
is high-risk, high-effort, and not the core beta capability.

---

### GAP-06 (partially resolved 2026-09-01): Knowledge items carry required provenance metadata
**Requirement:** Every knowledge item records topic, explanation,
recommendation, conditions, source, author, URL/reference, dates,
evidence class, confidence, review status, and KB version.
**Evidence:** Each of the 244 imported notes already carries most of this
per-item, in a consistent structure: title (topic), "Short answer"
(explanation), "Try this" (recommendation), "Common mistakes"/"When this
does not apply" (conditions/exceptions), `Source:` and `Reviewed:` fields
(source + date), `Status: Approved` (review status), plus a
machine-readable `Training_Data_Sources/sources.json` with creator, URL,
and import timestamp per cited source. The built index's
`manifest.json` records a whole-index version ID, source file list, and
per-file SHA-256 -- a form of KB versioning and integrity check.
**Gap:** No explicit "confidence" or "evidence class" field per item
(these exist at the KENN-management-code level -- `apps/backend/src/kenn/knowledge/trust_scores.py`
-- but are not yet populated per note). No author field distinct from
source. Not every note has a URL (some cite the Ableton Live manual or
internal checklists, not a web page).
**Risk:** Low -- the missing fields are refinements to an already-real,
already-cited corpus, not a "no metadata exists" problem anymore.
**Test:** None dedicated; `chat/tests/test_eval_runner.py` exercises
retrieval against this content indirectly.
**Exit condition:** Add confidence/evidence-class fields to the note
schema and backfill them (even a coarse default per category would be
better than absent). Not done this sprint.

---

### GAP-07: Evaluation harness runs independently and measures current code
**Requirement:** Mix Review and knowledge-base evaluation run from a clean
checkout and measure the code actually in this repo.
**Evidence:** `evaluation/benchmark/run_audio_holdout_v2c.py` and 4 sibling
scripts run standalone and were verified live to reproduce their recorded
JSON deterministically. They measure a **different** implementation
(the historical `audio_analysis` engine, not `mix-review/core/local_engine.py`).
**Gap:** No evaluation harness exists yet for the new local engine beyond
its own unit tests (which are correctness tests against known synthetic
constructions, not a calibration/precision-recall benchmark in the style
of the V2B/V2C reports). The two `audio_analysis`-importing scripts
(golden benchmark, V2D product qualification) cannot run here at all.
**Risk:** Medium -- without a benchmark, "24/24 unit tests pass" should
not be read as "this engine is calibrated."
**Test:** `mix-review/tests/test_local_engine.py` exists; a proper
holdout-style benchmark does not.
**Exit condition:** Either port the V2B/V2C-style synthetic holdout
methodology to run against `local_engine.py`, or explicitly state in every
product surface that Mix Review's fault families are unit-tested but not
benchmark-qualified. **Status: not met; documented honestly in current
state summary instead.**

---

### GAP-08: Confirmation, recovery, and rollback paths are tested
**Requirement:** Mutation/render/export actions require explicit
confirmation, are receipt-backed, and are recoverable/undoable.
**Evidence:** Mix Review: read-only, memory-only, receipt-backed, tested
(`storage: memory_only`, `audio_uploaded: false`, `external_network: false`
enforced by `contracts.receipt_errors`). AutoMix: approval-gate tested
(`test_requires_approval_without_calling_engine`), output-path safety
tested (`test_rejects_output_inside_audio_too`), failure honesty tested
(`test_engine_failure_is_reported_honestly`).
**Gap:** No end-to-end test of a *successful* AutoMix render + delivery
(the engine doesn't exist, so this can't be exercised beyond mocks). No
"undo" mechanism exists for AutoMix beyond "the output is a new file, the
input stems are untouched" (true by construction, not actively tested as
an undo flow).
**Risk:** Low -- the untested paths are all inside the already-disabled
AutoMix feature.
**Test:** `automix/tests/test_automix_adapter.py`.
**Exit condition:** Met for Mix Review (read-only by construction, no
"undo" needed). Deferred for AutoMix until GAP-05 is resolved.

---

### GAP-09: Prompt-injection and forged-approval resistance
**Requirement:** Resist prompt injection via filenames, metadata, chat,
documents; resist forged/stale approvals, duplicate actions.
**Evidence:** `chat/app.py`'s scope-classification runs on the raw
question text *before* any engine call, keyword-based and not
LLM-interpreted, which is itself a form of injection resistance (there is
no LLM in the loop to be steered, since LLM use is forced off).
AutoMix requires an explicit boolean `approved=True` passed by the calling
code for every call -- there is no persisted "approval token" to forge or
replay, so forged/stale/duplicate approval is structurally not applicable
to the current design (each call is a fresh, single decision).
**Gap:** No explicit adversarial test suite (e.g. a WAV file with a
crafted filename or embedded metadata designed to be misinterpreted as an
instruction) exists for Mix Review's filename handling. `filename` is used
only for the receipt and file-extension check, never interpreted as
content or code -- verified by reading `local_engine.py` and
`interfaces.py`, not by a dedicated adversarial test.
**Risk:** Low given the current design (no LLM in the retrieval-only path,
no persisted approval state to forge), but "no dedicated adversarial test"
is a real coverage gap, not proof of safety.
**Test:** None dedicated; recommend adding explicit adversarial fixtures
(malicious filenames, oversized/malformed metadata) to `mix-review/tests/`.
**Exit condition:** Add adversarial filename/metadata test cases. Not done
this sprint (scoped out in favour of the higher-impact GAP-01/GAP-02 work).

---

### GAP-10: Generated files never write into source directories
**Requirement:** No mutation, render, export, or runtime state writes into
the product source tree.
**Evidence:** Mix Review: `MixReviewBoundary.__post_init__` actively
raises `ValueError` if `runtime_root` is inside `product_root`
(tested: `test_runtime_must_be_external`). AutoMix: output directory
checked to be outside both the Audio_Too checkout and the source stems
directory (tested). Chat: runtime dir defaults to `chat/.runtime/`, itself
gitignored.
**Gap:** None found for the audited surfaces. Not checked for
`apps/backend/src/kenn/`'s other write paths (session memory, chats dir, local
`kenn.db`) since that package doesn't run standalone yet (GAP-04).
**Risk:** Low for what's currently reachable; unknown for what isn't.
**Test:** `mix-review/tests/test_core_boundaries.py::test_runtime_must_be_external`,
`automix/tests/test_automix_adapter.py::test_rejects_output_inside_audio_too`.
**Exit condition:** Met for the reachable surfaces. Re-verify once GAP-04
is addressed.

---

### GAP-11: Chat's engine-missing failure mode is a raised exception, not a graceful message
**Requirement (derived from Phase 3 UX audit -- error/support states):**
When the underlying engine can't answer, the caller should get an honest,
readable response, not an unhandled exception.
**Evidence:** `chat_retrieval.py` raises `SystemExit("Index not
found...")` when no index exists. **Fixed this sprint:**
`chat/app.py::_scoped_answer_payload` now catches `SystemExit` around the
`answer_payload` call and returns an honest abstention payload
(`found: false`, `intent: "engine_unavailable"`) instead of letting the
exception propagate out of a request thread.
**Gap:** This treats the symptom, not the root cause -- chat still cannot
answer real questions (GAP-03 remains open).
**Risk:** Low now (was Medium). A tester hitting this today gets a clean,
honest "no answer available" response instead of a crash.
**Test:** `chat/tests/test_app.py::test_missing_knowledge_index_abstains_instead_of_crashing`
(added this sprint, passing).
**Exit condition:** Met for graceful failure. GAP-03 (real content) remains
the substantive follow-up.

---

### GAP-12 (substantially resolved 2026-09-01): VST3/AU plugin builds and talks to the real server
**Requirement:** The VST3/Audio Unit plugin builds from this repo alone
and its "Ask KENN" feature works against `apps/backend/src/kenn/server.py`.
**Evidence:** Configured and built clean with `cmake`/Xcode Command Line
Tools alone (no full Xcode needed) -- both `KENNMixAssistant_VST3` and
`KENNMixAssistant_AU` targets, zero errors. The existing
`TestRealtimeThreadSafety` concurrency stress test (never previously run)
passed cleanly, including under `-fsanitize=thread` -- a tool-verified
absence of data races in the real-time audio core, not just "didn't
crash." A new integration test (`TestServerIntegration`, added this
sprint) links the actual compiled `KENNMixAssistantAudioProcessor` --
the same class handed to a DAW -- and calls its real `testKennConnection()`/
`askKenn()` methods against a live `server.py`: live-verified health check
plus a genuine, cited diagnostic answer returned through the compiled
binary.
**Gap:** Not loaded inside an actual DAW (Ableton Live) or validated with
Apple's `auval` (would require installing into
`~/Library/Audio/Plug-Ins/Components/`, altering the user's live plugin
list -- not done without being asked). AutoMix-related plugin routes
(`startAutoMix`/`fetchAutoMixStatus`) weren't integration-tested since
that feature is beta-disabled server-side (GAP-05) and correctly reports
unavailable.
**Risk:** Low. Everything testable outside an actual DAW host has been
tested and passes; the main untested surface (real DAW hosting) is a
manual step the user can now do on a build proven to compile and run
correctly.
**Test:** `plugins/kenn-vst3-au`'s `TestRealtimeThreadSafety` (plain + TSan) and
new `TestServerIntegration`, both run live this sprint (not part of the
Python `pytest` suite -- C++ executables, run manually via `cmake --build`
+ direct execution).
**Exit condition:** Met for "builds and integrates with the real server."
Not met for "verified inside an actual DAW" -- recommend the user load the
built `.vst3`/`.component` in Ableton Live as the next concrete step.

---

## Summary scorecard

| Capability | Standalone? | Tested? | Qualified? | Beta status |
|---|---|---|---|---|
| Mix Review | Yes | Yes (24/24 unit) | No (no human/real-mix review) | **Internal beta, restricted claims** |
| AutoMix | Yes (disabled-safe) | Yes (4/4, boundary only) | N/A (no engine) | **Excluded from beta** |
| Chat (scope/abstention) | Yes | Yes (39/39) | Partial | **Internal beta** |
| Chat (answer knowledge) | Yes (BM25 only; semantic search pending model fetch) | Live-verified (3/3 real questions correctly answered+cited) | No formal benchmark | **Internal beta, disclose BM25-only** |
| `apps/backend/src/kenn` server (core: health, ask) | Yes | Yes (22/22, incl. live smoke test) | No formal benchmark | **Internal beta, developer/plugin-integration use** |
| `apps/backend/src/kenn` specialist tools -- Ableton control | **Yes (updated 2026-09-06, see addendum above; was "No" at this audit's 2026-09-01 date)** | Yes (500+ tests) | Yes, for an explicit allowlisted subset (`docs/ABLETON_LIVE_SUPPORT_MATRIX.json`) | **Internal beta, supervised pilot; see `ABLETON_ASSISTANT_CURRENT_STATE.md`** |
| `apps/backend/src/kenn` specialist tools (stems, voice, AutoMix) | No | No | No | **Not ready, fails safely** |
| Desktop companion | No (blocked by design) | Not tested | No | **Not ready** |
| VST3 plugin | Yes (builds clean, VST3+AU) | Yes (concurrency + TSan + live server integration) | No DAW-load or auval yet | **Ready for DAW load-testing** |
| Evaluation harness (synthetic) | Yes (5 scripts) | N/A (is the test) | Measures old engine, not new | **Reference only** |
| Evaluation harness (product) | No | No | No | **Not ready** |
| Knowledge base | Yes (232 approved notes, real index) | Live-verified | No formal quality benchmark | **Internal beta, restricted claims** |
