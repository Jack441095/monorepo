"""
NITE DSP backend configuration.

Environment-driven throughout -- no domain, hosting, or secret is ever
hardcoded here. See docs/HUMAN_COMMERCIAL_REQUIREMENTS.md for why: the
company domain is not yet owned, so NITE_DSP_PUBLIC_URL defaults to a local
address rather than a guessed production domain (Phase 4 Section 6's
explicit requirement). ".env" files are per-environment (development/
staging/production) and never committed -- see .env.example for the
documented shape.
"""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Which environment this process is running as. Never inferred implicitly
    # from other settings -- always explicit, so a staging deploy can never
    # accidentally behave like production because of a missing env var.
    environment: str = "development"  # "development" | "staging" | "production"

    database_url: str = "postgresql+psycopg2://localhost/nitedsp_staging"

    # Public-facing URLs -- Phase 4 Section 6. Defaulting to localhost is
    # deliberate: a missing env var in a real deployment fails loudly (links
    # point at localhost, obviously broken) rather than silently pointing at
    # a guessed production domain that isn't owned yet.
    nite_dsp_public_url: str = "http://localhost:3000"
    nite_dsp_api_url: str = "http://localhost:8000"
    nite_dsp_support_email: str = "support@localhost.invalid"

    # Session/auth
    session_secret: str = "dev-only-insecure-secret-change-in-every-real-environment"
    magic_link_ttl_seconds: int = 15 * 60  # Phase 3's recommended 15-minute expiry

    # Licensing -- see docs/LICENSE_KEY_LIFECYCLE.md. The staging keypair is
    # generated fresh per local setup (scripts/generate_staging_keypair.py),
    # never committed, and is cryptographically unrelated to any future
    # production key.
    #
    # Two ways to supply the signing key, chosen at Jack's direction
    # (Railway deploy, 2026-08-13): a hosted environment like Railway has no
    # guaranteed-persistent filesystem across redeploys unless a Volume is
    # attached, so production reads the key straight from an env var
    # (licensing_private_key_base64) instead -- same pattern already used
    # for session_secret/admin_api_key. The file-path fields remain the
    # local/staging mechanism only; _validate_production_config below never
    # accepts a file path as sufficient for a real production environment.
    licensing_private_key_path: str = "./staging_keys/licensing_signing_key.private"
    licensing_public_key_path: str = "./staging_keys/licensing_signing_key.public"
    licensing_private_key_base64: str = ""
    offline_grace_period_seconds: int = 14 * 24 * 60 * 60  # unchanged from the dev server -- Section 22
    default_max_activations: int = 3  # unchanged from the dev server -- Phase 3 Section 23

    # Commerce -- Section 31. Paddle credentials are only ever read from
    # environment/secrets, never hardcoded. Empty by default; commerce.py's
    # PaddleProvider treats an empty api_key as "sandbox account not
    # configured" and refuses to attempt real API calls, falling back to a
    # documented mock mode used by the local E2E test.
    paddle_api_key: str = ""
    paddle_webhook_secret: str = ""

    # sandbox-api.paddle.com in every environment until a human explicitly
    # flips this to api.paddle.com for a real production deploy -- this is
    # the one line that draws the sandbox/live line for API calls, so it's
    # never inferred from `environment` (see docs/PADDLE_INTEGRATION_AUDIT.md).
    paddle_api_base_url: str = "https://sandbox-api.paddle.com"

    # Product/price ID mapping (docs/PADDLE_INTEGRATION_AUDIT.md Section 12) --
    # empty until a real Paddle sandbox product exists. commerce.py's webhook
    # handler refuses to issue an entitlement for any price_id/product_id
    # combination not represented in this mapping; it never infers a mapping
    # from event payload alone.
    paddle_product_id: str = ""
    paddle_intro_price_id: str = ""
    paddle_regular_price_id: str = ""

    # Which of the two price IDs above is currently offered at checkout.
    # Section 18/67: an explicit owner-controlled switch, not a code change
    # and not an unverified clock -- flipping this is a deliberate, reviewable
    # action (env var change + deploy), never automatic based on a launch date.
    paddle_active_price_id: str = ""

    # Email -- Section 63/64. "console" logs the email instead of sending it,
    # used for local/staging until a real transactional email provider is
    # configured. Never silently falls through to a real send in an
    # unconfigured environment.
    email_provider: str = "console"  # "console" | "resend"
    email_from_name: str = "NITE DSP"
    email_from_address: str = "noreply@localhost.invalid"
    resend_api_key: str = ""

    # Downloads -- Section 51/52. Local storage is development/test-only; a
    # private S3-compatible bucket (including Cloudflare R2) is the durable
    # deployment adapter. Release keys are immutable object/path keys.
    storage_backend: str = "local"  # "local" | "s3"
    storage_bucket: str = ""
    storage_endpoint: str = ""
    storage_region: str = "auto"
    storage_access_key_id: str = ""
    storage_secret_access_key: str = ""
    mock_storage_dir: str = "./mock_storage"

    # Admin -- Section 73. Deliberately fail-closed: empty (the default)
    # means every admin endpoint refuses, full stop. This is the direct fix
    # for the exact gap docs/PRODUCTION_LICENSING_ARCHITECTURE.md flagged in
    # the dev licensing_server (POST /v1/admin/licenses has zero auth) --
    # that mistake must never be repeated here.
    admin_api_key: str = ""


def _storage_configuration_problems(s: Settings) -> list[str]:
    problems = []
    if s.storage_backend not in ("local", "s3"):
        problems.append(
            f"storage_backend={s.storage_backend!r} is unsupported; expected 'local' or 's3'"
        )
    if s.storage_backend == "s3":
        for field_name, value in (
            ("storage_bucket", s.storage_bucket),
            ("storage_endpoint", s.storage_endpoint),
            ("storage_access_key_id", s.storage_access_key_id),
            ("storage_secret_access_key", s.storage_secret_access_key),
        ):
            if not value:
                problems.append(f"{field_name} is required when storage_backend=s3")
        if s.storage_endpoint:
            parsed_endpoint = urlparse(s.storage_endpoint)
            if parsed_endpoint.scheme != "https" or not parsed_endpoint.hostname:
                problems.append("storage_endpoint must be a public HTTPS URL when storage_backend=s3")
    return problems


def _validate_production_config(s: Settings) -> None:
    """Phase 5.5, Section 23: production startup must fail loudly if
    required configuration is missing, never silently fall back to a
    development-shaped default (localhost URLs, the dev session secret, an
    unconfigured admin key). Collects every violation before raising so a
    real deployment sees the whole list in one failed startup, not one
    error per redeploy attempt."""
    if s.environment != "production":
        return

    problems = []
    for field_name, value in (
        ("nite_dsp_public_url", s.nite_dsp_public_url),
        ("nite_dsp_api_url", s.nite_dsp_api_url),
    ):
        if "localhost" in value or "127.0.0.1" in value:
            problems.append(f"{field_name}={value!r} still points at localhost")

    if s.nite_dsp_support_email.endswith("@localhost.invalid"):
        problems.append(f"nite_dsp_support_email={s.nite_dsp_support_email!r} is still the dev placeholder")
    if s.email_from_address.endswith("@localhost.invalid"):
        problems.append(f"email_from_address={s.email_from_address!r} is still the dev placeholder")
    if s.session_secret == "dev-only-insecure-secret-change-in-every-real-environment":
        problems.append("session_secret is still the dev default")
    if not s.admin_api_key:
        problems.append("admin_api_key is empty -- admin endpoints would be entirely unreachable")
    if not s.licensing_private_key_base64:
        problems.append(
            "licensing_private_key_base64 is empty -- production reads the signing key from this "
            "env var, never from a file path (see config.py's licensing key comment)"
        )
    if "nitedsp_staging" in s.database_url or "nitedsp_test" in s.database_url:
        problems.append(f"database_url still points at a local staging/test database: {s.database_url!r}")
    if s.email_provider not in ("console", "resend"):
        problems.append(f"email_provider={s.email_provider!r} is not a valid provider")
    elif s.email_provider != "resend":
        problems.append("email_provider must be 'resend' in production; console email is not deliverable")
    elif not s.resend_api_key:
        problems.append("email_provider is 'resend' but resend_api_key is empty")
    if s.storage_backend != "s3":
        problems.append("storage_backend must be 's3' in production; local storage is not durable")
    problems.extend(_storage_configuration_problems(s))

    if problems:
        raise RuntimeError(
            "Refusing to start with environment=production and invalid configuration:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )


def _validate_staging_config(s: Settings) -> None:
    """Keep a staging deployment pointed at Paddle Sandbox and HTTPS.

    Staging is the only environment currently intended to exercise checkout.
    Fail loudly when it is half-configured or pointed at the live Paddle API;
    local development remains intentionally permissive so simulated webhook
    tests can run without credentials.
    """
    if s.environment != "staging":
        return

    problems = []
    paddle_host = urlparse(s.paddle_api_base_url).hostname
    if paddle_host != "sandbox-api.paddle.com":
        problems.append(
            "paddle_api_base_url must use sandbox-api.paddle.com in staging; "
            f"got {s.paddle_api_base_url!r}"
        )

    for field_name, value in (
        ("paddle_api_key", s.paddle_api_key),
        ("paddle_webhook_secret", s.paddle_webhook_secret),
        ("paddle_product_id", s.paddle_product_id),
        ("paddle_active_price_id", s.paddle_active_price_id),
    ):
        if not value:
            problems.append(f"{field_name} is required for staging checkout")

    configured_price_ids = {
        value for value in (s.paddle_intro_price_id, s.paddle_regular_price_id) if value
    }
    if not configured_price_ids:
        problems.append("at least one of paddle_intro_price_id or paddle_regular_price_id is required")
    elif s.paddle_active_price_id and s.paddle_active_price_id not in configured_price_ids:
        problems.append("paddle_active_price_id must match an intro or regular configured price ID")

    for field_name, value in (
        ("nite_dsp_public_url", s.nite_dsp_public_url),
        ("nite_dsp_api_url", s.nite_dsp_api_url),
    ):
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1"}:
            problems.append(f"{field_name} must be a public HTTPS URL in staging; got {value!r}")

    if problems:
        raise RuntimeError(
            "Refusing to start with environment=staging and invalid configuration:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )

    storage_problems = _storage_configuration_problems(s)
    if storage_problems:
        raise RuntimeError(
            "Refusing to start with invalid release storage configuration:\n"
            + "\n".join(f"  - {p}" for p in storage_problems)
        )


settings = Settings()
_validate_production_config(settings)
_validate_staging_config(settings)
