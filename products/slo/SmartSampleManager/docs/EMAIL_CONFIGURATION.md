# Email Configuration

## Status: PARTIALLY RESOLVED — nitedsp@outlook.com is a real, owned contact address

Phase 5.6: Jack supplied `nitedsp@outlook.com` as the approved current company/support email.
This is real and applied everywhere a customer-facing contact address belongs. It is explicitly
**not** the same as a verified transactional-email-sending setup -- keeping these distinct is
Phase 5.6's own Section 2 instruction, not an editorial choice.

## Two different things, still not conflated

1. **COMPANY CONTACT EMAIL** -- `nitedsp@outlook.com`. **RESOLVED.** A real mailbox someone
   reads. Fine for a human to see and reply to.
2. **TRANSACTIONAL EMAIL SENDER** -- an authenticated system that sends magic links, purchase
   confirmations, etc. automatically. **STILL BLOCKED.** Outlook is not assumed to be able to
   act as this without a real provider account and DNS control for `nitedsp.co.uk`
   (SPF/DKIM/DMARC -- unchanged from Phase 5's `docs/EMAIL_DOMAIN_CONFIGURATION.md`).
   `EMAIL_PROVIDER` stays `"console"` -- the backend does not attempt to send real mail through
   this address.

## Where the contact address is applied

- `nitedsp/website/lib/legal.tsx` -- shared contact line on every legal page (privacy, terms,
  eula, refund-policy)
- `nitedsp/website/app/layout.tsx` -- footer
- `nitedsp/website/app/account/page.tsx` -- "Need help?" contact line
- `nitedsp/backend/.env.production.example` -- `NITE_DSP_SUPPORT_EMAIL`, `EMAIL_FROM_ADDRESS`
- `CMakeLists.txt` -- `COMPANY_EMAIL "nitedsp@outlook.com"` (plugin metadata, cosmetic only)

**Deliberately not created**: `support@nitedsp.co.uk`, `hello@nitedsp.co.uk`,
`billing@nitedsp.co.uk`, or any other domain-based address -- per Section 3's explicit
instruction, none of these actually exist. The architecture (a single `NITE_DSP_SUPPORT_EMAIL`
setting, consumed everywhere via `settings.*`) already supports swapping in a domain-based
address later with a one-line config change, no code change.

## Verified this phase

`_validate_production_config` accepts `nitedsp@outlook.com` as a valid production
`NITE_DSP_SUPPORT_EMAIL`/`EMAIL_FROM_ADDRESS` (no longer rejected as the `@localhost.invalid`
dev placeholder).

---

## Historical record: Phase 5.5's original report (superseded above)

Same situation as `docs/DOMAIN_CONFIGURATION.md`'s history -- Phase 5.5 found no real address
anywhere and correctly reported `EMAIL VALUE REQUIRED` rather than inventing one. Phase 5.6
supplied the real value directly.
