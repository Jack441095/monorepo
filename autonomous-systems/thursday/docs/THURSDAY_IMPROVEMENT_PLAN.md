# Thursday Improvement Plan — Evolving Toward True Ambient Intelligence

**Date:** 2026-08-08  
**Scope:** Analysis + prioritized roadmap for deepening Thursday as Audio_Too's full-system AI orchestrator.  
**Context docs:** `THURSDAY_UPGRADE_PLAN.md`, `thursday/changelog.md`, `thursday/orchestrator.py`, `thursday/brain.py`, `thursday/autonomous_dispatcher.py`, `thursday/autonomous_producer.py`  
**Code verified against:** `thursday/` modules, `business/agents/` (Admin, Marketing, Research, CodingAgent, MetaAgent, Shared), `Audio_Too/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md`

---

## 0. Executive Summary

**Thursday is already far more mature than its v2.0.0 changelog suggests.** The changelog documents 18 modules shipped as the "Jarvis-Class Orchestrator Upgrade." But the directory listing reveals an additional 20+ modules beyond that changelog — `autonomous_dispatcher.py`, `autonomous_producer.py`, `brain.py`, `subagent_runtime.py`, `phase3_handlers.py`, `scheduler.py`, `daw_watcher.py`, `events.py`, `multimodal.py`, `plan_memory.py`, `feedback.py`, `user_profile.py`, `personality.py`, `stt_worker.py`, `tts_worker.py`, `voice.py`, `macros/` (3 real YAML files), and more.

The v2.0.0 upgrade plan (`THURSDAY_UPGRADE_PLAN.md`) describes these as Phase 5+ *future aspirations*. The code exists. The question is: **what's production-ready, what's scaffolding, and what needs real-world evidence to close the loop?**

The same discipline that governs KENN applies here: **never fabricate evidence.** Thursday is a business orchestrator — its claims must reflect real client outcomes, not fabricated metrics.

This plan focuses on three axes: (1) **integration hardening** — making sure the many implemented modules work together reliably; (2) **evidence-gathering infrastructure** — capturing the real business impact of Thursday's actions; (3) **ambient intelligence maturation** — evolving from "reactive with proactive alerts" to "always-on, context-aware, anticipatory."

---

## 1. What Thursday Already Is

### 1.1 Core Capabilities (v2.0.0, verified)

| Capability | Implementation | Evidence |
|---|---|---|
| **Intent Classification** | `intent.py` — 10 intent categories + regex entity extraction | All 12 tests pass (changelog) |
| **Entity Resolution** | `resolver.py` — pronoun resolution ("her" → client), implicit reference ("the client"), temporal references | Integrated into orchestrator |
| **Service Registry** | `registry.py` — declarative `ServiceDef` with triggers, intents, risk scoring, post-hooks | ~30+ services registered |
| **Unified API Client** | `client.py` — `APIClient` facade returning `{ok, data, error}` typed dicts for all modules | Full Dashboard/Creative Lab integration |
| **Session Memory** | `session_manager.py` — persistent JSON session store with context tracking | `--session`/`--new-session` CLI flags |
| **Compound Request Handling** | `compound.py` — splits "Invoice Jordan and check pipeline" into sequential actions | Integrated into orchestrator |
| **Disambiguation** | `disambiguator.py` — asks clarification when ambiguous ("Which Jordan?") | Recovery strategies in `errors.py` |
| **Proactive Monitoring** | `monitor.py` — stale leads, overdue invoices, new enquiries, financial health | Alerts prepended to every response |
| **Response Formatting** | `formatter.py` — standardized output with "Try next:" follow-ups | Integrated into orchestrator |
| **Error Recovery** | `errors.py` — `AmbiguousEntityError`, `MissingInfoError`, `NoMatchError`, `ServiceError` | Recovery suggestions per error type |

### 1.2 Business Agents

| Agent | Role | Key Capabilities |
|---|---|---|
| **Admin** (`business/agents/Admin/`) | Client/studio management | Lead tracking, invoicing, expenses, reminders, reports, calendar scheduling |
| **Marketing** (`business/agents/Marketing/`) | Content & outreach | Campaigns, lead nurturing, content drafting, A/B testing |
| **Research** (`business/agents/Research/`) | Market intelligence | Trend monitoring, competitive analysis, service demand tracking |
| **CodingAgent** (`business/agents/CodingAgent/`) | Code generation | JUCE/C++ plugin codegen, autonomous coding, web dashboard |
| **MetaAgent** (`business/agents/MetaAgent/`) | Meta-reasoning | Task coordination, plan abstraction, multi-agent orchestration |

### 1.3 Additional Modules (Beyond v2.0.0 Changelog)

The following modules exist in the `thursday/` directory but are not covered by the v2.0.0 changelog — indicating Phase 5 development is either underway or recently completed:

| Module | Function | Phase 5 Feature |
|---|---|---|
| `autonomous_dispatcher.py` | Commercial job orchestrator: AudioGen → Stem Export → AutoMix → LTAS → KENN → Invoice/Delivery | Full autonomous commercial pipeline |
| `autonomous_producer.py` | Decomposes NL instructions into multi-step audio workflows | Commercial production automation |
| `brain.py` | LLM-backed decision engine with JSON schema validation + codebase map loading | Smarter routing + codebase Q&A |
| `subagent_runtime.py` | Thread-pool-based in-process agent dispatch with timeout | Multi-agent swarm execution |
| `phase3_handlers.py` (544 lines) | AudioGen status/queue/history, Mix Review, Creative Lab handlers | Deep integration with production tools |
| `scheduler.py` / `scheduling.py` | Calendar/scheduling, daily briefing, reminders | Time intelligence |
| `daw_watcher.py` | DAW state monitoring | DAW integration |
| `events.py` | Event system for cross-module communication | Reactive architecture |
| `multimodal.py` | Multimodal input (text + audio?) | Multi-channel interface |
| `plan_memory.py` | Plan history with FTS matching | Learning from past decisions |
| `feedback.py` | Feedback collection + auto-correction rules | Continuous improvement |
| `response_rewrite.py` | Response quality improvements | Better output |
| `user_profile.py` | User preferences + learning | Personalization |
| `personality.py` | Personality config + greeting templates | Companion feel |
| `stt_worker.py` / `tts_worker.py` / `tts_worker_mlx.py` | Speech-to-text + text-to-speech | Voice I/O |
| `voice.py` / `voice_output.py` | Voice interface | Voice interaction |
| `watcher.py` | File system monitoring | Auto-scan directories |
| `macros/` | 3 YAML macro files: `morning_briefing`, `new_client_onboard`, `weekly_summary`, `mix_review_full_pipeline` | Custom automations |

### 1.4 Integration with KENN

Thursday acts as the **business orchestrator** that dispatches to KENN for audio-engineering-specific questions:
- `thursday/client.py` exposes KENN endpoints through the `APIClient` facade
- `thursday/phase3_handlers.py` handles AudioGen/Mix Review workflows
- `business/agents/Shared/kenn_bridge.py` provides the bridge primitives
- `autonomous_dispatcher.py` calls `KennAutonomousAgent()` for DAW control decisions
- The orchestrator's `_kenn_contract_text()` (line 94-125) passes KENN's grounding metadata (confidence, sources, grounding mode, quality scores) through to the user

---

## 2. The Gap Analysis

### 2.1 Integration Hardening Gaps (Safe, High-Impact)

Thursday has many modules that need to work together. The risk is **integration failures** — modules that work in isolation but fail when composed.

| # | Gap | Root Cause | Effort |
|---|---|---|---|
| **H1** | **`brain.py` LLM routing reliability** | The changelog (v2.0.0) says the brain was "unreliable against a real local model" before codebase-map filtering was added (line 40-46 of `brain.py` — only loads the codebase map for code questions). The `_generate_plan()` / `decide()` path may still struggle with ambiguous or novel requests. | M |
| **H2** | **`subagent_runtime.py` timeout / error handling** | Thread-pool dispatch with timeouts is inherently fragile — a hung agent (e.g. CodingAgent with a complex JUCE request) can silently timeout. The graceful-failure pattern (returns error results, never crashes) is good, but error *messages* may not surface to the user clearly. | S-M |
| **H3** | **Macro execution error propagation** | The `mix_review_full_pipeline.yaml` macro chains AudioGen → KENN fixes → AutoMix → email. If any stage fails, the macro needs to gracefully degrade ("Stage 2 failed, but I saved the stems") rather than aborting silently. | M |
| **H4** | **Voice I/O pipeline integration** | `stt_worker.py`, `tts_worker.py`, `voice.py`, `voice_output.py` exist but the `--voice` flag's reliability against a real local STT (Whisper.cpp) and TTS (macOS `say` or MLX) is untested. Wake-word detection may be scaffolding. | M |
| **H5** | **`daw_watcher.py` + `watcher.py` reliability** | File system watching + DAW state monitoring run in background threads — race conditions, missed events, and duplicate triggers are common failure modes. Need robustness tests. | S-M |
| **H6** | **`autonomous_producer.py` torch dependency fragility** | Explicitly deferred torch imports (lines 15-29) to avoid crashing the web server on ABI mismatch. But the pipeline itself (Composition → Stem Export → Mix Decision → LTAS Match) has never been verified end-to-end with a real commercial job. | M |

### 2.2 Evidence & Business Impact Gaps

Thursday orchestrates a business, not just code. The gap is **tracking real impact**.

| # | Gap | Impact |
|---|---|---|
| **E1** | **No business outcome tracking** | Thursday can route "invoice Jordan" to the Admin agent, but there's no closed loop: "did the invoice get paid? did the client renew? did the referral materialize?" The `due_work.py` module tracks overdue items, but there's no "business impact attribution" — linking a Thursday-routed task to a downstream business outcome. |
| **E2** | **No agent reliability scoring** | The `feedback.py` module exists for collecting thumbs up/down, but there's no per-agent reliability metric ("Admin drafts are 85% accepted, Marketing campaigns 40% engaged"). Without this, Thursday can't route to the best agent or know when to ask for human review. |
| **E3** | **No causal chain tracking** | When Thursday executes a macro ("morning briefing"), it touches monitor → client → audiogen → formatter. There's no end-to-end trace showing "which subagent did what, in what order, with what result." The `plan_memory.py` tracks the *plan*, but not the *execution trace*. |
| **E4** | **Macro success/failure analytics** | The macros exist (3 YAML files), but there's no dashboard showing "which macros fire most, which succeed, which need user intervention." The `analytics/` directory exists but its contents are unverified. |

### 2.3 Feature Maturation Gaps (Phase 5 Aspirations)

The upgrade plan describes Phase 5+ as future work. Modules exist, but they need to be **productionized**.

| # | Gap | What's Needed |
|---|---|---|
| **M1** | **`personality.py` + mood detection** | The personality file exists, but mood detection ("I'm stressed" → calm responses) requires natural language mood classification — a real NLP task. Is this just scaffolding or a working classifier? |
| **M2** | **Multi-user profiles** | `user_profile.py` exists, but switching between users ("I'm Jack" / "I'm Sarah") needs per-user contexts in `session_manager.py` + separate preferences, alert configs, and history. |
| **M3** | **Calendar two-way sync** | `scheduling.py` exists, but full calendar integration (macOS Calendar read/write + event creation) needs AppleScript/EventKit bridges that may not be complete. |
| **M4** | **Slack/WhatsApp/email external integration** | These are P3 in the priority order — lower priority, but they're the path to making Thursday a true multi-channel assistant. |
| **M5** | **LLM-powered routing** | The fallback chain is: regex → ML classifier → LLM. The `brain.py` decide() function is the LLM path, but it's gated on `AUDIO_TOO_LLM_ENABLED` (same off-by-default convention as KENN). Is the ML classifier even trained? |

### 2.4 Knowledge Integration Gaps

| # | Gap | What's Needed |
|---|---|---|
| **K1** | **KENN knowledge base awareness** | Thursday's `brain.py` loads `docs/CODEBASE_MAP.md` for codebase questions, but it doesn't reference KENN's 241 knowledge notes for technical audio advice. Thursday routes to KENN via `client.py`, but doesn't *know* what KENN knows. |
| **K2** | **No cross-agent knowledge sharing** | Admin knows client pricing, Research knows market trends, KENN knows audio technique — but these knowledge bases don't share context. A request like "should my podcast intro be louder?" needs Admin (client volume), Marketing (audience), and KENN (loudness standards) to coordinate. |

---

## 3. The Roadmap

> **Principle:** Thursday is a business orchestrator. Every improvement should either (a) make it more reliable at routing the right task to the right agent, or (b) make it more useful at anticipating needs. No "ambient intelligence" feature ships until it demonstrably saves time in a real business context.

### Phase 1 (2-3 weeks) — Integration Hardening

**Goal:** Make the existing modules work together reliably. Close the gaps between "file exists" and "production-ready."

**Deliverables:**
- **D1.1 — `brain.py` reliability pass** (`H1`): Audit the LLM decision engine's `decide()` / `_generate_plan()` paths against real requests. Add a test corpus of 50 ambiguous / compound / novel requests and verify the decision is correct or gracefully falls back to keyword routing. Fix any prompt-size or schema-validation issues found.

  - *Evidence:* 15 new tests in `tests/thursday/` + 1 live run against a real local model.

- **D1.2 — Subagent execution trace** (`E3`): Every `subagent_runtime.dispatch()` call records a trace: agent, command, elapsed_ms, status, result summary. Stored in `thursday/analytics/execution_traces.jsonl`. This is the foundation for the causal-chain tracking gap.

  - *Evidence:* 6 tests (trace format, persistence, timeout recording, error recording).

- **D1.3 — Macro error propagation** (`H3`): Each macro step wraps its service call in try/except. On failure, the macro produces a structured "partial success" message: "Stages 1-3 completed. Stage 4 (AutoMix) failed: [reason]. Stems were saved to [path]."

  - *Evidence:* 4 tests (success path, single-stage failure, multi-stage partial, recovery suggestion).

- **D1.4 — Voice I/O smoke tests** (`H4`): Verify `stt_worker.py` transcribes a real 5-second audio clip correctly, `tts_worker.py` produces audible speech, and `voice.py`'s `--voice` flag enters continuous listening without crashing. Mark any that are scaffolding vs. working.

  - *Evidence:* 3 tests + 1 live manual verification.

- **D1.5 — KENN knowledge awareness** (`K1`): `brain.py`'s `looks_like_codebase_question()` is joined by `looks_like_audio_engineering_question()` that checks KENN's knowledge notes index. When the request is audio-engineering-specific, Thursday routes to KENN rather than re-deriving from first principles.

  - *Evidence:* 5 tests.

### Phase 2 (4-6 weeks) — Business Impact Infrastructure

**Goal:** Start tracking whether Thursday's actions actually move the needle on real business outcomes.

**Deliverables:**
- **D2.1 — Business outcome attribution** (`E1`): When Thursday routes a task ("invoice Jordan"), it records a link: `task_id → client_id → invoice_id → payment_status`. The `due_work.py` monitor already checks overdue invoices; this extends it to "tasks Thursday recommended that are still outstanding."

  - *Evidence:* 4 tests (link creation, status cascade, overdue detection, payment linkage).

- **D2.2 — Per-agent reliability scoring** (`E2`): Every agent dispatch returns a result. Track: acceptance rate (did the user accept the drafted output?), error rate (did the dispatch crash?), speed (elapsed_ms). Surface this as a simple score in the CLI: "Admin: 85% reliable · Marketing: 62% reliable · KENN: 95% reliable."

  - *Evidence:* 5 tests.

- **D2.3 — Macro analytics dashboard** (`E4`): A new `tests/analytics/` module or CLI command (`/thursday macro-stats`) showing: which macros fire most, success/failure rates, average execution time, common failure points.

  - *Evidence:* 6 tests.

- **D2.4 — DAW watcher robustness** (`H5`): Add deduplication (same file-change event shouldn't trigger analysis twice), debouncing (rapid successive events collapse into one), and error recovery (watcher thread death → auto-restart).

  - *Evidence:* 8 tests.

### Phase 3 (2-3 months, Evidence-Gated) — Ambient Intelligence Maturation

**Goal:** Evolve Thursday from "reactive with proactive alerts" to "always-on, context-aware, anticipatory."

**Prerequisites:** Phase 1 + Phase 2 complete + **at least 10 real business tasks** routed through Thursday with outcome tracking.

**Deliverables:**
- **D3.1 — Cross-agent knowledge sharing** (`K2`): A shared context object that flows through every dispatch: `{"client_preferences": {...}, "current_project": {...}, "audio_knowledge": [...]}`. Admin provides client history, Research provides market context, KENN provides technique notes.

  - *Evidence requirement:* 3 real cross-domain requests produce measurably better results (shorter, more relevant answers) than siloed dispatch.

- **D3.2 — Multi-user profile switching** (`M2`): `--user Jack` / `--user Sarah` switches the entire context: session history, preferences, alert configurations, business metrics. Built on the existing `user_profile.py` + `session_manager.py`.

  - *Evidence:* 4 tests.

- **D3.3 — Calendar two-way sync** (`M3`): `scheduling.py` gains real macOS Calendar integration via AppleScript — read events, create events with reminders, detect conflicts. The daily briefing ("Good morning, Jack. Here's your day:") reads real calendar data.

  - *Evidence:* 5 tests + 1 live verification (read-only, no mutations).

- **D3.4 — Mood detection** (`M1`): Simple classifier built on the existing `feedback.py` patterns + `response_rewrite.py`. "I'm stressed" → calm mode: shorter responses, fewer follow-up suggestions, offer to reschedule non-urgent items. Start with 3 moods (stressed, celebrating, normal), rule-based (no ML needed initially).

  - *Evidence:* 6 tests.

- **D3.5 — External channel integration** (`M4`): Start with Slack (lowest effort — webhook in, bot token out). Thursday can receive a message in a Slack channel, route it through the orchestrator, and respond in-thread.

  - *Evidence:* 3 tests + 1 live Slack workspace verification.

---

## 4. Implementation Priorities

| Priority | Feature | Why |
|---|---|---|
| **P0** | `brain.py` reliability pass (D1.1) | The decision engine is the core of everything Thursday does. If it misroutes, nothing else works right. |
| **P0** | Subagent execution trace (D1.2) | Without traces, you can't debug why Thursday did the wrong thing. Foundation for all later analytics. |
| **P0** | KENN knowledge awareness (D1.5) | Thursday shouldn't guess at audio technique when KENN already has 241 approved notes. |
| **P1** | Business outcome attribution (D2.1) | The difference between a fancy assistant and a useful one is whether it can prove it helped. |
| **P1** | Macro error propagation (D1.3) | Macros exist but are fragile. A partial-success report is vastly better than a silent abort. |
| **P1** | Per-agent reliability scoring (D2.2) | Lets you see which agents to trust and when to intervene. |
| **P2** | Voice I/O smoke tests (D1.4) | Verify what's scaffolding vs. what works before promising hands-free operation. |
| **P2** | DAW watcher robustness (D1.3) | File system watching is inherently racy; fix before it causes data loss or missed scans. |

---

## 5. The Evidence Hierarchy (Same as KENN)

```
Level 1 — Unit Test (green in CI)
  └─ Every new handler/route/agent starts here
Level 2 — Live Round-Trip Verified
  └─ Real request through Thursday, real business action executed
Level 3 — Producer/Customer Usability Feedback
  └─ "I would use this in my actual workflow" ≥4/5
Level 4 — Business Impact Verified
  └─ Thursday-routed task produced a measurable business outcome (invoice paid, lead converted, time saved)
Level 5 — Case Study / Client Outcome
  └─ Real paying client job routed through Thursday, delivered, testimonial
```

No Phase 3 feature ships as a default until it passes Level 2. No Phase 4 feature ships until Level 3. The "Jarvis" dream (voice, calendar, ambient suggestions) stays experimental until Level 4 evidence shows it actually saves time.

---

## 6. Key Integration Points (Thursday ↔ KENN ↔ Business)

```
┌─────────────────────────────────────────────────────────────┐
│                    THURSDAY (Orchestrator)                   │
│                                                              │
│  CLI: ./audio-too thursday "..."                             │
│  Server: :8092 (/ask, /health, /session/<id>)               │
│                                                              │
│  ┌───────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  intent   │  │ resolver │  │  client  │  │ registry │   │
│  │classify   │  │resolve   │  │API facade│  │score+sel │   │
│  └────┬──────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │             │             │          │
│  ┌────▼────────────────────────────────────────────▼─────┐  │
│  │  orchestrator.handle() → routes to agents/subagents   │  │
│  │     ┌──────────┐  ┌──────────┐  ┌──────────┐         │  │
│  │     │   KENN   │  │  Admin   │  │Marketing │         │  │
│  │     │(client.py)│  │ (agent)  │  │ (agent)  │         │  │
│  │     └──────────┘  └──────────┘  └──────────┘         │  │
│  │     │             │              │                    │  │
│  │     │             │              │                    │  │
│  │     └─────────────┼──────────────┘                    │  │
│  │                   │                                   │  │
│  │         business/agents/Shared/                       │  │
│  │         ├── kenn_bridge.py  (KENN ↔ Thursday link)     │  │
│  │         ├── due_work.py    (overdue tracking)          │  │
│  │         ├── reminders.py   (follow-up reminders)       │  │
│  │         └── reports.py     (business summaries)        │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  autonomous_dispatcher.py   (commercial pipeline)     │  │
│  │  AudioGen → Stem Export → AutoMix → LTAS → KENN      │  │
│  │  → Invoice/Delivery                                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Immediate Next Steps

1. **D1.1 — `brain.py` reliability pass.** Audit the LLM decision engine's routing against 50 real request patterns. This is the single highest-leverage fix — if Thursday misroutes, nothing else matters.
2. **D1.2 — Subagent execution trace.** Add structured logging to `subagent_runtime.dispatch()`. Without this, you can't debug why Thursday did the wrong thing, and you can't measure agent reliability (D2.2).
3. **D1.5 — KENN knowledge awareness.** Teach Thursday's `brain.py` to recognize audio-engineering questions and route them to KENN, rather than guessing.
4. **D2.4 — Structured feedback on every response.** Turn on `feedback.py`'s thumbs-up/down on all Thursday responses, not just selected ones. This is the evidence pipeline — without it, Thursday can't learn.

> **Thursday's strength is breadth — it touches every part of the business. Its weakness is depth — it needs to prove it reliably saves time and drives outcomes, not just appears capable. This plan makes evidence-gathering the first feature, not the last.**
