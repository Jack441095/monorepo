# Public Launch Master Plan

Phase 6. Consolidated plan from repository baseline (Phase 5.6, `docs/PHASE_5_6_FINAL_SYNTHESIS.md`)
through to public paid launch. This is the index document -- detail lives in the referenced
canonical docs, not duplicated here (Section 106).

## Sequence

```text
VERIFY            docs/PHASE_6_FINAL_SYNTHESIS.md's baseline regression (this phase)
  ↓
IMPLEMENT/POLISH  Website design pass, error-message sanitization (this phase)
  ↓
DEPLOY            docs/RAILWAY_DEPLOYMENT.md + docs/IONOS_DNS_SETUP.md -- BLOCKED EXTERNAL,
                   no Railway account exists
  ↓
VALIDATE          docs/MACOS_RELEASE_PIPELINE.md's signing→notarization→clean-machine chain --
                   BLOCKED EXTERNAL, no Apple credentials or clean machine
  ↓
BETA              docs/PRIVATE_BETA_RESULTS.md -- sequenced after VALIDATE, not started
  ↓
FIX EVIDENCE-BASED ISSUES   Depends on real beta findings -- none exist yet
  ↓
RELEASE CANDIDATE  docs/RELEASE_CANDIDATE_VALIDATION.md -- not cut
  ↓
HUMAN LAUNCH APPROVAL  docs/LIVE_COMMERCE_GO_NO_GO.md -- currently NO-GO
  ↓
PUBLIC RELEASE     Not started
```

## What Phase 6 actually did (code-controllable work)

- Fresh regression baseline (native 12/12, commercial E2E 11/11, all release/identity/dependency
  guards) -- confirmed still clean, no drift since Phase 5.6.
- Sanitized a webhook error response that leaked internal exception text to an external caller.
- A substantial website design pass: a real design system (tokens, typography, cards, buttons),
  a rebuilt homepage with an honest information hierarchy, a fully built-out product page with
  FAQ, a pricing page with an explicit "HUMAN PRICING APPROVAL REQUIRED" flag, a new `/support`
  page written for musicians, accessibility basics (skip link, focus-visible states, reduced
  motion, form labels), and a scan confirming zero placeholder/dev text and zero WIP-product
  exposure in the built output.
- The full launch documentation set (Section 106), each document reporting genuine status --
  several are explicitly "not started" or "BLOCKED EXTERNAL," not padded with speculative work.

## What Phase 6 did not do, and why

Nothing requiring Railway, Apple, Paddle, a clean machine, legal review, or a pricing decision
was attempted or fabricated. Per Section 3's "hard release philosophy": private-beta-ready is
not public-launch-ready, and code-complete is not production-validated. See
`docs/PHASE_6_FINAL_SYNTHESIS.md` for the full accounting and `docs/PUBLIC_LAUNCH_CHECKLIST.md`
for the master gate list.

## Continuing across sessions

State lives in this documentation set, not in conversation history. A future session should
read `docs/PHASE_6_FINAL_SYNTHESIS.md` first, verify it against actual repository/test state
(never trust a synthesis doc over the code), then continue from whichever `docs/PUBLIC_LAUNCH_CHECKLIST.md`
items remain unchecked.
