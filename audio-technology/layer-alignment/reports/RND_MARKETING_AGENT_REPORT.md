# R&D-F — Marketing Intelligence Agent Report

## Status

**DESIGN READY / PROTOTYPE READY.** `marketing_agent/marketing_agent.py` defines typed `Insight`, `Audience`, `Experiment`, and `Campaign` concepts and emits a JSON plan. The validation run confirmed `external_writes: []`.

## Capabilities

- MarketResearch evidence records
- CompetitorIntelligence observations
- Campaign and Launch planning
- Audience/job-to-be-done definition
- Content strategy drafts
- SEO research placeholders
- Experiment design with metrics and guardrails
- Analytics interpretation as a future read-only module

The prototype distinguishes `FACT`, `MARKET_OBSERVATION`, `INFERENCE`, `STRATEGY`, and `CREATIVE_IDEA`. It does not publish, email, buy ads, mutate a website, write CRM state, or send analytics events.

## Thursday contract

Proposed read-only query names:

- `marketing.launch.plan`
- `marketing.campaign.status`
- `marketing.content.plan`
- `marketing.market.research`
- `marketing.experiments.list`

No live Thursday integration was performed because Audio_Too is owned by an active production writer.

## Biggest next step

Add schema validation, source provenance, expiry dates, and an approval state to every insight. Then evaluate the planner against five synthetic launch scenarios and a human rubric for coherence, evidence separation, and commercial usefulness.

## External writes

**NONE.**
