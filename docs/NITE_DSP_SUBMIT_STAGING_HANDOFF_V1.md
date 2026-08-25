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

Create or restore an isolated HTTPS staging service and database. Do not reuse
the production service or production database. The backend must start with:

```text
ENVIRONMENT=staging
NITE_DSP_PUBLIC_URL=https://<staging-website-host>
NITE_DSP_API_URL=https://<staging-api-host>
DATABASE_URL=<isolated-staging-database-url>
PADDLE_API_BASE_URL=https://sandbox-api.paddle.com
PADDLE_PRODUCT_ID=<Submit-sandbox-product-id>
PADDLE_ACTIVE_PRICE_ID=<Submit-sandbox-price-id>
STORAGE_BACKEND=s3
STORAGE_BUCKET=<private-staging-release-bucket>
STORAGE_ENDPOINT=https://<private-s3-compatible-endpoint>
STORAGE_REGION=<region>
STORAGE_ACCESS_KEY_ID=<secret-store-value>
STORAGE_SECRET_ACCESS_KEY=<secret-store-value>
ADMIN_API_KEY=<secret-store-value>
SESSION_SECRET=<secret-store-value>
PADDLE_WEBHOOK_SECRET=<sandbox-webhook-secret>
```

Use the staging signing keypair and an isolated transactional-email mode. Do
not copy production keys, storage credentials, database URLs, or customer
documents into this environment. Startup validation intentionally rejects live
Paddle URLs, incomplete HTTPS URLs, and incomplete durable-storage settings.

## Deployment sequence

1. Deploy the platform branch containing commits `04caa4a` and `c0dbf59` to
   the isolated staging target.
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

The previously linked Railway staging project is deleted. The surviving
Railway project contains production services only and has no staging
environment. Provisioning or restoring an isolated staging target is therefore
the remaining owner-controlled operational step.
