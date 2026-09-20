# KENN Current State Audit

Audit date: 2026-09-01. Branch `develop`, pushed to
`https://github.com/Jack441095/kenn-standalone`. Working tree clean at
audit start; 89/89 Python tests + 2/2 C++ tests passing, all re-verified
live (not recalled from memory) immediately before this audit began. This
document is the "where does everything actually stand" reference this
mission's other reports build on; see `KENN_FULL_AUDIT_2026-09-01.md` at
the repo root for the narrative version and `docs/KNOWN_ISSUES.md` for
every individual bug found and fixed.

## Repository facts

- Single branch in active use: `develop` (created as
  `beta-audit-2026-09-01`, renamed once its fixes were verified). `main`
  is the original clean extraction point, untouched.
- Remote: `origin` -> `https://github.com/Jack441095/kenn-standalone.git`
  (renamed from an operator typo, `keno-standalone`, at the owner's
  request). Both `main` and `develop` are pushed.
- Single worktree, no stray worktrees.
- No secrets, credential files, or hardcoded absolute local paths in
  tracked source (checked this session and in the prior sprint; the one
  absolute-path reference, in `KENN_MIGRATION_RECEIPT.md`, is a historical
  record of the extraction event, not a runtime dependency).
- No symlinks in the tracked tree.
- One Dockerfile (`chat/Dockerfile`) -- builds `chat/`'s retrieval-only
  HTTP wrapper as a standalone container image; not re-verified this
  session (no container build was attempted), flagged as untested in the
  gap matrix.
- Generated state correctly excluded from git: `chat/.runtime/`,
  `apps/backend/src/kenn/data/` (the built retrieval index), `__pycache__/`
  throughout, `build/` (native build output) -- all covered by
  `.gitignore`, confirmed via `git check-ignore` this session.

## Surface-by-surface classification

Categories per the mission: working / partially working / demo-only /
externally dependent / untested / tested but unqualified / blocked /
beta-ready.

| Surface | Classification | Basis |
|---|---|---|
| Mix Review (`mix-review/`) | **Tested but unqualified** | 24/24 unit tests against synthetic fixtures; no human listening review or real-mix benchmark |
| Chat scope/abstention (`chat/app.py`) | **Tested but unqualified** | 39/39 tests; scope-boundary logic is deterministic and testable, but "does it abstain correctly on genuinely ambiguous real questions" hasn't been human-reviewed |
| Chat knowledge answers | **Tested but unqualified** | Live-verified with real cited answers; no formal retrieval-relevance/citation-correctness benchmark yet (see `KENN_KNOWLEDGE_BASE_AUDIT.md`) |
| `apps/backend/src/kenn/server.py` core routes (`/api/health`, `/api/ask`) | **Working, tested** | 22 tests incl. live server smoke test; live-verified via 3 independent paths this session (chat/app.py, direct HTTP, compiled VST3 plugin binary) |
| `apps/backend/src/kenn/server.py` specialist routes (Ableton hardware, stem separation, voice, AutoMix upload) | **Blocked, fails safely** | No KENN-owned implementation exists; every call site individually verified to degrade to a clean error rather than crash |
| VST3/AU plugin real-time core | **Working, tested (sanitizer-verified)** | See `KENN_CPP_ARCHITECTURE_AUDIT.md` |
| VST3/AU plugin network integration | **Working, tested (live integration)** | Compiled-binary integration test against a live server, this session |
| VST3/AU plugin inside an actual DAW | **Untested by this audit** | Built and installed into live plugin folders; owner is DAW-testing separately, outside this audit's own verification |
| `UX/` front-end | **Working, tested at the HTTP layer** | Every API call verified against real routes; live-verified with the exact request shape the UI sends (including streaming); not click-tested in an actual browser by a human |
| AutoMix (`automix/`) | **Blocked, explicitly disabled** | Safety boundary tested (4/4); no render engine exists in this repo |
| Desktop companion | **Blocked by design** | Builds and rebrands cleanly; first-run flow requires locating an external `Audio_Too` repo, incompatible with this repo's standalone model |
| Live control (parameter-level) | **Not yet built -- see `KENN_LIVE_CONTROL_AUDIT.md`** | This mission's primary new deliverable; audited separately in depth |
| Evaluation harness (synthetic scripts) | **Working, tested** | 5 of 7 benchmark scripts run standalone and reproduce deterministically, verified live |
| Evaluation harness (product-decoder scripts) | **Blocked, externally dependent** | 2 scripts hard-import the old `audio_analysis` package, absent from this repo |
| `apps/backend/src/kenn/main.py` core commands (`build`, `ask`, `chat`) | **Working** | `build` run live this session, produces a real index |
| `apps/backend/src/kenn/main.py` deeper commands (`build-checklist`, `download-pdfs`) | **Blocked** | Reference scripts not present in this repo; low priority, non-core |
| `m4l/osc_listener.py` | **Untested** | Not exercised live this session; see `KENN_LIVE_CONTROL_AUDIT.md` for what it actually is |
| `integrations/ableton-remote-script/KENN_Bridge/` | **Untested by this audit, manual-install artifact** | See `KENN_LIVE_CONTROL_AUDIT.md` |

## What changed this session (chronological, for traceability)

1. Mix Review unblocked and rebuilt KENN-owned (was: `RuntimeError` on
   import).
2. Chat's default engine path fixed; missing-index failure made graceful
   instead of an unhandled `SystemExit`.
3. Knowledge base populated with real content (232 approved notes) with
   explicit owner approval, sourced from an external reference checkout,
   narrowly scoped (front-end/knowledge content only, no backend, no
   private data, no business database) and the source material deleted
   after integration.
4. A second, previously-undocumented `audio_too` import bug found and
   fixed (`onnx_embedder.py`) -- found only by actually attempting an
   index build, not by reading code.
5. `apps/backend/src/kenn/server.py` unblocked: six small, self-contained modules
   ported as KENN-owned code to replace `audio_too`/`thursday` imports; a
   `REPO_ROOT` path bug fixed (the same bug class found and fixed in four
   other files this session).
6. `apps/backend/src/kenn/tests/` created -- this package's first-ever test
   coverage (22 tests).
7. VST3/AU plugin built, thread-safety-tested (plain + ThreadSanitizer),
   and integration-tested against the live server for the first time ever
   in this repo's history.
8. A colleague's UX redesign integrated into `UX/`, wired to and
   live-verified against the current server.
9. Plugin and desktop companion rebranded to Shenrendao AI, verified via
   the actual installed bundle metadata (not assumed from source alone).
10. GitHub remote configured and pushed for team collaboration.

## Standalone-boundary status (re-confirmed this audit)

Nothing in this repo's default code paths reaches into the old
`Audio_Too`/`NITE_DSP` estate at runtime. Every place this session's work
touched that estate's *content* (the knowledge notes, the UX redesign)
was an explicit, scoped, owner-approved one-time import of specific
non-backend files -- not a live dependency -- and the source material was
deleted after integration in both cases. Remaining genuine couplings, all
already documented and none silently claimed as resolved:

- ~10 specialist `server.py` routes have no KENN-owned implementation
  (fail safely, not silently).
- `main.py`'s `build-checklist`/`download-pdfs` subcommands reference
  missing scripts.
- AutoMix's render engine doesn't exist in this repo.
- The desktop companion's first-run flow is architecturally incompatible
  with a standalone repo (it exists to find the old estate).
- 2 of 7 evaluation scripts hard-depend on the old `audio_analysis`
  package.

None of these are hidden or newly discovered as "actually fine" -- they
remain open, individually scoped items in `docs/KENN_BETA_GAP_MATRIX.md`.

## Test coverage summary

```
python3 -m pytest mix-review/tests automix/tests chat/tests apps/backend/src/kenn/tests -q
# 89 passed, 0 failed
```
Plus two C++ executables (not part of the Python suite, run manually):
`TestRealtimeThreadSafety` (plain + ThreadSanitizer, both clean) and
`TestServerIntegration` (live-verified against a real server).

At the start of this session: 0 runnable tests in `mix-review/`, `chat/`,
or `apps/backend/src/kenn/` (all three failed to even collect), and no C++ test had
ever been executed in this repo's history.
