# NITE DSP operations audit — 2026-10-08

## 2026-10-10 deployment update

Vercel production deployment `dpl_AwWdrveciMEwXAGZKQPXtU7f7e1A` now serves the
current website source. Its production build guard passed; `/pricing`,
`/privacy`, and `/terms` return HTTP 200. The privacy page no longer describes
NiteDSP as a sole trader, and pricing still has no checkout link. Production API
readiness remains healthy while checkout, legal approval, release readiness, and
commercial gates remain false. The registered company name, number, and office
address are still outstanding, so this deployment does not approve sales.

The platform responds in production, but public payment readiness has not been
proved. Website and backend checkout are disabled. The five old live Stripe
Payment Links were deactivated on 2026-10-08 after explicit owner approval;
their saved status was verified after reloading the dashboard. No new live
purchase was made during this audit.

The earlier £2 Submit purchase succeeded. On 2026-10-08, the live Stripe API
confirmed a paid GBP 200-pence session created on 2026-09-18. Its exact session
ID matches one completed backend purchase with one active licence and a sent
confirmation timestamp. A prior Resend API check recorded that purchase email
as delivered on 2026-09-18, outside the dashboard screenshot's last-15-days
window. The screenshot was captured at 14:10 BST, eight minutes before a
separate controlled sign-in message that Resend later reported as delivered at
14:18 BST. These records establish provider-reported delivery, not inbox
placement or that the dashboard and installed key belong to the same workspace.
Payment and fulfilment are verified; inbox placement and customer download
access are not.

This is the current platform checklist. Product engineering evidence remains in
each product's documentation; KENN's roadmap remains `products/kenn/KENN_PLAN.md`.
Checkboxes distinguish finished source work from outstanding deployed behavior.

## Product identity

| Public name | Current scope | Stable internal identity |
| --- | --- | --- |
| Submit | Local macOS document preparation; beta, paid launch gated | `nite-submit` |
| SLO (Sample Library Optimizer) | Local sample discovery; release delivery not approved | `smart-sample-manager` |
| Para-phase | Free online writing aid with a daily quota; production engine disabled | `nite-paraphrase` |
| KENN | Research and development; no sale or price promised | `kenn` |

The owner confirmed these names on 2026-10-08. Current website copy follows them.
Para-phase payment prompts and the unused donation component were removed. Its
new paid Checkout route and £1/£3/£10 price settings are now removed as well.
The historical webhook and redemption path remain so old paid orders and
previously issued unlock tokens keep working during their normal lifetimes.
The internal catalog ID remains stable for those historical payments.
Thursday is internal infrastructure. Audio_Too remains a studio workspace.

## Verified infrastructure

| Area | Observed state | What this proves |
| --- | --- | --- |
| Website | Patched Vercel production deployment responds over HTTPS | New product labels and closed checkout verified on the live domain |
| API | Fly.io, two Amsterdam machines, shared CPU, 256 MB each, auto-stop/start | Current API hosting; no global rate-limit or failover proof |
| Account/commerce DB | PostgreSQL attached to backend; Alembic head `f9c2d4e6a8b1` | Schema is current at audit time |
| Waitlist DB | Separate website Neon integration; Vercel database secret configured | Separate storage path; sign-up and retention need customer checks |
| Releases | S3-compatible Cloudflare R2; readiness reports durable storage | Storage configuration, not clean-machine release acceptance |
| Email | Resend replacement sending key installed; dashboard access confirmed | A controlled message was provider-reported delivered at 14:18 BST; confirm inbox placement and that dashboard/API key use the same workspace |
| DNS/mail | IONOS MX; public root SPF, `send` SPF/MX, Resend DKIM selector, and DMARC `p=none` records resolve | Records are published; message alignment, provider verification, and bounce handling remain unverified |
| Stripe | Live dashboard/API accessible; earlier £2 Submit payment matched to fulfilment | Payment and one active licence verified; related email delivery remains unverified |

API `/health` and `/ready` returned HTTP 200. Readiness reports database, durable
storage, and deliverable email configuration true. Checkout, legal approval,
release readiness, and customer rehearsal flags are false in production.
Readiness alone is not permission to open sales.

After this snapshot, the Fly `NITE_DSP_SUPPORT_EMAIL` secret was set to the
owner-confirmed `nitedsp@outlook.com`. A remote runtime comparison confirmed
the value without printing it. Both Fly machines completed the rolling update;
production `/health` and `/ready` again returned HTTP 200, with checkout still
disabled.

A fresh read-only check on 2026-10-08 returned `/ready` HTTP 200 with database,
storage, and email checks true; checkout, legal approval, and release readiness
remain false. Fly reports one 256 MB machine started and one stopped under the
configured auto-stop policy; the stopped machine's service check is warning,
while the started machine passes. This confirms the current autostart setup, not
two-machine availability or memory headroom. DNS lookups returned no A or AAAA
answers for `staging.nitedsp.co.uk` or `api-staging.nitedsp.co.uk`.

The observed production catalog has Submit and SLO marked purchasable. Only a
Submit 1.0.0 macOS arm64 stable release is registered. SLO has no registered
production release. The Submit descriptor signature field is empty; that does
not establish whether the application binary is signed or notarized.

At the audit snapshot, the stored purchase backlog had no unsent confirmation
emails and no failed webhook records. Those counts can change after the audit.
No private database host, credential, purchaser address, or signed URL is saved
in this report.

The database runs on one unmanaged Postgres Flex 18.1 machine with 256 MiB of
memory; no Fly Managed Postgres cluster exists in the account. Its encrypted
volume has six automatic snapshots with five-day retention, totalling 138 MiB;
the newest was 16 hours old at 16:05 UTC on 2026-10-08. Fly's PostgreSQL backup
commands report WAL backups disabled. I left that setting unchanged: enabling
it creates a Tigris bucket and changes the production database's backup path,
while the current database has only 256 MiB. Fly's July 2024 WAL-archive
[guidance](https://community.fly.io/t/fresh-produce-enhanced-wal-archiving-and-remote-restores/20827)
lists 512 MiB as the minimum, and Fly's [current pricing docs](https://docs.fly.io/about/pricing)
classify unmanaged Postgres as unsupported. A [2025 community incident](https://community.fly.io/t/database-stuck-as-replica-after-fly-postgres-backup-enable-on-legacy-postgres-app/25487)
reports a production cluster failing after backup enable; that report does not
prove the same failure would occur here, but it reinforces the need to avoid an
untested production change. Volume snapshots still do not provide continuous
recovery or prove that a production restore works. Fly Managed Postgres starts
at $38/month plus storage ([pricing](https://docs.fly.io/postgres)), so no
database migration or recurring-cost change was made without the owner's
choice.

## Launch blockers — complete before paid sales

- [x] **Operations: verify the earlier £2 Submit payment and fulfilment.**
  Matched the paid Stripe session to its completed production purchase, one
  active licence, and confirmation timestamp. The historical confirmation's
  provider delivery event was not verified. A separate controlled sign-in email
  was reported delivered by Resend at 14:18 BST; the owner's screenshot was
  captured at 14:10 BST and predates that probe. No extra live charge or resend
  was needed to verify the payment and fulfilment.
- [x] **Operations: pause the five old live Payment Links.** After owner approval,
  deactivated Submit £2, the old “Smart Sample Manager” £9 link, and three old
  Para-phase support links (£1, £3, £10). All five saved statuses read
  “Deactivated” after a dashboard reload. The earlier Submit £3 link was already
  deactivated. These links can be reactivated when their launch checks pass.
- [ ] **Operations: complete the isolated Sandbox customer journey.** The
  owner completed a £2 GBP Stripe Sandbox checkout for NITE Submit on
  2026-10-10 (`livemode=false`). Stripe reported the session paid; its matching
  signed `checkout.session.completed` event reached the local listener with
  HTTP 200. The isolated checkout-rehearsal database contains one completed
  purchase and one active entitlement. The local mailer is console-only, so
  inbox delivery, sign-in, release download, and duplicate-event delivery still
  need proof. The local `backend/tests/test_e2e.py` suite passes all 10 tests,
  including purchase-to-activation, duplicate webhook idempotency, download
  authorization, and refund revocation. This proves local Sandbox payment and
  fulfilment, not a hosted customer journey. Its webhook is signed locally, and
  its mail delivery is not sent through Resend. On 2026-10-08 the saved Submit
  Checkout session was open and unpaid for £2 GBP; a read-only retrieval
  on 2026-10-10 shows it expired without payment. The saved test key can read
  that session and its line item, but Stripe returns HTTP 403 when it lists
  active prices or hosted webhook endpoints. The successful checkout used a
  local Stripe CLI listener; it does not verify a hosted Sandbox endpoint or
  customer inbox delivery. The focused commerce/catalog, production-config,
  and webhook-robustness suites also pass (66 tests).
- [ ] **Operations: establish durable public staging.** The local rehearsal is
  isolated, but does not prove an external browser can complete the full journey.
  Public tunnel attempts failed to connect and were stopped. Current DNS checks
  also return no A or AAAA answers for `staging.nitedsp.co.uk` or
  `api-staging.nitedsp.co.uk`. Use a maintained staging API and website with
  separate test keys and database.
- [ ] **Operations: bring the free Para-phase engine online.** Production
  `PARAPHRASE_ENABLED` is false. Verify the engine's hosting, service authentication,
  streaming, cancellation, privacy behavior, and daily quota before enabling it.
  The website form defaults closed through `NEXT_PUBLIC_PARAPHRASE_ENABLED` and
  states that public rewriting is not available yet; free pricing does not imply
  that a working production engine is deployed.
- [ ] **Release owner: register and accept the SLO artifact before sale.** Verify
  object checksum, supported architectures, licence activation, signing and
  notarization where required, and install/launch on a clean Mac. Repeat the
  applicable checks for the exact Submit artifact offered to customers.
- [x] **Operations: archive legacy live Stripe products.** In the live
  dashboard, archived Smart Sample Manager (£9), Paraphrase Support (three
  prices), and the already-inactive Submit (£3) catalog rows. All three now
  appear under Archived. The old public Payment Links remain deactivated.
- [ ] **Owner + operations: verify Stripe product/price/metadata mapping.** The
  archived Submit row is £3, while the earlier successful live purchase and
  current public copy use £2; no current SLO product is ready to sell. Create
  and verify the intended Submit and SLO products/prices and their Payment Link
  metadata only after release and legal approval; keep Para-phase free. The
  old £2 Submit and £9 SLO Payment Links are deactivated; their dashboard
  metadata maps to `nite-submit` and `smart-sample-manager`, respectively, but
  the catalog products are archived. The live Stripe catalogue currently has
  zero active products. Their URLs have been removed from source;
  production checkout now also requires replacement Stripe-hosted URLs in
  Vercel. The fail-closed website build deployed on 2026-10-10; both apex and
  `www` pricing pages return HTTP 200, show beta access, and contain neither
  deactivated Payment Link. A live
  Checkout Session read returned three records: one paid and two expired, with
  no open sessions. The restricted key cannot read prices, Payment Links, or
  the Stripe account object (HTTP 403). Sandbox cleanup deactivated seven old
  Paraphrase Support Payment Links, their three £1/£3/£10 prices, and the
  product; every saved object reported `livemode=false`.
  The live API-key inventory shows the configured `NITE DSP backend checkout`
  key has only Checkout Sessions write permission. A second active key,
  `key_01`, has 138 permissions (46 read and 92 write), including broad account,
  catalog, payment, and payout permissions. Its visible activity includes two
  successful Payment Link creation calls on 2026-09-18; the legacy links are
  deactivated. Owner action: expire `key_01` after confirming no other service
  still uses it.
  The Stripe dashboard confirms Starling Bank Ltd is the default GBP payout
  destination; account digits are intentionally omitted. Receipt/support
  information still needs review. On 2026-10-10, successful-payment and refund
  emails were enabled, and public support replies were changed to the business
  support inbox. The public-details editor had prefilled the support address
  from the account address; that address was cleared before saving, so the
  private address is not exposed on receipts. Add a customer-facing address only
  after confirming the registered office. The 2026-10-10 account-status view
  lists Payments and Payouts as active with no open verification tasks; the app's
  closed legal, release, and checkout gates still prevent storefront sales.
- [ ] **Owner/legal reviewer: approve accurate terms, privacy, and refund copy.**
  The owner supplied `Nite-DSP` as the registered name and confirmed the
  operator is a UK limited company. An [official Companies House search for
  Nite-DSP](https://find-and-update.company-information.service.gov.uk/search/companies?q=Nite-DSP)
  returned no results; the company number and registered office are also still
  missing, so the legal entity needs independent confirmation before approval.
  The 2026-10-10 production privacy page check confirms the old
  sole-trader, nurture-sequence, and fixed-retention claims are gone. It now
  names the website, waitlist, backend, release-storage, payment, and email
  providers; describes Submit and SLO as local products; and identifies
  Para-phase as an online service that is disabled and KENN as research and
  development. The page still leaves company particulars, provider regions and
  data transfers, and retention procedures unresolved. Its analytics claims
  also need review against the actual Plausible configuration.
  The deployed refund policy promises a full refund within 14 days and says a
  refund revokes the licence. The current source now revokes active entitlements
  on a full-refund webhook and records the action. Production now runs that
  change, and a signed synthetic webhook smoke check passed; a real Stripe event
  delivery and refund still need operational validation. Para-phase
  is an online text service: when enabled, the website sends text to the backend,
  which streams it to a separately configured engine. Verify that engine's
  provider, location, logging, and retention before enabling it. Confirm the
  actual regions, transfers, lawful bases, retention/deletion practice,
  analytics behavior, and email workflow with the reviewer.
  The privacy corrections are deployed, but exact registered particulars and
  legal review remain outstanding.
  Keep legal approval disabled until the registered company particulars and
  reviewed policy are complete.
- [ ] **Owner: approve go-live only after evidence is attached.** Backend and
  website legal/release/checkout flags must agree. Do not enable them merely
  because the services or payment dashboard are reachable.

## Maintenance already started

- [x] **Source: retire Railway.** Removed root, backend, and website Railway
  configs and obsolete deployment guidance. Current hosting comments use the
  verified platform. The two Thursday infrastructure helpers, including
  Audio_Too's copy, now point to this audit. Submit draft emails use the public
  name and read the relocated product truth sheet; its contact now uses the
  owner-confirmed public email. Funding/research references use the same path.
  A scoped scan found no active Paddle/Railway references in the backend,
  website app/dependencies, or Audio_Too runtime. Historical reports and
  migration lineage retain those names for provenance. The current Submit
  readiness prompt now names Stripe, and Audio_Too's redaction test covers the
  Resend key instead of a retired Paddle key.
- [x] **Production operations: remove retired Paddle secrets.** After confirming
  no active backend runtime reference remained, removed the six unused Paddle
  variables from Fly production. A name-only Fly secret listing confirmed all
  six are gone. The API later reported readiness `ok` with database, storage,
  and email configured; checkout remains disabled.
- [ ] **Fly memory headroom: review an observed OOM.** At 15:29 UTC, kernel logs
  reported an OOM kill of Uvicorn during a one-off SSH Python probe. The timing
  overlaps the probe, so its cause is unconfirmed. The probe was stopped. After
  the 2026-10-08 deployment, production `/health` and `/ready` returned HTTP
  200. The latest Fly CLI snapshot shows one 256 MB machine started and one
  256 MB machine stopped. The started machine's service check is passing and the
  stopped machine reports “the machine hasn't started”; public `/health` and
  `/ready` both return HTTP 200. The running machine's event history records a
  requested stop with `oom_killed=false` before it auto-started on traffic. The
  Prometheus query returned 401 during organization lookup, so no memory trend
  was verified. This confirms the configured autostart path, not memory
  headroom. Inspect platform metrics or schedule a supervised memory review
  before increasing workloads.
- [x] **Source: retire duplicated commerce plans.** Removed the old website
  commerce reports and SLO-hosted platform phase/deployment/launch plans. Kept
  migration history and product engineering evidence. The SLO documentation
  index identifies dated reports as historical rather than current instructions.
- [x] **Source: prevent credentials entering backend build contexts.** Root and
  backend Docker ignore files exclude dotenv files, admin/staging credential
  folders, private/key/PEM files, virtual environments, and generated state.
  Credential files used for operations are ignored and stored with mode 600;
  active ignored `.env` files under `Audio_Too/` and `products/kenn/` were also
  changed from mode 644 to 600.
- [x] **Source: suppress Uvicorn access logs in the container command.** Existing
  application logs retain status and latency without URL query strings; default
  access logs would duplicate magic-link/download tokens into provider logs.
  The 2026-10-08 Fly deployment runs this command.
- [x] **Source: guard actual Vercel production builds.** The website now recognizes
  `VERCEL_ENV=production` as well as the explicit build flag. Local builds and
  previews remain separate. Six regression cases passed; removing the Vercel
  guard made the required rejection test fail.
- [x] **Vercel configuration: persist production build settings.** Production
  now has the API URL and explicit Stripe live-mode label, with checkout, legal,
  and release flags set to zero. The existing private database secret was not
  replaced with the CLI's sensitive-value placeholder.
- [x] **Source: patch production website dependencies.** Next.js and its existing
  ESLint configuration moved from 16.3.5 to 16.3.8; compatible sharp and
  source-map-js lockfile entries were updated. Production dependency audit now
  reports zero vulnerabilities. No new direct dependency was added.
- [x] **Deployment: publish and verify the patched website.** Vercel production
  deployment `dpl_2APhxtFUvwaSZ4WZPNR75jr6Gjfc` built successfully and was promoted
  after checks against its protected URL. Both public hosts respond with HTTP
  200 and HSTS; the content security policy no longer permits Paddle. Browser
  checks confirm Submit, SLO, free Para-phase, and KENN research/development.
  Para-phase shows its service-preparation notice and no payment prompt. Pricing
  has no active purchase link; backend checkout/legal/release flags remain false.
  Previous deployment for rollback: `dpl_3N4mWhQbso5RbraBmJ1JcnaBRgsa`.
- [x] **Deployment verification: remove temporary bypass access.** Vercel's CLI
  automatically created an automation bypass token for the protected candidate
  check. That exact token was revoked afterward; the project now reports zero
  bypass tokens. Existing SSO and Git-fork protection settings are unchanged.
- [x] **Recovery rehearsal: verify dump/restore semantics.** A disposable local
  PostgreSQL cluster migrated to head, seeded synthetic paid commerce state,
  dumped/restored it, and checked seven table counts. Paid purchase/licence/device
  relationships, pending confirmation delivery, payment intent, and a failed
  webhook's retry state survived. The disposable cluster was removed afterward.

## Remaining operational checklist

- [x] **Email delivery probe:** the controlled 2026-10-08 sign-in email has a
  Resend event record with `last_event=delivered` at 14:18 BST. The owner’s
  screenshot was taken at 14:10 BST, eight minutes before this message was sent,
  so its empty view predates the probe. This verifies provider-reported delivery,
  not inbox placement.
- [ ] **Email operations:** confirm the probe is visible in the inbox or junk
  folder, then verify the dashboard and installed API key use the same Resend
  workspace. `/ready` reports
  `email_deliverable=true` from key presence alone, not from a send probe.
  Public DNS answers show root SPF, `send` SPF/MX, the Resend DKIM selector,
  and DMARC `p=none`; actual message alignment, provider verification, and
  bounce handling remain unverified. Keep the current DMARC policy. Revocation
  of the old exposed Resend key remains unconfirmed: its API returned 403 for
  the revoke attempt. The production replacement key works; local rehearsal
  copies use it. The October 8 rehearsal files were removed after a command
  accidentally printed fragments of ignored JSON, including local signing and
  session material. A process check after the paid Sandbox checkout found no
  Stripe CLI listener and no service on ports 8765 or 8766. The exposed local
  signing value could not be compared with Fly's stored production signer;
  verify its provenance through the secret manager before issuing more
  production licences. Do not rotate the production signer until the client
  trust-key lifecycle is ready, because an immediate change can invalidate
  existing licence signatures.
- [x] **Stripe webhook secret rotation:** the live signing secret was exposed
  in the conversation and replaced on 2026-10-10 using the hidden-input
  credential wizard. The replacement is stored only in the ignored,
  mode-600 `backend/admin/.env.operations-stripe-webhook-replacement` file and
  was installed in Fly. The wizard's signed synthetic `account.updated` check
  passed against production, where the event is ignored without creating a
  purchase or charge; its final completion also followed the owner's
  confirmation that the previous secret was expired. The secret value is not
  recorded here.
  A live-dashboard check on 2026-10-10 confirms the active destination is
  `https://api.nitedsp.co.uk/webhooks/stripe` with four events. The separate
  Stripe sandbox has its own account context; rotate the live destination shown
  above, not a sandbox endpoint. The live Stripe event list confirms the 18 Sep
  £2 Submit Checkout Session completed with `livemode=true` and
  `payment_status=paid`.
  Its detail says Stripe sent it to the active endpoint, but the full delivery
  attempt record has aged out. The endpoint overview currently shows zero
  deliveries this week, and its Event deliveries view is empty. Stripe still
  offers a replay of that event during its 30-day window. Replaying it would
  send the original checkout payload, including buyer contact details, to the
  production API; it has not been replayed. After the 2026-10-10 backend
  deployment, a fresh signed `account.updated` event returned HTTP 200 with
  status `ignored`, confirming production accepts the replacement
  signer without creating a purchase or charge.
  Stripe's sandbox dashboard shows the restricted `NITE DSP checkout rehearsal`
  key has only `Checkout Sessions: Write` and was used on 2026-10-10. It cannot
  list hosted sandbox webhook endpoints (HTTP 403), so hosted test-mode routing
  remains unverified. A local Stripe CLI listener did receive and fulfil the
  paid Sandbox checkout on 2026-10-10. Checkout remains disabled pending the
  remaining customer-journey checks, legal review, and release checks.
- [ ] **Licensing key provenance:** the lifecycle design says no production key
  was generated, while the deployed backend requires a signing key. Reconcile
  that document with the live secret's origin and check whether the removed
  local rehearsal value matches it without displaying either value. If they
  match, follow the dual-public-key client release sequence before rotation.
- [x] **R2 credential rotation:** on 2026-10-10 the Cloudflare dashboard showed
  the new Account API token scoped to Object Read & Write on
  `nite-dsp-releases` only. Its one-time credentials are stored in the ignored,
  mode-600 `backend/admin/.env.operations-r2-replacement` file. A signed list
  and one-byte ranged read of a current Submit release passed. Those two values
  were imported into Fly; both machines updated successfully, and the live
  `/ready` endpoint still reports durable S3 storage. No old token was revoked.
- [ ] **Cloudflare token cleanup:** identify the remaining token users before
  retiring credentials. The current account inventory shows four active
  Account API tokens for `nite-dsp-releases` and one for
  `nite-dsp-release01`. The User API token `client-websites build token` has
  Admin Read & Write across all buckets. Keep the broad user token and the
  other-bucket token untouched until their use is identified; do not revoke
  older release-bucket tokens until production usage is positively ruled out.
- [ ] **Email recovery:** assign a monitored caller for
  `sweep_unsent_confirmations`. Its implementation exists, but no recurring
  production job was verified. Stripe's successful webhook acknowledgement does
  not retry a later failed email. The local source now locks and refreshes each
  purchase before sending, excludes refunded/disputed purchases from the sweep
  and backlog, and rejects manual resends for them. Eight focused confirmation
  tests and 39 commerce/catalog tests passed; the full backend suite passed 133
  tests before deployment. This fix is now deployed in image
  `deployment-01M4E632FPNQ7R4D23ZCTEEGF2`. Follow
  `backend/docs/COMMERCE_RUNBOOK.md` for the still-unassigned recurring operator.
- [ ] **Refunds/disputes:** assign the owner, response times, and evidence trail.
  Full refunds mark purchases refunded; disputes mark them disputed. Entitlement
  revocation remains an explicit admin action. Imported purchases without payment
  intent IDs and out-of-order events require reconciliation.
- [ ] **Backups:** automatic encrypted volume snapshots and five-day retention
  are verified; six snapshots totalling 138 MiB were listed at 16:05 UTC on
  2026-10-08. PostgreSQL WAL backups are disabled on the unmanaged 256 MiB
  Postgres Flex machine. Choose between migrating to Managed Postgres (Basic
  currently starts at $38/month plus storage) and building a separately tested
  off-system dump path. Do not enable the unmanaged cluster's WAL workflow until
  its compatibility and memory requirements are resolved. Set restore
  permissions and time/data-loss targets. A local synthetic restore does not
  prove recovery from a production snapshot.
- [ ] **Monitoring:** assign alerts for API readiness, failed webhooks, pending
  confirmation emails, certificate/domain renewal, storage failures, and billing
  limits. Verify a test alert reaches the owner. No alert routing was proved.
- [x] **Fly deployment configuration and hardening:** tracked the live
  non-secret configuration in `backend/fly.toml`, including its Alembic release
  command and `/health` liveness check. From `backend/`, deploy with
  `flyctl deploy --remote-only --config fly.toml --dockerfile Dockerfile --yes`.
  The 2026-10-08 deployment completed its migration command and rolling update;
  both machines now use image
  `registry.fly.io/nite-dsp-backend:deployment-01M4E632FPNQ7R4D23ZCTEEGF2`.
  The image replaced for this rollout was
  `registry.fly.io/nite-dsp-backend:deployment-01M4E2NXH9S0E5AHHB3FFMJ2Z6`;
  redeploy that image with `flyctl deploy --image registry.fly.io/nite-dsp-backend:deployment-01M4E2NXH9S0E5AHHB3FFMJ2Z6 --config fly.toml --dockerfile Dockerfile --yes` to restore the prior code. Rollback preserves current secrets and app config. Immediately after deployment, both machines were started with passing health checks; `/health` and `/ready` returned HTTP 200. The older image before the replaced rollout was `registry.fly.io/nite-dsp-backend:deployment-01M488Y13N9CV9M68EA7XA20WW`.
- [ ] **Fly capacity and staging recovery:** machines remain at 256 MB with
  auto-stop enabled. On 2026-10-10, Fly listed both AMS machines stopped before a
  public `/ready` request; the request returned HTTP 200 in 5.32 seconds, and a
  follow-up list showed one started machine with a passing check and one stopped.
  This proves one readiness cold start, but not sustained memory headroom or a
  staging rollback. Review both before increasing production workload.
- [x] **Rate-limit client identity:** production DNS and HTTPS resolve directly
  to Fly, so the backend now keys requests on Fly's `Fly-Client-IP` header and
  ignores `X-Forwarded-For` there. Focused tests cover spoofed and missing
  platform headers. The code was deployed on 2026-10-08 and production
  readiness passed. Counters remain process-local and do not enforce a shared
  quota across two machines.
- [ ] **Rate-limit shared quota:** choose and configure a shared edge or storage
  limit before relying on per-IP quotas across concurrently running machines.
- [ ] **Waitlist/account lifecycle:** prove sign-up deduplication, export/deletion,
  unsubscribe handling, and actual retention. Existing copy promises a nurture
  sequence; its delivery and unsubscribe implementation were not verified.
- [ ] **Account ownership:** verify named owners, MFA, recovery methods, billing
  access, and renewal notices for Stripe, Vercel, Fly.io, IONOS, Resend, R2, and
  Neon. Account ownership was not changed. The temporary Vercel verification
  token described above was removed after use.
- [x] **Thursday documentation pointers:** both runtime copies now read the
  existing Submit private-preview handoff checklist and this audit's paid-sales
  blocker section. The readiness output calls out that handoff evidence does
  not approve tester distribution or commercial release. Beta drafting and its
  truth-sheet references also use current product documents.
- [ ] **Business operations:** Stripe's default GBP payout destination is
  verified as Starling Bank Ltd; account details are not stored in the repo.
  Verify payout reconciliation, accounting exports, tax obligations, customer
  receipts, refund handling, software licence terms, and third-party licence
  compliance with the responsible owner/adviser.
- [ ] **Development dependency advisory:** `npm audit` was rechecked on
  2026-10-08 and still reports five
  high-severity package findings along the development ESLint/glob path, all
  rooted in `braces` and [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
  GitHub currently lists no patched
  `braces` version. npm's suggested automatic fix downgrades `eslint-config-next`
  to 14.2.35, which does not match the app's Next 16 major; that change was not
  made. Revisit when upstream publishes a compatible fix.
- [ ] **Release automation:** current manual workflows are not evidence that
  these changes ran in CI. Review release verification and secret injection with
  the owner; CI was not changed, and temporary verification access was revoked.

## Verification recorded

| Check | Result |
| --- | --- |
| Website `npm run test:unit` | 23 passed |
| Website `npm run lint` | Passed |
| Website `npm run build:production` with closed-checkout production settings | Passed; 56 static pages generated |
| Vercel source-upload dry run | 188 files; no credential paths included |
| Website `npm audit --omit=dev` | Zero production vulnerabilities |
| Backend full test suite before deployment | 133 passed, including the completed-purchase-only confirmation-email regression |
| Backend Fly proxy IP security regressions | 10 passed |
| Disposable PostgreSQL paid-state dump/restore | Passed |
| Thursday infrastructure, beta drafting/parser, funding, and research tests | 44 passed |
| Thursday preview-handoff, paid-launch, and support helper tests (both copies) | 26 passed in each copy |
| Audio_Too infrastructure, beta drafting/parser, and funding tests | 34 passed with repository `shared/` on `PYTHONPATH` |
| Live website browser/HTTPS checks | Product names/status and closed checkout verified; Paddle removed from CSP |
| 2026-10-10 public storefront/policy check | `/pricing`, `/privacy`, and `/terms` return HTTP 200; pricing HTML has no Stripe Checkout URL or checkout API path; the deployed privacy page no longer contains the old sole-trader claim; registered company particulars and legal review remain outstanding |
| Earlier £2 Submit purchase | Exact paid Stripe session matches one completed purchase, one active licence, and a sent confirmation; Resend reported delivered on 2026-09-18, but inbox placement was not verified |
| Live Stripe webhook after rotation | Destination is active for four commerce events; current-week delivery count is zero. The 18 Sep paid session was sent to it, but its detailed attempt record aged out; a replay remains available and awaits owner approval because it resends checkout contact data |
| Five old live Payment Links | Deactivated with owner approval; saved statuses verified after reload |
| Current Stripe API and dashboard read | Three live Checkout Sessions remain: one paid and two expired; no open sessions. The three catalog products are archived, and the restricted key cannot list Payment Links or the account object |
| Scoped R2 replacement | Bucket-only token passed a ranged release read, was imported into Fly, and production `/ready` reports durable S3 storage; older tokens remain active pending usage identification |
| Backend Fly deployment | Image `deployment-01M4JQCJZF070TEDFFH54RKE9E`; current snapshot shows one started machine with a passing service check and one stopped by the configured auto-stop policy (warning: machine hasn't started) |
| Production API readiness | Current `/health` and `/ready` return HTTP 200; database, storage, and email checks true; checkout, legal approval, and release readiness false |
| Full-refund webhook deployment | Image `deployment-01M4JQCJZF070TEDFFH54RKE9E` rolled out; both machines report passing checks; signed synthetic webhook returned HTTP 200 `ignored`; checkout remains closed |
| Public email DNS records | SPF/MX, DKIM selector, and DMARC records resolve; `p=none`; message alignment and bounce handling remain unverified |
| Controlled sign-in email | Resend reports delivered at 14:18 BST; the 14:10 BST screenshot predates the probe, while inbox placement and dashboard/API workspace match remain unverified |
| Complete customer purchase and inbox delivery | The isolated £2 Sandbox payment and local webhook fulfilment passed; inbox, sign-in, release download, duplicate hosted delivery, and public staging remain unverified; no new live charge was made |
| Full-refund handling | Production code is deployed; focused commerce, end-to-end, and webhook suites pass (58 tests), and a signed synthetic event was accepted; a real refund delivery still needs operational validation |
| Para-phase free-only checkout guard | Focused paraphrase and commerce catalog suites pass (51 tests); new paid checkout route is absent, and historical paid-order redemption remains covered |

Audio_Too's initial test collection failed because the shell could not import
the repository's `nite_core` package. Running with `PYTHONPATH=../shared` passed
without installing dependencies. Expanded beta-drafting checks initially found
a pre-existing stale truth-sheet path in both copies; correcting it to the
existing product document made both checks pass. No audio, live Ableton session,
or GPU job was used.

On 2026-10-10, a process check found no Stripe CLI listener and no service
listening on local ports 8765 or 8766. The local API, redirect helper, and
Stripe CLI had been stopped after the paid Sandbox checkout. Production
`/ready` remains healthy with checkout disabled; the local Sandbox rehearsal
does not establish production readiness.

The dependency patch addresses published Next.js/sharp/source-map-js advisories:
[Next.js ImageResponse](https://github.com/vercel/next.js/security/advisories/GHSA-vcvr-r3jv-pc5j),
[Next.js advisory](https://github.com/vercel/next.js/security/advisories/GHSA-cjq9-62q9-8jv4),
[sharp](https://github.com/lovell/sharp/security/advisories/GHSA-wq5f-xc86-pv6w),
[source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
The audit did not establish that this application's static image inputs were
exploitable; patching removes the affected dependency versions.

## Cleanup record

The exact retired-file list follows below. Files were tracked and recoverable in
Git history. Required database migrations remain: earlier provider columns are
part of the upgrade path, and recorded legacy transactions still need parsing.
Audio_Too's legacy-key redaction test remains because it protects credential
redaction rather than configuring a payment integration.

```text
website/docs/NITE_DSP_WEBSITE_AUDIT_V1.md
website/docs/NITE_DSP_WEBSITE_IMPLEMENTATION_PLAN_V1.md
website/docs/NITE_DSP_CONVERSION_COMMERCIAL_UX_V1.md
website/docs/NITE_DSP_WEBSITE_COMMERCIAL_READINESS_REPORT_V1.md
website/docs/NITE_DSP_WEBSITE_COMMERCIAL_IMPLEMENTATION_REPORT_V1.md
products/slo/SmartSampleManager/docs/DOMAIN_CONFIGURATION.md
products/slo/SmartSampleManager/docs/IONOS_DNS_SETUP.md
products/slo/SmartSampleManager/docs/RAILWAY_DEPLOYMENT.md
products/slo/SmartSampleManager/docs/STAGING_DEPLOYMENT.md
products/slo/SmartSampleManager/docs/STAGING_E2E_RESULTS.md
products/slo/SmartSampleManager/docs/NITE_DSP_BACKEND_IMPLEMENTATION.md
products/slo/SmartSampleManager/docs/NITE_DSP_COMMERCIAL_ARCHITECTURE.md
products/slo/SmartSampleManager/docs/NITE_DSP_DATABASE_SCHEMA.md
products/slo/SmartSampleManager/docs/NITE_DSP_WEBSITE_ARCHITECTURE.md
products/slo/SmartSampleManager/docs/PHASE_2_FINAL_SYNTHESIS.md
products/slo/SmartSampleManager/docs/PHASE_3_FINAL_SYNTHESIS.md
products/slo/SmartSampleManager/docs/PHASE_3_PLAN.md
products/slo/SmartSampleManager/docs/PHASE_4_FINAL_SYNTHESIS.md
products/slo/SmartSampleManager/docs/PHASE_4_PLAN.md
products/slo/SmartSampleManager/docs/PHASE_5_5_FINAL_SYNTHESIS.md
products/slo/SmartSampleManager/docs/PHASE_5_5_PLAN.md
products/slo/SmartSampleManager/docs/PHASE_5_6_FINAL_SYNTHESIS.md
products/slo/SmartSampleManager/docs/PHASE_5_FINAL_SYNTHESIS.md
products/slo/SmartSampleManager/docs/PHASE_5_PLAN.md
products/slo/SmartSampleManager/docs/PRODUCTION_CONFIG_REFERENCE.md
products/slo/SmartSampleManager/docs/PRODUCTION_EMAIL.md
products/slo/SmartSampleManager/docs/PUBLIC_LAUNCH_FINAL_SYNTHESIS.md
products/slo/SmartSampleManager/docs/PUBLIC_LAUNCH_MASTER_PLAN.md
products/slo/SmartSampleManager/docs/HUMAN_COMMERCIAL_REQUIREMENTS.md
products/slo/SmartSampleManager/docs/COMMERCIAL_RELEASE_BLOCKERS.md
products/slo/SmartSampleManager/docs/PUBLIC_LAUNCH_CHECKLIST.md
products/slo/SmartSampleManager/docs/SMART_SAMPLE_MANAGER_LAUNCH_PLAN.md
products/slo/SmartSampleManager/docs/LICENSING_PRODUCTION_GAP.md
products/slo/SmartSampleManager/docs/PRODUCTION_LICENSING_ARCHITECTURE.md
railway.json
backend/railway.json
website/railway.json
website/components/ParaphraseDonate.tsx
```

## Changed files

In addition to the retired files listed above, these are the exact modified
and added files for this operations work. The unrelated SLO classification
prompt already present in the workspace was not changed.

```text
.dockerignore
Audio_Too/thursday/ops/beta_invite_ops.py
Audio_Too/thursday/ops/funding_ops.py
Audio_Too/thursday/ops/infrastructure_ops.py
README.md
autonomous-systems/thursday/thursday/ops/beta_invite_ops.py
autonomous-systems/thursday/thursday/ops/funding_ops.py
autonomous-systems/thursday/thursday/ops/infrastructure_ops.py
autonomous-systems/thursday/thursday/ops/research_ops.py
backend/.dockerignore
backend/Dockerfile
backend/app/admin.py
backend/app/config.py
backend/app/licensing.py
backend/app/rate_limit.py
backend/migrations/env.py
backend/scripts/check_staging_rehearsal.py
backend/scripts/rehearse_local_postgres_restore.sh
docs/CLOUDFLARE_HOSTING_ASSESSMENT.md
docs/OPERATIONS_AUDIT_2026-10-08.md
docs/STRIPE_COMMERCE.md
products/nite-submit/docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md
products/slo/SmartSampleManager/docs/README.md
products/slo/SmartSampleManager/docs/SECURITY_MODEL.md
products/slo/SmartSampleManager/licensing_server/README.md
website/app/about/page.tsx
website/app/account/page.tsx
website/app/beta/page.tsx
website/app/layout.tsx
website/app/learn/guides/demo-deck/page.tsx
website/app/page.tsx
website/app/paraphrase/page.tsx
website/app/portfolio/page.tsx
website/app/pricing/page.tsx
website/app/privacy/page.tsx
website/app/products/kenn/page.tsx
website/app/products/page.tsx
website/app/products/smart-sample-manager/opengraph-image.tsx
website/app/products/smart-sample-manager/page.tsx
website/app/products/submit/opengraph-image.tsx
website/app/products/submit/page.tsx
website/app/refund-policy/page.tsx
website/app/sitemap.ts
website/app/support/page.tsx
website/app/terms/page.tsx
website/app/trust/page.tsx
website/components/BetaRequestForm.tsx
website/components/CtaButton.tsx
website/components/ParaphraseBox.tsx
website/docs/NITE_DSP_WEBSITE_COMMERCIAL_ARCHITECTURE_V1.md
website/lib/commerce-config.ts
website/lib/og.tsx
website/lib/paraphrase.ts
website/package-lock.json
website/package.json
website/proxy.ts
website/scripts/check-production-config.mjs
website/tests/unit/production-config.spec.ts
Audio_Too/tests/thursday/test_thursday_documentation_ops.py
Audio_Too/tests/thursday/test_thursday_qa_ops.py
Audio_Too/tests/thursday/test_thursday_support_ops.py
Audio_Too/thursday/ops/documentation_ops.py
Audio_Too/thursday/ops/qa_ops.py
Audio_Too/thursday/ops/support_ops.py
Audio_Too/thursday/registry/handlers.py
Audio_Too/thursday/registry/system.py
autonomous-systems/thursday/docs/EXTRACTION_COUPLING.md
autonomous-systems/thursday/docs/THURSDAY_LONG_TERM_PLAN.md
autonomous-systems/thursday/tests/test_thursday_documentation_ops.py
autonomous-systems/thursday/tests/test_thursday_qa_ops.py
autonomous-systems/thursday/tests/test_thursday_support_ops.py
autonomous-systems/thursday/thursday/ops/documentation_ops.py
autonomous-systems/thursday/thursday/ops/qa_ops.py
autonomous-systems/thursday/thursday/ops/support_ops.py
autonomous-systems/thursday/thursday/registry/handlers.py
autonomous-systems/thursday/thursday/registry/system.py
products/slo/SLO_PRIVATE_BETA_PLAN_V1.md
products/slo/SLO_PRIVATE_BETA_TEST_PLAN_V1.md
```
