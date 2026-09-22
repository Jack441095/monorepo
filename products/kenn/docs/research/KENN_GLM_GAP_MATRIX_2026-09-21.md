# KENN Full-GLM Capability Gap Matrix — 2026-09-21

“Full GLM capability” = open-ended producer intent → grounded Live
understanding → multi-step typed plans → safe execution → exact undo,
with audio/MIDI/musical reasoning, generation, and learning. Each area is
scored against code paths, test results, or real runtime evidence from the
2026-09-21 qualification (report: `docs/reports/KENN_ABLETON_GLM_QUALIFICATION_2026-09-21.md`).

States: production-ready | tested-but-incomplete | implemented-but-unqualified |
reachable-but-unwired | experimental | mocked | broken | missing.

| # | Area | State | Evidence |
|---|---|---|---|
| 1 | Natural-language intent understanding | tested-but-incomplete | Deterministic regex parser (`core/live_intent.py`, ~1500 lines) handles device/track/param/mixer phrasing incl. repairs QLM-01/02/05; verified live. No model-backed parsing on the command path (LLM disabled); open-ended/phrasal variety beyond patterns clarifies. |
| 2 | Entity extraction & reference resolution | tested-but-incomplete | Exact index+name binding with duplicate refusal; verified live. No anaphora (`it`/`that`), no corrections, no fuzzy/duplicate-name disambiguation dialogue. |
| 3 | Conversation & project memory | missing | Command gateway stateless per call (matrix E all clarify). Session-scoped proposals exist but no conversational memory, no project history surface. |
| 4 | Live Set state representation | tested-but-incomplete | Full snapshot (tracks/devices/mixer/tempo/signature/selection) read live every call. No clips/notes/returns-locator content, no sections, no persisted set model. |
| 5 | Track/clip/device/parameter identity | production-ready | Index+name binding, stale-version rejection, duplicate-insert guard, sparse Live indices preserved — all verified live with readbacks. Clip identity partially covered (duplication/rename services, not live-fired here). |
| 6 | Typed planning & tool selection | tested-but-incomplete | Versioned proposal schemas per action with confirmation gating, verified live. No multi-step planner on chat (recipes natural-language-limited; compound EQ needs two turns); move/bypass/remove/tempo plans missing. |
| 7 | Confirmation & risk classification | production-ready | Every mutation requires exact-token confirmation; idempotency keys; destructive chat verbs refused; KENN_ALLOW_DAW_CONTROL default-deny (403 verified). |
| 8 | Idempotency & durable receipts | production-ready | Repeat confirm rejected (“already executed”); receipts journal-persisted across restarts; verified live incl. restart test. |
| 9 | Readback & outcome verification | production-ready | Every mutation verified against fresh Live reads (raw + display strings); failures fail closed. 500 Hz / +3.00 dB / −18 dB / 1 kHz measured, not assumed. |
| 10 | Exact undo & restart recovery | tested-but-incomplete | Identity-bound undo with verified reverts proven live for inserts, params, mixer. Pending proposals correctly die on restart (409). Untested: Live-restart recovery, return/clip undo coverage. |
| 11 | Audio understanding | missing | No audio analysis wired to chat (mixer telemetry exists elsewhere but not consumed by the command path; musical requests clarify-fail). |
| 12 | MIDI/key/chord/rhythmic understanding | missing | Generative-MIDI modules exist in-tree but are unwired to chat; no clip-note reads on the command path. |
| 13 | Arrangement & section understanding | missing | No locator/scene-content reasoning on chat (locator read endpoints exist; unused by planner). |
| 14 | Mix reasoning & masking analysis | missing | Mix-doctor/masking engines exist in-tree; not reachable from the Ableton chat surface. |
| 15 | Generative MIDI capability | reachable-but-unwired | `core/generative_midi.py`, audiogen midi proposals exist; no chat invocation, no Live insertion path qualified. |
| 16 | AudioGen generation & artifacts | reachable-but-unwired | Audiogen handlers/routes exist; no chat-driven generation, preview, or Live insertion qualified in this task. |
| 17 | SLO search/classification/handoff | implemented-but-unqualified | Adapter + routes present; classification DB absent in qual env; not exercised against Live here. |
| 18 | Retrieval quality & citations | blocked-env | `/api/ask` 500s without generated index (`SystemExit` from `load_chunks`); stale server failed differently (missing module). Retrieval unqualified in this env. |
| 19 | Model routing & fallback | experimental | LLM planner paths exist (shadow/active) with deterministic-match gating, but KENN_LIVE_LLM_ENABLED off; untested live in this task. |
| 20 | Preference learning & isolation | missing | No producer-preference storage, no opt-in learning, no project/user isolation on the command path. |
| 21 | Latency & background execution | tested-but-incomplete | Measured: propose ~104–180 ms, executions ~450–760 ms verified. No background/long-task management on chat; 60/60s/IP limiter trips under bursts. |
| 22 | Observability & evaluation | tested-but-incomplete | Structured receipts, journals, stage timings, qualification runners (mock+real) present and used. No continuous eval harness or telemetry pipeline in this env. |
| 23 | Security, privacy & permissions | tested-but-incomplete | Default-deny DAW flag, confirmation tokens, allowlists, no-credential-in-repo boundaries verified. No formal threat model/permissions UX review in this task. |
| 24 | Packaging, installation & updates | tested-but-incomplete | Worktree-tested backend runs from source; installer/updater, Control Deck bundling, Node-24 prerequisite chain unqualified (provider absent). |
| 25 | Real-world reliability inside Ableton | tested-but-incomplete | Single disposable set, stopped transport, small track count: dependable. Untested: large sessions, playback-during-edit, Live restarts, real Control Deck transport, 5-track duplicate/clip fixture. |

## Truth-map summary
- Production-ready: 5, 7, 8, 9.
- Tested-but-incomplete: 1, 2, 4, 6, 10, 21, 22, 23, 24, 25.
- Implemented-but-unqualified: 17. Reached-but-unwired: 15, 16.
- Experimental: 19. Blocked-env: 18. Missing: 3, 11, 12, 13, 14, 20.
- Mocked/broken as presented: none (all live claims backed by readbacks; pre-existing breakage repaired with tests).
