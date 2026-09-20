# Hosted Staging Deployment

# HUMAN ACTION REQUIRED

```text
STATUS: BLOCKED -- no hosting account exists
OWNER:  You
BLOCKS: Sections 9-11, 45, 48-50 of the Phase 5 master prompt (real domain, TLS, hosted
        Postgres, hosted API/website, CORS/cookie behavior across real HTTPS origins)
REASON: See docs/HUMAN_COMMERCIAL_REQUIREMENTS.md -- "Production hosting account"
```

Everything in `docs/STAGING_DEPLOYMENT.md` runs on this development machine only, deliberately.
Moving it to a real hosted environment requires an account and payment method this environment
cannot create on your behalf (VPS/PaaS provider, managed Postgres).

## What's ready to deploy the moment hosting exists

The backend and website are already environment-variable-driven with no hardcoded domain
anywhere (`config.py`'s `Settings`, `lib/api.ts`'s `NEXT_PUBLIC_NITE_DSP_API_URL` -- see
`docs/NITE_DSP_BACKEND_IMPLEMENTATION.md`) -- deploying to a real host should require setting
environment variables and running `alembic upgrade head`, not code changes. This was a
deliberate Phase 4 design choice specifically to make this transition low-risk once hosting
exists.

## What can only be verified once hosting exists

- TLS-only transport (Section 11)
- Cookie `Secure`/`SameSite`/CSRF behavior across a real cross-origin HTTPS deployment
  (Section 49) -- `settings.environment == "production"` already gates `Secure` in
  `auth.py`, but this is unverified against a real browser/real HTTPS origin
- CORS behavior against the real production website origin (Section 48) -- currently a
  single-origin allow-list pointed at `localhost:3000`; must be repointed at the real origin
- Website metadata/canonical URLs/sitemap/robots under the real domain (Section 50)
