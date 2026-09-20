# Public Launch Checklist

Phase 6, Section 107. One authoritative gate list for public paid release. Re-evaluate this
document, don't recreate it, as work proceeds.

## PRODUCT

- [x] native regression suite PASS (12/12, zero leaks -- reconfirmed this phase)
- [x] zero release-blocking crashes known
- [x] async lifetime fixes preserved (Phase 2, untouched since)
- [ ] project recall PASS -- needs a real DAW + signed build, not yet possible
- [ ] realistic large-library workflow PASS under real customer conditions -- exercised via
      test fixtures, not a genuinely large real-world library

## PACKAGING

- [x] fresh Release build (reconfirmed this phase, not stale)
- [x] recursive dependency bundling PASS (Phase 5.5's fix, reconfirmed all 3 formats)
- [x] zero forbidden Homebrew dependencies (reconfirmed this phase)
- [x] release manifest PASS (all 3 formats, both build trees)
- [x] third-party notices included (Phase 2)
- [x] secret scan PASS (reconfirmed this phase, all bundled Mach-O binaries)

## IDENTITY

- [x] NITE DSP identity locked (`docs/FINAL_PRODUCT_IDENTITY.md`)
- [x] Smart Sample Manager product identity locked
- [x] identity regression guard enforced in CI
- [x] COMPANY_WEBSITE/COMPANY_EMAIL applied (Phase 5.6)

## DOMAIN & HOSTING

- [x] domain known and applied in code (`nitedsp.co.uk`)
- [x] company contact applied in code (`nitedsp@outlook.com`)
- [ ] Railway project created -- BLOCKED EXTERNAL, no account
- [ ] IONOS DNS records configured -- BLOCKED, chained on Railway
- [ ] HTTPS verified on real domains -- BLOCKED, chained on hosting
- [ ] hosted backend reachable -- BLOCKED, chained on hosting
- [ ] hosted database initialized via migration -- BLOCKED, chained on hosting (migration
      mechanism itself verified locally, Phase 5-6)

## SIGNING & NOTARIZATION

- [ ] Apple Developer Program membership -- BLOCKED EXTERNAL
- [ ] Developer ID Application certificate -- BLOCKED, chained on membership
- [ ] code signing performed -- BLOCKED
- [ ] notarization passed -- BLOCKED
- [ ] Gatekeeper validated -- BLOCKED

## CLEAN MACHINE

- [ ] genuine clean-machine test passed -- BLOCKED EXTERNAL, no clean machine
- [x] test procedure ready for someone unfamiliar with the codebase (Phase 5.6, strengthened)
- [x] non-destructive acceptance script verified standalone-portable (Phase 5.6)

## DAW VALIDATION

- [ ] Ableton Live tested -- BLOCKED, needs signed build + real/clean machine
- [ ] Logic Pro (AU) tested -- BLOCKED, same
- [ ] Reaper/Bitwig/Studio One/Cubase tested -- not attempted, lower priority per Section 66

## COMMERCE

- [x] commerce code complete and unit-tested against simulated payloads
- [x] webhook idempotency concurrency-safe (Phase 5.5 fix, reconfirmed)
- [ ] real Paddle sandbox validated -- BLOCKED EXTERNAL, no account (`docs/PADDLE_PRODUCTION.md`)
- [ ] refund sandbox validated -- BLOCKED, chained on sandbox
- [ ] live Paddle enabled -- explicitly NOT READY, see `docs/LIVE_COMMERCE_GO_NO_GO.md` (NO-GO)

## PRICING & LEGAL

- [ ] launch price approved -- NOT READY, flagged "HUMAN PRICING APPROVAL REQUIRED" on the
      pricing page itself
- [ ] Privacy Policy professionally reviewed -- NOT READY
- [ ] Terms professionally reviewed -- NOT READY
- [ ] EULA professionally reviewed -- NOT READY
- [ ] Refund Policy professionally reviewed -- NOT READY
- [ ] JUCE commercial license resolved -- NOT READY, unresolved business decision
- [ ] trademark clearance checked -- NOT READY, not performed

## EMAIL

- [x] real company contact address applied (`nitedsp@outlook.com`)
- [ ] transactional email provider configured -- BLOCKED EXTERNAL, no account
      (`docs/PRODUCTION_EMAIL.md`)
- [ ] SPF/DKIM/DMARC verified -- BLOCKED, chained on provider + DNS access

## WEBSITE

- [x] production build passes, zero secrets, zero application-level localhost references
- [x] design system in place, homepage/product/pricing/support pages built out
- [x] accessibility basics (skip link, focus states, labels, reduced motion)
- [x] SEO basics (canonical URLs, Open Graph, sitemap, robots)
- [x] zero placeholder/dev text, zero WIP-product exposure (scanned this phase)
- [ ] real product screenshots -- not available; current pages use text/icon treatment
      honestly rather than fabricated UI mockups (Section 28)
- [ ] live on the real domain -- BLOCKED, chained on hosting

## TRIAL

- [ ] trial system implemented -- NOT BUILT, `docs/PUBLIC_TRIAL_VALIDATION.md`
- [ ] public trial journey validated -- BLOCKED, chained on implementation

## OPERATIONS

- [x] backup/restore rehearsed against real local Postgres (Phase 5)
- [ ] backup/restore rehearsed against hosted Postgres -- BLOCKED, chained on hosting
- [x] /health and /ready endpoints correct through a real DB outage
- [ ] production monitoring configured -- BLOCKED, chained on hosting
- [x] admin authorization verified (anonymous denied, customer denied, admin allowed)
- [x] log privacy -- no secrets found in any log inspected this session (console-provider email
      logs, uvicorn logs)

## GO/NO-GO

**Overall: NO-GO for public paid launch.** See `docs/LIVE_COMMERCE_GO_NO_GO.md` for the formal
report. The website could reasonably go live before payments (Section 98) once hosting exists,
with pricing/trial/buy CTAs presented honestly as "coming soon" rather than live commerce --
that decision is yours, not made here.
