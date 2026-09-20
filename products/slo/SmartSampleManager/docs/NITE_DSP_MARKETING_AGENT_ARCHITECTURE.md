# NITE DSP Marketing Agent — Architecture Direction

2026-08-14. Design/plan doc, not an implementation — see `docs/MARKETING_AGENT_AUDIT.md` for what
already exists and why this repoints it rather than building fresh. Scoped down from the master
prompt's full Phase H per Section 107's stop rule: this documents the target architecture so a
dedicated future pass can execute it, rather than rushing a partial build inside an already-large
combined session.

## Direction: repoint, don't rebuild

`business/agents/Marketing/` already has the right shape — four capabilities
(`create_campaign`/`draft_outreach`/`generate_social_post`/`analyze_leads`), a local-only Ollama
LLM backend, working memory/persistence, and a permissions-aware execution engine borrowed from
`CodingAgent/`. What it lacks is a NITE DSP identity: its `business_profile.md` and knowledge
base describe Audio_Too's mixing/mastering/podcast-editing service business, not a software
product company.

## Target architecture

```
NITE DSP Marketing Agent
├── business_profile: NITE DSP (not Audio_Too)
├── knowledge base (Section 70) — READ-scoped, human-curated:
│   ├── company facts: NITE DSP, www.nitedsp.co.uk, nitedsp@outlook.com
│   ├── product facts: Smart Sample Manager, verified features only
│   │   (pulled from docs/APP_FUNCTIONAL_VALIDATION.md's EXECUTED list,
│   │   never from aspiration/marketing copy — source of truth stays the
│   │   QA evidence, not the other way around)
│   ├── pricing: £5 intro / £10 regular, perpetual (Section 52-57)
│   ├── experimental-feature list: Ableton integration only, currently
│   ├── compatibility: verified vs. in-progress (docs/SMART_SAMPLE_MANAGER_UX_AUDIT.md,
│   │   product page's own Compatibility section)
│   └── brand voice: restrained, technical-enough, no "revolutionary"/
│       "game-changing"/"next-gen" language (Section 77)
├── data store: separate table/namespace or separate DB file from
│   Audio_Too's service-business leads (Section 75's privacy scoping +
│   the audit's ISOLATE recommendation for data_store.py)
└── tool permission tiers (Section 74):
    READ    — competitor research, SEO research, analytics summaries
    DRAFT   — social posts, emails, campaign plans (default for everything new)
    PROPOSE — experiment recommendations, pricing-performance observations
    EXECUTE — nothing, by default. No integration reaches EXECUTE without
              explicit human wiring + explicit human approval per action.
```

## Prohibited without explicit human approval (Section 73, restated for this system specifically)

Publishing social posts, sending customer emails, changing pricing, creating discounts, spending
ad money, purchasing services, altering the live website, changing product claims, issuing
refunds, contacting creators/influencers, modifying legal text, exposing customer information.
The agent has no code path to any of these today (confirmed in the audit: zero external platform
integrations exist), so this is currently true by simple absence of capability — the point of
listing it here is to make sure it stays true as the agent gains real capabilities later.

## Competitor intelligence (Section 76)

Structure, not content: `{source, observed_date, claim, confidence}` per fact, stored in the
agent's existing memory/data-store layer rather than hardcoded. Category to research once this is
built: Atlas, XO, Sononym, COSMOS, ADSR Sample Manager, and adjacent sample-discovery tools — not
researched this pass (would mean live web research the agent isn't yet pointed at NITE DSP to
do).

## Why this wasn't executed this session

Repointing `business_profile.md`, building the actual knowledge base content, and isolating the
data store are each real, contained tasks — but doing them well means writing NITE DSP's brand
voice and knowledge base carefully (exactly the kind of content that should derive from verified
product facts, not be rushed), and this session already covered baseline verification, two real
JUCE product fixes with full rebuild/test/verify, and a website pricing update. Recommended as
the next focused pass once the product fixes in this session are verified stable.
