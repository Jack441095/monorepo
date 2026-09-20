# Domain Configuration

## Status: RESOLVED — nitedsp.co.uk

Phase 5.6: Jack supplied the approved production domain, `nitedsp.co.uk`, registered at IONOS.
This supersedes Phase 5.5's `DOMAIN VALUE REQUIRED` report (kept below for history, since Phase
5.5's finding -- that the Phase 5.5 prompt's claim of "sorted" didn't match repo reality -- was
itself correct and worth keeping as a record of how this was actually resolved: by the human
supplying the value directly in Phase 5.6's prompt, not by search).

## Where it's applied

- `nitedsp/backend/.env.production.example` -- `NITE_DSP_PUBLIC_URL=https://nitedsp.co.uk`,
  `NITE_DSP_API_URL=https://api.nitedsp.co.uk`
- `nitedsp/backend/app/main.py` -- CORS allow-list derived from `NITE_DSP_PUBLIC_URL`
  (`_allowed_cors_origins()`, also auto-includes the `www.` variant)
- `nitedsp/website/app/layout.tsx` -- `metadataBase`, Open Graph URL
- `nitedsp/website/app/sitemap.ts`, `app/robots.ts` -- both new this phase
- `CMakeLists.txt` -- `COMPANY_WEBSITE "https://nitedsp.co.uk"` (plugin metadata, cosmetic only)
- `docs/RAILWAY_DEPLOYMENT.md`, `docs/IONOS_DNS_SETUP.md` -- deployment topology

## Verified this phase

`_validate_production_config` accepts `NITE_DSP_PUBLIC_URL=https://nitedsp.co.uk` /
`NITE_DSP_API_URL=https://api.nitedsp.co.uk` as valid production values (no longer rejected as
localhost). A real production-configured website build
(`NEXT_PUBLIC_NITE_DSP_API_URL=https://api.nitedsp.co.uk npm run build:production`) succeeds and
bakes in the real API URL, confirmed by inspecting the built bundle.

## What's still not done (ownership/registration itself, and DNS)

This environment cannot independently verify domain registration/ownership (no WHOIS/registrar
access) -- the value is applied in code on the strength of Jack's explicit statement, consistent
with how every other credential in this project is handled. Real DNS records at IONOS still need
creating once a Railway project exists to supply target hostnames -- see
`docs/IONOS_DNS_SETUP.md`. TLS, real hosted reachability, and CORS/cookie behavior across the
real domain remain unverified until actual deployment happens.

---

## Historical record: Phase 5.5's original report (superseded above)

The Phase 5.5 master prompt claimed the domain was "sorted," but a repo-wide search found no
real domain value anywhere. Per that prompt's own Section 7 instruction not to fabricate one,
Phase 5.5 reported `DOMAIN VALUE REQUIRED` instead of guessing. That was the correct call --
Phase 5.6 subsequently supplied the real value directly, confirming the report was accurate
rather than overly cautious.
