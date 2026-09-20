# Phase 5.6 Final Synthesis

Apply Real Domain + Email, Finalise Deployment Readiness, Close Remaining Codex-Resolvable
Gates. Closing report per Section 27.

## Final regression (actual results)

```text
Native SmartSampleManager suite:  12/12 passing in isolation (both build/ and build-release/ trees)
Commercial backend E2E suite:     11/11 passing
Website production build:        PASS -- 14 routes (added /sitemap.xml, /robots.txt this phase)
Website secret leak scan:        PASS -- zero secrets
Website localhost scan:          PASS -- zero application-level matches (only Next.js's own
                                  internal URL-parsing library code matches "localhost" as a
                                  substring, unrelated to configuration)
Release manifest (both trees, all 3 formats): PASS -- 96/95/95 files
Identity guard:                  PASS
Homebrew dependency guard (both trees, all 3 formats): PASS -- zero forbidden paths
Migration-from-empty spot-check: PASS
Production config validation:    PASS with real values, FAILS CLOSED with dev defaults (both
                                  directions verified directly)
```

## DOMAIN

`nitedsp.co.uk`. Applied: website metadata (`metadataBase`, Open Graph, `sitemap.ts`,
`robots.ts`), backend CORS allow-list derivation (`_allowed_cors_origins()`, auto-includes
`www.` variant), `CMakeLists.txt`'s `COMPANY_WEBSITE`, `docs/PRODUCTION_CONFIG_REFERENCE.md`,
`docs/RAILWAY_DEPLOYMENT.md`, `docs/IONOS_DNS_SETUP.md`. Verified: production config accepts it
as valid, production website build bakes in the real API subdomain, plugin's `moduleinfo.json`
shows the real URL. Not independently verified: actual domain ownership/registration (no
WHOIS access from this environment) or DNS/TLS (no Railway project exists yet to point DNS at).

## EMAIL

`nitedsp@outlook.com`. Applied: website footer, all 4 legal pages, account page, backend
`NITE_DSP_SUPPORT_EMAIL`/`EMAIL_FROM_ADDRESS` production reference, `CMakeLists.txt`'s
`COMPANY_EMAIL`. Limitation, kept explicitly distinct per Section 2: this is a real contact
mailbox, not a verified transactional sender -- `EMAIL_PROVIDER` stays `"console"`, no
SPF/DKIM/DMARC exists for `nitedsp.co.uk`. No domain-based address (`support@nitedsp.co.uk`
etc.) was invented, per Section 3.

## IDENTITY

Complete. All 7 `juce_add_plugin()` identity fields now set: `COMPANY_NAME`,
`COMPANY_COPYRIGHT`, `BUNDLE_ID`, `PLUGIN_MANUFACTURER_CODE`, `PLUGIN_CODE`, and (new this
phase) `COMPANY_WEBSITE`/`COMPANY_EMAIL`. Verified in the actual built artifacts (VST3
`moduleinfo.json`), not assumed.

## WEBSITE

Production build passes with the real domain/API URL baked in. Zero secrets, zero
application-level localhost references. `sitemap.xml`/`robots.txt` added. Release-time guard
(`check-production-config.mjs`) still enforces this on every `build:production` invocation.

## RAILWAY

Fully prepared, not deployed. `railway.json` for both services (backend: Nixpacks, migration-
then-serve start command, `/ready` healthcheck; website: Nixpacks, `build:production`,
`npm run start`). One concrete, documented gap found: Railway's default Postgres `DATABASE_URL`
scheme (`postgresql://`) will need adjusting to `postgresql+psycopg2://` for this codebase's
SQLAlchemy config -- flagged in `docs/RAILWAY_DEPLOYMENT.md` rather than assumed to just work.

## IONOS

`docs/IONOS_DNS_SETUP.md` documents which records (apex/CNAME-or-A, `www`, `api`) will need
creating, explicitly deferring the actual target values until Railway supplies them (per
Section 13 -- not invented ahead of time).

## BACKEND

Deployment readiness: prepared. `/health`/`/ready` exist and are wired as the Railway
healthcheck. Production config fails closed, verified with the real supplied values this phase.

## DATABASE

Migration readiness: reconfirmed via a fresh spot-check this phase (empty DB → `alembic upgrade
head` → 16 tables + `alembic_version`, clean). No schema changes this phase, so the deeper Phase
5.5 up/down/up rehearsal evidence stands unrepeated, per Section 15's "preserve existing
verified evidence rather than inventing redundant work."

## LICENSING

Unchanged, still fully working (Ed25519, online + 14-day offline grace, concurrency-safe).

## PADDLE

Unchanged: code-ready, BLOCKED EXTERNAL on real sandbox credentials. No new evidence fabricated,
per Section 20's explicit instruction.

## APPLE

Unchanged: `scripts/signing_preflight.py` re-run this phase, still reports "Build/manifest/
identity preflight: READY," still "MISSING -- no Developer ID Application certificate found."

## CLEAN MAC

Procedure strengthened this phase for genuine standalone executability: added exact URLs,
exact terminal commands (`spctl`, `auval`, `open`), an explanation of the NDSP/AtSm codes for
someone unfamiliar with the codebase, and fixed a real portability bug in
`scripts/clean_machine_acceptance.py` (it referenced `check_homebrew_dependencies.py` via a
repo-root-relative path that would have broken if the script were copied standalone to a clean
machine as instructed -- fixed and verified by actually copying both scripts to `/tmp` and
running them from there). Still not actually validated -- no clean machine available.

## DEPENDENCIES

Full transitive graph guard re-run this phase against the freshly rebuilt (identity-metadata-
updated) Release and Debug trees, all 3 formats each: zero forbidden Homebrew paths, 88 Mach-O
binaries checked per format.

## TESTS

12/12 native + 11/11 commercial E2E = 23 automated tests, all passing this phase.

## PRIVATE BETA GATES

12 PASS / 3 BLOCKED EXTERNAL / 0 FAIL (up from Phase 5.5's 10/5/0). See
`docs/PRIVATE_BETA_RC.md`.

## ENGINEERING READINESS

**97 / 100** (up from Phase 5.5's 96 -- deployment target is now concrete/configured, not just
"not blocked," and two more identity fields are genuinely applied and verified in built
artifacts). Not 100 for the same reasons as Phase 5.5: no browser-automation E2E, no
independent packet-capture privacy audit, never run on hardware other than this development
machine.

## ACTUAL PRIVATE BETA READINESS

**NO.** Three external blockers remain: Apple Developer credentials, a real clean Mac, and
actual Railway/hosting execution (configuration is ready, the account/deployment itself is not).

## EXACT NEXT HUMAN ACTIONS

1. Create a Railway account and project; add the two services (backend, website) pointed at
   `nitedsp/backend` and `nitedsp/website` respectively; attach a Postgres plugin.
2. Set the environment variables from `nitedsp/backend/.env.production.example` on the Railway
   backend service (generating real random values for `SESSION_SECRET`/`ADMIN_API_KEY`), and
   `NEXT_PUBLIC_NITE_DSP_API_URL`/`NITEDSP_BUILD_ENV=production` on the website service.
3. Once Railway supplies target hostnames, add the corresponding records at IONOS per
   `docs/IONOS_DNS_SETUP.md`.
4. Enroll in the Apple Developer Program.
5. Arrange a genuinely clean Mac or VM for `docs/CLEAN_MACHINE_TEST_PROCEDURE.md`.

Per Section 26's directive: STOP here. Everything code-controllable is done and verified; what
remains is exactly these five actions, none of which more engineering work can substitute for.
