# Email / Domain Configuration

# HUMAN ACTION REQUIRED

```text
STATUS: BLOCKED -- no domain is owned
OWNER:  You
BLOCKS: Sections 9-14 (domain-wide URL config, TLS, real transactional email, SPF/DKIM/DMARC)
REASON: See docs/HUMAN_COMMERCIAL_REQUIREMENTS.md -- "Company/product website domain",
        "Support email address"
```

## Central configuration (Section 9) -- already satisfied, verified this phase

The master prompt asks for `PUBLIC_WEB_URL`, `API_BASE_URL`, `SUPPORT_EMAIL`, `ACCOUNT_URL`,
`DOWNLOAD_URL` configured centrally, never duplicated. Phase 4 already built exactly this:
`Settings.nite_dsp_public_url`, `nite_dsp_api_url`, `nite_dsp_support_email`
(`nitedsp/backend/app/config.py`), consumed everywhere via `settings.*`, never a literal string.
`ACCOUNT_URL`/`DOWNLOAD_URL` are intentionally *not* separate settings -- they're paths under
`nite_dsp_public_url`/`nite_dsp_api_url` (`/account`, `/downloads/latest`), which avoids
duplicating the domain itself in a second variable, consistent with Section 10's "prefer minimum
operational complexity." Confirmed via the config-leak scan this phase
(`docs/PHASE_5_FINAL_SYNTHESIS.md`) that no literal domain is hardcoded anywhere in the shipped
website bundle or backend.

## What's still blocked

- **Domain environments (Section 10)**: no domain exists to split into `www.`/`api.`/`staging.`
  subdomains yet. The simplest viable pattern once a domain exists: `<domain>` for the website,
  `api.<domain>` for the backend, matching what `nite_dsp_public_url`/`nite_dsp_api_url` already
  expect as two independent env vars -- no code change needed, just setting real values.
- **TLS (Section 11)**: requires real hosting (`docs/HOSTED_STAGING_DEPLOYMENT.md`, also BLOCKED).
- **Real transactional email (Section 13)**: `email_provider` stays `"console"` until a real
  provider account exists. `email.py` already refuses to silently fall through to a fake "sent"
  state for any unimplemented provider (`raise NotImplementedError`), so this fails loudly
  rather than pretending to work if misconfigured.
- **SPF/DKIM/DMARC (Section 14)**: cannot be configured or verified without a real domain's DNS
  control. Documented here as a known follow-up, not attempted.

## Magic-link production hardening (Section 12) -- verified against what's testable now

Token entropy: 256 bits (`secrets.token_urlsafe(32)`). Expiration: enforced, 15 min. Single-use:
enforced, verified via automated test (replay returns "Token already used"). No account
enumeration: `/auth/request-link` always returns `{"status": "sent"}` regardless of whether the
email is a known user. No token leakage in logs: the raw token is never logged server-side, only
the SHA-256 hash is persisted; the console email provider logs the raw token by design (it *is*
the "email"), which is correct for local/staging and must not carry over once a real email
provider exists. HTTPS destination: not yet verifiable, since no real hosted deployment exists.
