# Cloudflare hosting assessment

Assessed 2026-10-02 against the current website and customer backend. This is an architecture assessment; no deployment, DNS changes, Cloudflare resources, dependency additions, or CI changes were made.

## Recommendation

Use Cloudflare Workers for the website and R2 for private release downloads. Move the Python backend to Cloudflare Containers if preserving the current application is the first priority. Keep the existing PostgreSQL database during that first stage, then treat moving customer records to D1 as a separate migration with explicit concurrency tests.

That first stage consolidates application hosting, but the database remains outside Cloudflare. A strict Cloudflare-only target is Workers + D1 + R2, with commerce, account, and licensing persistence rewritten for D1. Hyperdrive connects to an existing PostgreSQL database; it does not move that database into Cloudflare. [Hyperdrive overview](https://developers.cloudflare.com/hyperdrive/)

For the strict target, prove the D1 persistence path in staging before moving the public site. Replacing PostgreSQL while changing the website runtime and live commerce together would make failures harder to diagnose and roll back.

Stripe remains the payment provider. Cloudflare hosting does not replace Stripe Checkout or Stripe webhook verification. Desktop audio applications and their local Ableton integrations stay local. This assessment covers the public website, customer API, and release distribution; it does not propose moving every project in this folder to Workers.

## What the repository actually uses

| Area | Current implementation | Cloudflare implication |
| --- | --- | --- |
| Website | Next.js 16.3.5, React 19.2.8, App Router in `website/package.json` | Needs a Workers-compatible Next runtime or adapter. |
| Website server routes | Two waitlist route handlers use `@neondatabase/serverless` in `website/lib/db.ts` | Keeping Neon preserves an external database dependency; D1 needs different queries and bindings. |
| Protected portfolio | `website/proxy.ts` checks Basic Auth and fails closed without its password | Must test Next 16 proxy behavior, including nested portfolio URLs and assets. |
| Customer API | FastAPI, synchronous SQLAlchemy, `psycopg2-binary`, Python 3.12 Docker image | Containers preserve the ordinary Linux Python environment; Python Workers require an import/runtime compatibility spike. |
| Database | PostgreSQL UUID, ARRAY, JSONB, PostgreSQL upserts, `SELECT ... FOR UPDATE` | D1 is a schema and transaction migration, not a connection-string change. |
| Licences | PyNaCl Ed25519 signatures, canonical JSON, production signing key from an environment secret | Preserve the exact signed bytes and existing public key. No signing key belongs in an image or browser bundle. |
| Releases | Existing `S3CompatibleStorage` uses boto3, immutable keys, SHA-256, and signed download URLs | R2 is already an intended adapter target; prove a real R2 round trip before cutover. |
| Email | Backend supports `console` and Resend | Retaining Resend is compatible with Cloudflare hosting. Cloudflare Email Service needs another adapter if service consolidation is desired. |
| Paraphrase | Feature-gated API streams from a separate engine URL | Hosting the public API does not migrate the model engine. Inventory that service before declaring all enabled services migrated. |
| Deployment | Railway configurations, backend pre-deploy Alembic migration, and website Vercel configuration | Add a reviewed Cloudflare deployment path first; remove old deployment files after cutover succeeds. |
| Rate limits | Backend keeps counters in process memory and trusts the first forwarded IP | Multiple Workers/Containers need a shared policy and a trusted ingress boundary. |

These observations come from `website/package.json`, `website/app/api/waitlist`, `website/proxy.ts`, `backend/app/database.py`, `backend/app/models.py`, `backend/app/licensing.py`, `backend/app/storage.py`, `backend/app/rate_limit.py`, and the existing deployment files.

## Hosting options

| Option | Application changes | Database location | Assessment |
| --- | --- | --- | --- |
| Workers website + R2; current API host | Website runtime/configuration and release-storage rehearsal | Existing PostgreSQL | Smallest first trial, but retains the API host. |
| Workers website + Containers API + R2 | New Worker/Container routing and lifecycle configuration; mostly retain FastAPI | Existing PostgreSQL | Preferred first move when preserving the backend matters. Cloudflare hosts the application compute, but not all its data. |
| Workers website + Python Workers API + Hyperdrive + R2 | ASGI entrypoint, compatible dependencies/driver, binding-aware settings and database access | Existing PostgreSQL | Worth a compatibility spike; not a drop-in replacement for the current Docker service. |
| Workers website/API + D1 + R2 | D1 schema, migrations and persistence implementation; retain public HTTP/licence contracts | Cloudflare D1 | Preferred strict Cloudflare-only target once transaction behavior is proven. |
| Static Next export on Pages | Move server route handlers and portfolio gate elsewhere, or remove them | Depends on API | Poor fit for the current full-stack website. |

### Website runtime

Cloudflare currently recommends **vinext** for Next.js on Workers, including existing Next 16 applications. It reimplements the Next API surface on Vite and is **beta**. The documented compatibility check should precede adoption. OpenNext remains a documented alternative when compatibility gaps prevent the preferred path; Pages is the static-export path. [Next.js on Workers](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/), [OpenNext adapter](https://developers.cloudflare.com/workers/framework-guides/web-apps/opennext/), [Next.js on Pages](https://developers.cloudflare.com/pages/framework-guides/nextjs/)

For this website, the first compatibility spike should cover `proxy.ts`, `next/image`, `next/font/google`, configured security headers, dynamic waitlist route handlers, account query parameters, and server environment secrets. Start with an isolated vinext preview and retain the existing Next build for comparison. If those checks fail, compare OpenNext against this exact Next 16.3.5 version before selecting an adapter. An ordinary `next build` passing does not prove Workers compatibility.

### Python backend

FastAPI is supported in Python Workers through Cloudflare's ASGI integration. That does not establish compatibility for this application's full dependency set. Python Workers support pure Python, PyEmscripten wheels, and packages included in Pyodide; ordinary Linux binary wheels are insufficient evidence. Test imports and real execution for PyNaCl/cffi, the chosen PostgreSQL driver, SQLAlchemy, boto3, HTTPX, and Pydantic. Replace Uvicorn's entrypoint with the documented Workers ASGI entrypoint for that trial. [FastAPI support](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/), [Python package support](https://developers.cloudflare.com/workers/languages/python/packages/)

Cloudflare's current Python Hyperdrive guide lists `asyncpg`, `pg8000`, and `psycopg`, supports synchronous SQLAlchemy, and requires a compatibility date of 2026-09-08 or later. Async SQLAlchemy is currently unsupported because greenlet is unavailable. The repository uses `psycopg2-binary`, so the guide does not verify its current driver. Audit connection lifetimes and serialization rather than reusing a global engine without testing concurrent requests. [Python Hyperdrive support](https://developers.cloudflare.com/hyperdrive/examples/python-workers/)

Containers preserve the existing native Python environment and are the less invasive compute migration. Build Linux AMD64 images, forward HTTP through a Worker/Durable Object, wait for the API port to be ready, and configure restart/inactivity behavior. Container disk is ephemeral by default. Snapshots are point-in-time copies, not a continuously durable database volume. Do not run production PostgreSQL on that disk or depend on an R2 FUSE mount as a PostgreSQL data directory. [Container lifecycle](https://developers.cloudflare.com/containers/concepts/architecture/)

Containers currently need explicit scaling/routing decisions; built-in stateless autoscaling is not available. API startup, sleep/restart, image rollouts, observability, and database connection limits need staging checks. Run Alembic as a controlled migration step, retaining the existing rule that an ordinary API restart does not change the schema. [Containers FAQ](https://developers.cloudflare.com/containers/faq/)

### Database and release storage

D1 uses SQLite SQL semantics and provides Worker and HTTP APIs. Translate PostgreSQL arrays/JSONB/UUID handling and server SQL functions. Rework the row-lock assumptions in licensing and Stripe receipt processing. Unique constraints must prevent duplicate provider orders, duplicate event receipts, and duplicate activations under concurrent requests. Repeated requests and failures after partial progress must preserve current retry behavior. [D1 overview](https://developers.cloudflare.com/d1/)

Keep the existing signing key and canonical token contract during a database migration. Changing persistence is not a reason to rotate the signing key. An eventual language change would need client-verification fixtures proving that existing applications accept the new signatures.

R2 supports the S3 operations used by the current storage adapter. Configure the existing `STORAGE_BACKEND=s3` fields with bucket-scoped credentials and the R2 S3 endpoint, using region `auto`. Rehearse `head_bucket`, uploads, metadata, SHA-256 readback, download headers, expiry, and cleanup against a disposable prefix. A fake S3 test does not prove provider compatibility. [R2 S3 compatibility](https://developers.cloudflare.com/r2/api/s3/api/)

Keep the bucket private. Existing presigned URLs should use the R2 S3 API domain; Cloudflare documents that those URLs do not work on a custom domain. If branded download URLs become necessary, implement an authenticated Worker download route as a separate change. [R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

Cloudflare Email Sending is now public beta and supports Workers bindings, REST, and SMTP. It could replace Resend later, but the current application has no Cloudflare email adapter. Verify sender-domain setup, delivered magic links, bounces, retries, and staging recipient isolation before changing customer email. [Email Service](https://developers.cloudflare.com/email-service/), [Email Sending setup](https://developers.cloudflare.com/email-service/get-started/send-emails/)

## Staged migration and release gates

1. **Create a compatibility preview.** Use synthetic database rows and Stripe test mode. Compare the current Next application against the Workers runtime. No production DNS or Stripe endpoint changes are needed for this stage.
2. **Consolidate API routing.** Prefer a same-origin `/api` route to avoid cross-origin cookie and CSP changes. Strip the prefix consistently, preserve session cookies and request bodies, and forward API traffic to the selected backend. Preserve the portfolio gate and private admin routes. A direct public backend endpoint must not bypass the trusted ingress policy.
3. **Rehearse R2.** Use the existing guarded rehearsal script with synthetic bytes in a disposable bucket/prefix. Confirm entitlement checks still precede issuing downloads. Keep release keys immutable and preserve checksums.
4. **Move API compute.** Use Containers if the Python Workers compatibility spike is incomplete. Inject signing/session/Stripe/storage secrets at runtime; never bake them into images. Keep PostgreSQL unchanged for this stage. Verify `/ready`, cold starts, restarts, streaming, email, and concurrent webhook delivery.
5. **Prove strict Cloudflare-only persistence separately.** Create D1 migrations and a persistence implementation. Compare synthetic and sanitized export counts, foreign keys, purchase amounts, entitlement status, activation limits, receipt replay, refunds, and redemption tokens. Replace direct Neon website queries too. Perform a restore rehearsal before permitting customer writes.
6. **Cut over one owner of writes.** Take a final backup, stop writes briefly for the database migration, reconcile outstanding Stripe events, and switch routing. Do not dual-write customer records without a separately tested reconciliation design. Stripe requests must reach one authoritative receipt store during the transition.
7. **Retire old hosting.** Keep the previous compute deployment and a documented restore procedure during the observation period. Remove obsolete deployment files and provider account resources only after the cutover is accepted.

The current in-memory limiter cannot enforce a shared quota across instances. Use a distributed counter for licence, redemption, and paid quota accounting. Workers' rate-limit binding is useful for abuse throttling, but its counters are local to each Cloudflare location and eventually consistent; it is not an exact global accounting mechanism. Have trusted ingress overwrite forwarded client-IP headers, and test spoofed headers. [Workers rate limiting](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/)

Preserve Stripe's raw webhook bytes and `Stripe-Signature` through every routing hop. Test duplicate delivery, separate completed/async-payment events for the same session, failure-and-retry, unknown products, full/partial refunds, and disputes. Do not cache webhook, auth, account, licence, or redemption responses at the edge. Public pricing and immutable public assets can use normal cache rules.

## Dependencies and verification before implementation

No dependencies were installed for this assessment. A website implementation would add vinext/Vite/Cloudflare deployment tooling, or OpenNext/Wrangler if selected after testing. Python Workers would add the Workers entrypoint/tooling and may replace the PostgreSQL driver. Containers need routing/deployment tooling. A D1 migration needs a reviewed persistence path, not an unexamined third-party SQLAlchemy dialect. The repository requires approval before dependencies or CI changes.

Use the existing scoped checks as the baseline:

```sh
# From website/
npm run lint
npm run test:unit
npm run build
npm run test:e2e

# From backend/ with the dedicated local test database configured
python -m pytest -q tests
python scripts/rehearse_s3_release_storage.py
```

After adding a Cloudflare runtime, run the same HTTP/browser behavior against its local preview and a separate staging deployment. The commands above alone do not validate a Cloudflare deployment. Add tests for binding configuration, cookie forwarding, exact licence signatures, D1 transaction failures, concurrent activation limits, and verified webhook replay; mutation-check new regression guards as required by `AGENTS.md`.

Application rollback and database rollback are separate. Revert Workers/Container traffic when the database remains unchanged. After D1 has accepted customer writes, restoring an old PostgreSQL snapshot would lose those writes; pause writes and reconcile/export them before any database rollback. Keep the old database read-only rather than assuming a DNS revert restores data safely.

Capacity and cost should be estimated from measured request CPU, database operations, release download volume, and container uptime. No pricing estimate is made here because those measurements and account requirements are not available. This assessment has checked repository compatibility constraints and current official documentation; it has not proved a deployed Cloudflare runtime.
