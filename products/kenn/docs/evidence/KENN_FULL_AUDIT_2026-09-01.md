# KENN Full Audit — 2026-09-01

Branch: `develop` (pushed to `https://github.com/Jack441095/kenn-standalone`).
Working tree clean, 89/89 automated tests passing, re-verified live
immediately before writing this. This is a fresh synthesis of everything
done and found across this session, not a copy of the earlier in-progress
reports — those live in `docs/` and go deeper on any one topic; this file
is the one-stop "where are we, what's next" answer.

## 1. Executive summary

KENN's standalone extraction started this session in worse shape than
documented: Mix Review couldn't even import, the knowledge base shipped
empty, and the full server (`source/kenn/server.py`) was blocked by
multiple missing external packages nobody had previously catalogued. By
the end of this session, four of the product's core surfaces are real,
tested, and live-verified working from a clean checkout of this repo
alone — no external monorepo, no placeholder claims:

1. **Mix Review** — a KENN-owned, dependency-free analysis engine.
2. **Chat / knowledge base** — real content (232 approved notes), a real
   BM25 index, real cited answers.
3. **The full local server** (`source/kenn/server.py`) — the "Ask KENN"
   backend the plugin and dashboard both depend on.
4. **The VST3/AU plugin** — builds clean, thread-safety tool-verified,
   and proven to talk to the real server end-to-end.

On top of that: a colleague's UX redesign was integrated and wired to the
current server, and the plugin/desktop app were rebranded to Shenrendao AI.

**What's still not done**: AutoMix has no render engine (safely disabled,
not broken); ~10 specialist server routes (Ableton hardware control, stem
separation, voice synthesis) have no KENN-owned implementation, though
each fails cleanly rather than crashing; nothing has been qualified by a
human listening review or a formal benchmark yet — everything that works,
works and is *tested*, but "tested" and "qualified" are not the same
claim, and this document does not conflate them.

**Bottom line recommendation: beta with restrictions**, same as the
standing recommendation in `docs/KENN_BETA_READINESS_REPORT.md` — the
restrictions have gotten narrower as more surfaces proved out, not wider.

## 2. What changed this session, in order

| # | Change | Evidence |
|---|---|---|
| 1 | Mix Review: was completely blocked (`RuntimeError` on import), now a real, dependency-free engine, 7 fault families, 24 tests | `mix-review/core/local_engine.py` |
| 2 | Knowledge base: shipped empty, now 232 real approved notes + real BM25 index | `source/kenn/Training_Data_Notes/`, live-verified answers |
| 3 | `chat/app.py`: default engine path fixed, missing-index failure made graceful | 39/39 tests |
| 4 | `source/kenn/server.py`: was blocked by `audio_too`/`thursday` imports + a path bug, now starts and answers real questions through `/api/ask` | 22 new tests incl. live server smoke test |
| 5 | VST3/AU plugin: never build-verified, now builds clean, thread-safety tool-verified (ThreadSanitizer), and proven to reach the live server and get a real cited answer through the compiled binary | `TestRealtimeThreadSafety`, `TestServerIntegration` |
| 6 | UX: a colleague's chat/dashboard redesign integrated into `UX/`, dead links to a non-existent multi-product dashboard removed, wired to and live-verified against the real server (including the exact streamed request format the UI sends) | `UX/`, `docs/KNOWN_ISSUES.md` ISSUE-16 |
| 7 | Branding: plugin (VST3 + AU) and desktop companion renamed "Shenrendao AI" | `vst3-plugin/CMakeLists.txt`, installed bundle metadata verified |
| 8 | Repo hygiene: repo-root path bugs fixed in 5 places, two broken `requirements.txt` paths fixed, GitHub remote set up and pushed | `docs/KNOWN_ISSUES.md` |

Full commit-by-commit detail: `git log --oneline main..develop`.

## 3. Current state by subsystem

### Mix Review (`mix-review/`) — **working, tested, not yet qualified**
Standalone, KENN-owned, zero external dependency. Measures clipping,
headroom, silence/truncation, channel imbalance, phase/polarity & mono
compatibility, DC offset, and an approximate (non-LUFS) loudness estimate
— each with real evidence, confidence, and severity. Explicitly abstains
(doesn't guess) on masking, tonal balance, arrangement, genre context,
calibrated loudness, and true peak. 24/24 unit tests against synthetic
fixtures constructed to exercise every fault family.
**Gap**: no human listening review, no real-mix benchmark corpus. Unit
tests prove the code does what it claims on synthetic input; they don't
prove the claims are musically correct on real mixes.

### Chat + knowledge base (`chat/`, `source/kenn/`) — **working, tested, not yet qualified**
232 approved notes (mostly Ableton device workflows, mixing/mastering
fundamentals, Wwise game-audio integration), indexed via BM25 into 1104
chunks. Live-verified: real questions get real, cited, substantive
answers — both through `chat/app.py`'s scoped public wrapper and through
the full `server.py`. Semantic (embedding) search isn't active yet —
BM25-only, because the ONNX model weights aren't fetched
(`scripts/fetch_embedding_model.py` doesn't exist in this repo). LLM use
is force-disabled by code, not just config, everywhere.
**Gap**: no formal retrieval-relevance/citation-correctness benchmark —
only live spot-checks and unit tests using the `evals/` fixtures that were
migrated alongside the notes.

### Full local server (`source/kenn/server.py`) — **core working, specialist routes not**
Previously totally blocked. Now starts standalone and its core route
(`/api/ask`) works end-to-end — verified through three independent paths
this session: `chat/app.py`, direct HTTP, and the compiled VST3/AU plugin
binary. ~10 specialist routes (Ableton hardware bridge, stem separation,
stem upload, voice synthesis, AutoMix upload) have no KENN-owned
implementation behind them, but every one of those call sites was checked
individually and already fails into a clean error response rather than
crashing the request or the server.
**Gap**: those ~10 routes are real product capabilities with no
implementation yet. `main.py`'s `build-checklist`/`download-pdfs`
subcommands are also still blocked (low priority, non-core).

### VST3/AU plugin (`vst3-plugin/`) — **builds, tested, integration-proven; not DAW-loaded by this session**
Builds clean with just Xcode Command Line Tools (both formats). Its
real-time audio-analysis core passed a concurrency stress test under
ThreadSanitizer — a tool-verified absence of data races, not a "didn't
crash" claim. A new integration test constructs the actual compiled
processor class (the same one a DAW loads) and proved it reaches the real
server and gets a real answer. Rebranded to Shenrendao AI and installed
into this machine's live plugin folders (you're loading it in Ableton now).
**Gap**: I haven't loaded it inside Ableton myself or run Apple's `auval`
validator (the latter would touch your live plugin folder in a way I
didn't want to do without being asked). You're the one actually
DAW-testing it right now — that's the remaining verification step.

### UX (`UX/`) — **integrated, wired, live-verified**
A colleague's redesign of the chat/dashboard front-end. Every API call it
makes was checked against `server.py`'s real route table (not assumed) —
full match. Dead nav links to a larger multi-product dashboard that isn't
part of this repo were removed (Mix Review/AutoMix/AudioGen are already
inline widgets on the same page, so nothing was lost). Live-verified with
the UI's exact request shape (including `stream: true`) getting back a
real SSE-streamed, cited answer.
**Gap**: not tested in an actual browser by a human — only via `curl`
matching what the browser would send. Worth a real click-through.

### AutoMix (`automix/`) — **safely disabled, no render engine**
The approval-gate safety boundary is real and tested (4/4). No actual
render engine exists — `Audio_Too/scripts/automix_local.py` isn't in this
repo. This is a genuine capability gap, not a bug: the boundary correctly
refuses to pretend it works.

### Desktop companion (`source/desktop_companion/`) — **builds, blocked by design**
Compiles cleanly, rebranded. Its first-run flow's entire purpose is
locating an external Audio_Too repository, which doesn't fit this
standalone repo's model — blocked for beta, not a bug.

### Evaluation harness (`evaluation/`) — **split: some reproducible, some not**
5 of the historical benchmark scripts run standalone today and reproduce
their recorded output deterministically (verified live). 2 scripts hard-
import the historical `audio_analysis` package from the old estate and
cannot run here — their "real product decoder" numbers are frozen JSON
claims, not currently reproducible evidence.

## 4. Test coverage

```
python3 -m pytest mix-review/tests automix/tests chat/tests source/kenn/tests -q
# 89 passed, 0 failed
```
Plus, not part of the Python suite (C++, run manually):
- `TestRealtimeThreadSafety` (plain + ThreadSanitizer) — passing
- `TestServerIntegration` — passing, live-verified against a real server

At the start of this session: **0 runnable tests** in `mix-review/`,
`chat/`, or `source/kenn/` (all three failed to even collect), and no
C++ tests had ever been executed.

## 5. Standalone boundary — where it actually stands

Confirmed genuinely dependency-free at runtime: Mix Review, Chat's core
answer path, `server.py`'s core route, the VST3/AU plugin's real-time
core and network client. Confirmed still coupled to the old estate and
explicitly out of scope: `main.py`'s deeper subcommands, ~10 specialist
`server.py` routes, AutoMix's render engine, the desktop companion's
first-run flow. Nothing in this repo silently reaches into the old
`Audio_Too`/`NITE_DSP` estate on this machine by default — every case
where that estate's *content* was used this session (the knowledge notes,
the UX redesign) was an explicit, scoped, approved import of specific
non-backend files, not a runtime dependency, and the source material was
deleted after integration in both cases.

## 6. How to improve KENN from here (ranked)

1. **Load the plugin in Ableton and use it for real** — you're doing this
   right now. This is the one meaningful verification step nothing short
   of an actual DAW session can provide.
2. **Real-mix, human-reviewed benchmark for Mix Review** — the single
   biggest gap between "tested" and "qualified" for the core product
   capability. Needs real mixes with known issues and a human reviewer,
   not more synthetic fixtures.
3. **Formal chat retrieval/citation benchmark** using the `evals/` case
   files that already exist — turns "live-verified to work" into
   "measured to work well."
4. **Scoped, individual follow-up per specialist `server.py` route**
   (Ableton hardware bridge, stem separation, voice synthesis, AutoMix
   upload) — each needs its own remove/replace/adapter/disable decision;
   trying to do all ~10 at once is how the original migration
   under-scoped itself.
5. **Fetch the ONNX embedding model** to enable semantic search on top of
   the already-working BM25 index — a real quality upgrade for chat, not
   a blocker.
6. **Grow the knowledge base past 232 notes** — genre-specific,
   troubleshooting, and deeper mastering content are the most obviously
   thin areas relative to the mission's original knowledge-base scope.
7. **A real browser click-through of `UX/`** — the integration is
   proven at the HTTP level; nobody has clicked every button yet.
8. **Adversarial input testing** for Mix Review and the server (malformed
   metadata, crafted filenames, oversized files) — the current safety
   argument ("no LLM in the loop") is sound by design but untested by
   deliberate attack.
9. **A KENN-owned AutoMix render path**, or a formal decision to retire
   AutoMix from the product surface entirely rather than leave it
   permanently "disabled."

## 7. Where to go deeper

- `docs/KENN_BETA_READINESS_REPORT.md` — the full 10-section report
  (architecture, findings, risks, evidence) this file summarizes.
- `docs/KENN_BETA_GAP_MATRIX.md` — every requirement, evidence,
  gap, risk, and exit condition, individually.
- `docs/KNOWN_ISSUES.md` — every specific bug found and fixed (or
  explicitly left open, with why) this session, including this session's
  discoveries beyond the original mission scope (a `thursday` package
  dependency nobody had documented, a second hidden `audio_too` import,
  the UX integration, the rebrand).
- `docs/KENN_CURRENT_STATE_SUMMARY.md` — per-surface working/partial/
  blocked classification.
- `docs/KENN_BETA_TESTER_GUIDE.md`, `KENN_BETA_SUPPORT_RUNBOOK.md`,
  `KENN_BETA_ROLLBACK_PLAN.md` — for anyone testing or supporting the beta.
- `docs/KENN_CPP_ARCHITECTURE_NOTES.md` — the standing decision on the
  hybrid C++/Python architecture direction.

## 8. Honesty check

Everything marked "working" or "tested" above was re-verified live
immediately before writing this document, not recalled from memory or
copied from an earlier claim: the full test suite was re-run, the server
was started and its health/chat/UX endpoints were hit fresh, and the
mix-review CLI was run against a freshly-generated synthetic file.
Nothing here is qualified as "beta-ready" or "production-ready" — those
are separate, higher bars this repository's own operating rules require
real evidence for, and that evidence (human review, formal benchmarks)
doesn't exist yet. What does exist is real: standalone, tested, and
proven to work from a clean checkout of this repository alone.
