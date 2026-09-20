# Launch Analytics Plan

2026-08-14. Design only — no analytics implementation shipped this pass. Privacy-first by
requirement (Section 90 of the current master prompt), consistent with the product's own
"nothing about your library leaves your drive" claim, which any website/product analytics
addition must not contradict.

## Business questions to answer

Website funnel: visits → product-page engagement → pricing engagement → account creation →
download → activation → purchase. Documentation usage and support themes, to find real friction
points rather than guessing.

## What we do NOT need, ever

Sample filenames, sample audio, sample paths, embeddings, DAW project contents. None of this
should reach any analytics system, first-party or third-party. The product's local-first privacy
claim depends on this remaining true.

## Website funnel events (conceptual, not implemented)

```
landing_view
product_view
learn_view
pricing_view
account_start
download_start
activation_success
purchase_success
```

## Why nothing was implemented this pass

Adding real analytics means picking a provider, understanding its data-processing/legal
implications (cookie consent requirements, data residency, GDPR if EU/UK visitors are expected —
UK company, `.co.uk` domain, so this matters), and wiring real event tracking into the Next.js
site and FastAPI backend. That's a real scope of work with real legal-adjacent implications
(Section 91's explicit "only implement analytics when privacy/legal implications are
understood" instruction) — not something to bolt on inside an already-large combined
product+website+marketing session. Recommendation: treat as its own focused pass once launch is
closer and the actual provider decision (privacy-conscious options: Plausible, Fathom, or a
minimal self-hosted event log against the existing Postgres) has been made by the owner.

## Product telemetry

Not added. Section 92 explicitly requires this to be designed separately, with minimal data,
transparency, and no audio/library contents — deferred entirely, no silent tracking added to the
JUCE product this pass or any prior one.

## Marketing agent's eventual role

Once real analytics exist, the marketing agent (`docs/MARKETING_AGENT_AUDIT.md`,
`docs/NITE_DSP_MARKETING_AGENT_ARCHITECTURE.md`) can summarize aggregated metrics on a cadence —
visitors, product views, downloads, activations, purchases, conversion, top documentation pages,
top support themes. This is a downstream consumer of analytics data, not a reason to rush
analytics implementation ahead of understanding its legal implications.
