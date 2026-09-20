# Production Email

Phase 6, Section 19-20. Consolidates the transactional-email status already established in
`docs/EMAIL_CONFIGURATION.md` (Phase 5.6, the real contact address) and
`docs/EMAIL_DOMAIN_CONFIGURATION.md` (Phase 5, the SPF/DKIM/DMARC requirement) into one
production-facing status.

## Status: BLOCKED EXTERNAL -- no transactional provider account exists

`nitedsp@outlook.com` is a real, owned contact mailbox (Phase 5.6) -- it is not, and cannot
automatically become, a verified transactional sender. `EMAIL_PROVIDER` stays `"console"`.

## What's needed to close this out

1. **A transactional email provider account.** Prefer operational simplicity (Section 19) --
   Postmark, AWS SES, or Resend are all reasonable, all far simpler than self-hosting an SMTP
   server, which this document does not recommend. No provider has been selected or paid for.
2. **DNS control for `nitedsp.co.uk`** at IONOS to add the provider's required SPF/DKIM/DMARC
   records (`docs/IONOS_DNS_SETUP.md` covers the Railway-related records; these are additional,
   separate records the chosen provider will specify).
3. **A code change**, small and already scoped: `email.py`'s `send_email()` currently only
   implements `"console"` and raises `NotImplementedError` for anything else, by design (Phase
   4) -- adding a real provider means implementing one more branch there, not redesigning the
   function.

## What must NOT happen

Per Section 20: DNS verification is never marked PASS without the provider's own verification
actually succeeding. No SPF/DKIM/DMARC status is asserted here because none has been attempted.

## Required message templates (already written, Phase 5.5, ready to send once a provider exists)

Magic link, beta invitation, license ready, purchase confirmation -- all in
`nitedsp/backend/app/email_templates.py`, all currently delivered via the console provider only.
Two additional templates (`trial_started`, `new_sign_in_notice`) exist but have no triggering
code path yet (no trial-issuance endpoint, no session-tracking feature).
