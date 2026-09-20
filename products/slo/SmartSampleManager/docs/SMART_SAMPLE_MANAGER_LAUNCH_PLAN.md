# Smart Sample Manager — Launch Plan

2026-08-14. Grounded in verified product features (`docs/APP_FUNCTIONAL_VALIDATION.md`,
`docs/SMART_SAMPLE_MANAGER_UX_AUDIT.md`) and owner-approved pricing. No fabricated dates, no
invented metrics, no claims beyond what's actually built and tested.

## Positioning

**NITE DSP introductory launch pricing.** Not "cheap software" — the £5 intro price is framed as
a deliberate launch offer with a stated regular price (£10) right next to it, the same way any
premium product runs a launch promotion without cheapening the product itself.

Core verified strengths to build messaging around:
- Acoustic-similarity search (Find Similar) — audio-to-audio, not text search. Never claim
  natural-language query support; it doesn't exist.
- Visual Map — spatial library exploration by sonic similarity.
- Fully local — no sample audio, filename, or path uploaded in ordinary use.
- Perpetual license, no subscription.

Do not lead with ML architecture (ONNX, embeddings, HNSW) — that's technical-appendix material,
not the pitch. See `docs/NITE_DSP_UX_SYSTEM.md` / the website copy style already established.

## Value moment (candidate, unvalidated)

Best current hypothesis, not yet confirmed by real user behavior: a producer selects a sample
they already like, hits Find Similar, and immediately gets a short list of other sounds from
their own library they'd forgotten they had. This is a hypothesis to validate with real beta/
launch usage, not a claim to publish as fact.

## Funnel (as currently built)

```
Website (nitedsp.co.uk) → Product page → Pricing → Account (magic-link sign-in)
→ Download → Install → Activate → First library scan → Find Similar / Visual Map → Return use
```

Every step through "Account" is live today. Download/install/activate depends on the still-
unresolved signing/notarization blocker (`docs/PRIVATE_BETA_EXECUTION.md`) — this plan doesn't
change that dependency, just documents the funnel around it.

## Launch calendar (relative structure, no fabricated date)

```
T-30   Signed/notarized build exists; clean-Mac acceptance passes (external gate)
T-14   Real product screenshots/video captured from the actual signed build
T-7    Website copy final pass against the real build; pricing page reflects live checkout
       state (only once Paddle sandbox is validated -- docs/PADDLE_INTEGRATION_AUDIT.md if
       that exists, or the commerce docs the parallel pricing work produces)
T-3    Launch content drafted (see below), held for approval
T-1    Final smoke test of the full funnel end-to-end
LAUNCH Public announcement, checkout live (only after explicit human go-live approval --
       standing rule from every prior phase of this program)
T+7    First real usage/conversion data reviewed
T+30   Regular price (£10) takes effect, ending the introductory period
```

No specific calendar date is set here, per Section 56's explicit instruction not to fabricate
one. Substitute real dates once the external blockers (signing, clean Mac, Paddle) clear.

## Draft content (drafts only — none of this is published; needs explicit approval)

- **Launch announcement**: "NITE DSP is live. Smart Sample Manager finds the sounds already on
  your drive — introductory price £5, one-time, for the first month."
- **Find Similar demo concept** (15-30s, once real product video exists per the UX pass's
  deferred Phase D): select a kick → Find Similar → three alternates appear → drag one into a
  DAW timeline.
- **Visual Map demo concept**: open the map on a populated library, pan/zoom to show clustering,
  click a point to preview.
- **Launch email** (to the private beta list, once one exists): same core message as the
  announcement, plus a direct account/download link.

None of this is scheduled or sent — Section 84/85's explicit "draft only unless publishing
permission exists" rule applies throughout.

## Creator outreach (ethical, no spam)

Target: small/independent audio-production content creators and plugin reviewers who cover
sample-management or organization workflows specifically, not a mass list. Process: identify a
short list (search music-production YouTube/newsletter creators covering this space genuinely
covering sample tools), manually check that Smart Sample Manager is a genuine fit before any
outreach, offer a real review copy with no positive-review requirement, track status (contacted/
responded/reviewed) in a simple internal list — not built this pass, a spreadsheet or the
marketing agent's future memory (see `docs/MARKETING_AGENT_AUDIT.md`) is sufficient, no new
infrastructure needed for this scale.

## No fake social proof (standing rule, restated for this doc)

No star ratings, no invented user counts, no fabricated testimonials or creator quotes, no fake
logos, until real ones exist with real permission.

## What this plan deliberately does not include

A specific launch date, real screenshots/video (Phase D was deferred in the prior UX session and
remains deferred here), a live Paddle-validated checkout flow (the parallel commercial-config
work covers this), and any analytics implementation (see `docs/LAUNCH_ANALYTICS_PLAN.md`).
