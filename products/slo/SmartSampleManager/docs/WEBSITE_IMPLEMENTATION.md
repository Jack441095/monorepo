# Website Implementation

Phase 4 Milestone E. Implementation: `nitedsp/website/` -- Next.js 16 (App Router) + TypeScript
+ Tailwind, per `docs/PHASE_4_PLAN.md`'s stack decision. Calls the FastAPI backend via
`NEXT_PUBLIC_NITE_DSP_API_URL` (defaults to `http://localhost:8420`, env-driven, same
no-hardcoded-domain rule as the backend's `config.py`).

## Pages

- `/` -- homepage
- `/products/smart-sample-manager` -- product page
- `/pricing` -- £59 launch / £79 regular perpetual license, matches
  `docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`'s pricing; explicitly notes checkout isn't live
- `/account` -- client component: magic-link request/verify against the real backend, session
  state via `/auth/me`, entitlement list via `/auth/entitlements`, sign-out
- `/auth/verify` -- reads the `?token=` query param, POSTs it to the backend, redirects to
  `/account` on success
- `/privacy`, `/terms`, `/eula`, `/refund-policy` -- structural placeholders, each carrying a
  visible "PROFESSIONAL REVIEW REQUIRED" banner (`lib/legal.tsx`'s shared `LegalPage` component),
  per Section 65's requirement that these not be presented as final legal text

## CORS

The website (`localhost:3000`) and API (`localhost:8420`) are separate origins in local staging.
`main.py` adds `CORSMiddleware` with an explicit single-origin allow-list
(`settings.nite_dsp_public_url`) and `allow_credentials=True` -- never a wildcard origin, since
credentialed (cookie-bearing) cross-origin requests require one.

## Verified this session

`npx tsc --noEmit` clean. `npm run build` succeeds -- all 9 routes compile and prerender as
static content. Production server started locally; all 8 user-facing routes return HTTP 200.
CORS preflight (`OPTIONS`) and an actual `Origin: http://localhost:3000` request against
`/auth/request-link` both succeed with the correct `Access-Control-Allow-*` headers, confirmed
via `curl`.

## Not done (correctly out of scope this phase)

No browser-automation (Playwright/Cypress) E2E run was performed -- the client-rendered
`/account` flow was verified by (a) confirming the pages build and render, and (b) exhaustively
testing the exact backend endpoints those pages call (`docs/AUTH_IMPLEMENTATION.md`), not by
driving an actual browser through the UI. Flagged rather than presented as full E2E coverage.
