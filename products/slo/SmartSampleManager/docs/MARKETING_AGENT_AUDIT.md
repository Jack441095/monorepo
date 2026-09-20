# Marketing Agent Audit

2026-08-14. Read-only discovery of the existing marketing-agent system referenced in the current
master prompt. Nothing was modified, run, or executed as part of this audit — inspection only.

## Bottom line

A real, semi-functional marketing agent exists at `business/agents/Marketing/` — but it's built
for **Jack's audio-engineering *service* business** (recording/mixing/mastering/podcast editing,
per `business_profile.md`), not NITE DSP / Smart Sample Manager. There is no NITE DSP-specific
marketing agent yet. Per the master prompt's own Section 61 ("do not build another one from
scratch first"), the plan is to **repoint/refactor**, not replace — see the component table
below and `docs/NITE_DSP_MARKETING_AGENT_ARCHITECTURE.md` for the direction.

## Component table

| Component | Purpose | Current state | Quality | Security risk | Privacy risk | Reusability | Recommendation |
|---|---|---|---|---|---|---|---|
| `business/agents/Marketing/` (`main.py`, `agent_loop.py`) | Exposes `create_campaign`/`draft_outreach`/`generate_social_post`/`analyze_leads` | Functional CLI, delegates to `CodingAgent`'s generic planner | Prototype-grade; basic smoke tests exist (`tests_all_agents.py`) | None found | Local-only, no external send | High -- the *interface shape* (four capabilities) fits NITE DSP marketing needs directly | **REFACTOR**: keep the four-capability shape, repoint the underlying knowledge/business-profile it drafts from |
| `business/agents/Shared/agent_llm.py` | LLM calls via local Ollama (`qwen2.5:1.5b`/`qwen2.5-coder:7b`) | Working, graceful fallback if Ollama isn't running | Solid | None -- no cloud API keys, no data leaves the machine | None -- fully local inference | High | **REUSE** as-is. Matches this program's own "least privilege," no-cloud-dependency-by-default spirit |
| `business/agents/Shared/data_store.py` + business dashboard SQLite (`business/app/db.py`) | Persists leads/campaigns/drafts | Working, real tables | Adequate | Shared DB with the rest of the business dashboard -- not isolated per-business | Needs a hard boundary before NITE DSP data mixes with Audio_Too service-business data | Medium | **ISOLATE**: NITE DSP marketing data needs its own table/namespace or its own DB file, not commingled with the audio-engineering-service business's leads |
| `business/agents/CodingAgent/` (execution engine, memory, permissions) | Generic autonomous task execution the Marketing agent delegates to | Working, has its own test suite and a real `permissions.py` | The most mature piece found | One synthetic secret-shaped string in its own test fixture (`tests_agent.py:55`, `"API_KEY = 'sk-...'"`) -- confirmed fake, used to test the agent's own secret-detection behavior, not a real credential | N/A | High | **REUSE** unchanged -- this is infrastructure, not business-specific |
| `Marketing/campaigns/`, `Marketing/leads/` (directories) | Scaffolding for campaign/lead content | Mostly empty, README-only placeholders | N/A | N/A | N/A | Low as-is | **REPLACE** the placeholder content with real NITE DSP campaign/lead structure once the agent is repointed |
| `Marketing/agent.md` | System-prompt-style role/tone/rules spec | Aspirational -- describes "weekly marketing reviews," "service offers" not clearly implemented as distinct code paths | Documentation, not code | N/A | N/A | Partial | **REFACTOR**: the *rules* (no fabricated testimonials, no fake results) transfer directly to NITE DSP; the *business content* (service offers, audio-engineering-client language) does not |
| Social/email/ads platform integrations | — | **Do not exist** -- grepped for Twitter/X, Instagram, LinkedIn, Buffer, SendGrid, Mailchimp, SEMrush, Google Ads/Analytics; zero matches | N/A | N/A | N/A | N/A | Confirms the agent only ever drafts content to files/DB -- a human copies it out. No autonomous-posting risk exists today because no posting capability exists today |

## Secret/credential audit (Section 66)

No hardcoded API keys, tokens, or passwords found in the Marketing agent, Shared infra, or
CodingAgent. The only regex hit for an API-key-shaped string was a deliberately synthetic test
fixture (`business/agents/CodingAgent/tests_agent.py:55`) used to test the agent's own
secret-detection logic — confirmed fake by content and context, not flagged as a real leak.

## Architectural boundary (Section 67)

The Marketing agent is correctly separable from the Smart Sample Manager product: it lives
entirely under `business/agents/`, has no code path that touches `nitedsp/` or
`studio/vst3_plugins/SmartSampleManager/`, and produces no public-facing output on its own (no
posting capability exists). Keeping it there — internal business infrastructure, never a product
feature, never bundled or exposed on the website — requires no new work; it's already true.

## What wasn't done this pass

Actually repointing the agent's business-profile content from Audio_Too's service business to
NITE DSP, building the NITE DSP knowledge base (Section 70), and wiring least-privilege tool
permissions (Section 74) are real implementation work, scoped and directioned in
`docs/NITE_DSP_MARKETING_AGENT_ARCHITECTURE.md` but not executed this session — this was a
discovery/audit pass, not a build pass, consistent with Section 63's "first inspect, then
classify" instruction.
