# NITE DSP Submit staging handoff V1

**Scope:** private staging only. This handoff does not authorise a production
deploy, live Paddle checkout, production database mutation, or public release.

## Current release candidate

The Submit integration candidate is:

- Product: `nite-submit`
- Version: `0.2.0`
- Platform/architecture: `macos` / `arm64`
- Channel: `private-beta`
- ZIP: `products/nite-submit/artifacts/Submit-0.2.0-macOS.zip`
- SHA-256: `64c503ebbbc975a8c839cb731ec158b9e0ef14029e84df23ff2e91dc5f0096a9`

The artifact was locally registered and fetched through the authenticated
download path; the downloaded bytes matched this checksum. Remote staging has
not yet been registered.

## Required staging boundary

The Railway project `ample-liberation` now has an isolated `submit-staging`
environment with an online Postgres service and the existing Backend service
attached to that environment. The staging API domain is
`https://backend-submit-staging.up.railway.app`. Do not reuse the production
database or production URLs. The backend must start with:

```text
ENVIRONMENT=staging
NITE_DSP_PUBLIC_URL=https://backend-submit-staging.up.railway.app
NITE_DSP_API_URL=https://backend-submit-staging.up.railway.app
DATABASE_URL=<isolated-staging-database-url>
PADDLE_API_BASE_URL=https://sandbox-api.paddle.com
PADDLE_PRODUCT_ID=<Submit-sandbox-product-id>
PADDLE_ACTIVE_PRICE_ID=<Submit-sandbox-price-id>
STORAGE_BACKEND=local
MOCK_STORAGE_DIR=/app/mock_storage
ADMIN_API_KEY=<secret-store-value>
SESSION_SECRET=<secret-store-value>
PADDLE_WEBHOOK_SECRET=<sandbox-webhook-secret>
```

Use the staging signing keypair and an isolated transactional-email mode. Do
not copy production keys, storage credentials, database URLs, or customer
documents into this environment. Startup validation intentionally rejects live
Paddle URLs, incomplete HTTPS URLs, and incomplete durable-storage settings.

## Deployment sequence

1. Deploy the platform branch containing commits `04caa4a`, `c0dbf59`, and
   `9b2c00d` to the isolated staging target.
2. Run database migrations with `alembic upgrade head` and verify `/health` and
   `/ready`.
3. Configure the Submit Sandbox catalog values and register the Paddle Sandbox
   webhook at the staging API endpoint.
4. Upload the exact ZIP to the private release bucket. The object key should be
   `releases/nite-submit/0.2.0/Submit-0.2.0-macOS.zip`.
5. From a controlled operator machine, register it with:

   ```sh
   python scripts/upload_release.py \
     nite-submit 0.2.0 macos arm64 \
     /path/to/Submit-0.2.0-macOS.zip \
     --channel private-beta \
     --api-url https://<staging-api-host> \
     --admin-key "$ADMIN_API_KEY"
   ```

   The CLI recomputes the checksum before registration; stop if it is not the
   candidate SHA above.

## Remote proof gate

Record one fresh, independent run of:

1. magic-link request and verification;
2. Sandbox checkout or an explicitly issued private-beta entitlement;
3. Paddle Sandbox webhook receipt and idempotency result;
4. entitlement and licence issuance;
5. authenticated `GET /downloads/latest` for `private-beta` / `macos` / `arm64`;
6. signed download fetch; and
7. SHA-256 of the downloaded ZIP equals
   `64c503ebbbc975a8c839cb731ec158b9e0ef14029e84df23ff2e91dc5f0096a9`.

Do not send the beta handoff until all seven steps are recorded. The local
proof and the code-path test suite are not substitutes for this remote proof.

## Current external blocker

The isolated Railway environment and Postgres service are now present. The
Backend service was attached to it without copying production variables, and
staging variables were configured with fresh staging secrets. The first direct
deployment was accepted but stopped during Railway's build scheduling phase,
before any build or runtime logs were emitted. The connected GitHub deployment
retry also failed because this workspace has no GitHub installation for
`Jack441095/NITE_DSP`.

Next operational action: enable the repository's GitHub integration in Railway
or retry the direct Railway builder when the workspace permits it. Only after a
successful `/health` and `/ready` check should the exact ZIP be registered and
the remote seven-step proof be run. This staging setup uses local release
storage for the cost-conscious proof environment; durable S3-compatible
storage remains required before any paid launch.
