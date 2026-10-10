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

from .submit_licensing import load_submit_signing_key


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Which environment this process is running as. Never inferred implicitly
    # from other settings -- always explicit, so a staging deploy can never
    # accidentally behave like production because of a missing env var.
    environment: str = "development"  # "development" | "staging" | "production"

    # Optional staging gate. Keep lightweight local/console staging available
    # for development, but require this flag for a staging deployment that is
    # allowed to claim a customer checkout/download rehearsal is ready.
    staging_customer_rehearsal: bool = False

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
    # Two ways to supply the signing key: a hosted container has no
    # guaranteed-persistent filesystem across redeploys unless a Volume is
    # attached, so production reads the key straight from an env var
    # (licensing_private_key_base64) instead -- same pattern already used
    # for session_secret/admin_api_key. The file-path fields remain the
    # local/staging mechanism only; _validate_production_config below never
    # accepts a file path as sufficient for a real production environment.
    licensing_private_key_path: str = "./staging_keys/licensing_signing_key.private"
    licensing_public_key_path: str = "./staging_keys/licensing_signing_key.public"
    licensing_private_key_base64: str = ""
    # Submit's offline key uses a separate public key from the backend's
    # online licensing service, so it must have its own production secret.
    submit_license_private_key_base64: str = ""
    offline_grace_period_seconds: int = 14 * 24 * 60 * 60  # unchanged from the dev server -- Section 22
    default_max_activations: int = 3  # unchanged from the dev server -- Phase 3 Section 23

    # Empty credentials keep checkout closed; webhooks use a separate signing secret.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_product_id: str = "nite-submit"
    stripe_intro_price_id: str = ""
    stripe_regular_price_id: str = ""
    stripe_active_price_id: str = ""
    stripe_checkout_enabled: bool = False
    legal_review_approved: bool = False
    release_ready: bool = False

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

    # Paraphrase product (products/nite-paraphrase) -- Phase 2. Off by
    # default (the estate norm: a feature never exposes itself before the
    # staging gate flips it on). The engine is a separate deployable
    # service that wraps Ollama -- see products/nite-paraphrase/engine/
    # -- so this backend only needs its URL and an optional shared token,
    # never Ollama credentials.
    paraphrase_enabled: bool = False
    paraphrase_engine_url: str = "http://localhost:8687"
    paraphrase_service_token: str = ""
    paraphrase_free_daily_limit: int = 3
    # Phase 4 placeholder: an unlock token the webhook path will issue to
    # paid users. Until then it lets staging/tests simulate an unlocked
    # session without touching Stripe. Empty means no one bypasses the
    # free tier.
    paraphrase_unlock_token: str = ""

    # Keep the internal slug so old Stripe payments can still redeem during
    # their token lifetime; Para-phase no longer creates paid Checkout sessions.
    paraphrase_product_id: str = "nite-paraphrase"

    # How long a redeemed paraphrase unlock stays valid (an anonymous
    # session token, deliberately not a perpetual licence).
    paraphrase_unlock_days: int = 7


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


def _usable_sender_address(address: str) -> bool:
    """Return whether an environment sender looks usable for a real provider.

    Domain ownership is verified by the email provider, not by this process;
    this only rejects empty, malformed, local-only, and ``.invalid`` values
    before the application advertises deliverable email.
    """
    if not address or address != address.strip() or any(char.isspace() for char in address):
        return False
    local_part, separator, domain = address.rpartition("@")
    return bool(
        separator
        and local_part
        and domain
        and "." in domain
        and not domain.lower().endswith(".invalid")
    )


def _checkout_configuration_problems(s: Settings) -> list[str]:
    problems = []
    for name in ("stripe_secret_key", "stripe_product_id", "stripe_active_price_id"):
        if not getattr(s, name):
            problems.append(f"{name} is required for checkout")
    prices = {p for p in (s.stripe_intro_price_id, s.stripe_regular_price_id) if p}
    if not prices:
        problems.append("at least one of stripe_intro_price_id or stripe_regular_price_id is required")
    elif s.stripe_active_price_id and s.stripe_active_price_id not in prices:
        problems.append("stripe_active_price_id must match an intro or regular configured price ID")
    if s.stripe_product_id == "nite-submit":
        try:
            load_submit_signing_key(s.submit_license_private_key_base64)
        except ValueError as exc:
            problems.append(str(exc))
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
    if s.stripe_checkout_enabled and not s.legal_review_approved:
        problems.append("legal_review_approved must be true before production checkout")
    if s.stripe_checkout_enabled and not s.release_ready:
        problems.append("release_ready must be true before production checkout")
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
    if not s.stripe_webhook_secret:
        problems.append("stripe_webhook_secret is required for production commerce")
    if s.stripe_secret_key and not s.stripe_secret_key.startswith(("sk_live_", "rk_live_")):
        problems.append("stripe_secret_key must be a live Stripe key in production")
    if s.stripe_checkout_enabled:
        problems.extend(_checkout_configuration_problems(s))
    if s.email_provider not in ("console", "resend"):
        problems.append(f"email_provider={s.email_provider!r} is not a valid provider")
    elif s.email_provider != "resend":
        problems.append("email_provider must be 'resend' in production; console email is not deliverable")
    elif not s.resend_api_key:
        problems.append("email_provider is 'resend' but resend_api_key is empty")
    elif not _usable_sender_address(s.email_from_address):
        problems.append(
            "email_from_address must be a usable public address when email_provider='resend'"
        )
    if s.storage_backend != "s3":
        problems.append("storage_backend must be 's3' in production; local storage is not durable")
    problems.extend(_storage_configuration_problems(s))

    if problems:
        raise RuntimeError(
            "Refusing to start with environment=production and invalid configuration:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )


def _validate_staging_config(s: Settings) -> None:
    """Staging uses Stripe test credentials and public HTTPS endpoints."""
    if s.environment != "staging":
        return

    problems = []
    if not s.stripe_webhook_secret:
        problems.append("stripe_webhook_secret is required for staging commerce")
    if s.stripe_secret_key and not s.stripe_secret_key.startswith(("sk_test_", "rk_test_")):
        problems.append("stripe_secret_key must be a Stripe test key in staging")
    if s.stripe_checkout_enabled:
        problems.extend(_checkout_configuration_problems(s))

    for field_name, value in (
        ("nite_dsp_public_url", s.nite_dsp_public_url),
        ("nite_dsp_api_url", s.nite_dsp_api_url),
    ):
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1"}:
            problems.append(f"{field_name} must be a public HTTPS URL in staging; got {value!r}")

    if s.nite_dsp_support_email.endswith("@localhost.invalid"):
        problems.append(
            f"nite_dsp_support_email={s.nite_dsp_support_email!r} is still the dev placeholder"
        )

    if s.email_provider not in ("console", "resend"):
        problems.append(f"email_provider={s.email_provider!r} is not a valid provider")
    elif s.email_provider == "resend":
        if not s.resend_api_key:
            problems.append("email_provider is 'resend' but resend_api_key is empty")
        if not s.email_from_address or s.email_from_address.endswith("@localhost.invalid"):
            problems.append(
                f"email_from_address={s.email_from_address!r} is still the dev placeholder"
            )
        elif not _usable_sender_address(s.email_from_address):
            problems.append(
                "email_from_address must be a usable public address when email_provider='resend'"
            )

    storage_problems = _storage_configuration_problems(s)
    if storage_problems:
        problems.extend(storage_problems)

    if s.staging_customer_rehearsal:
        if s.storage_backend != "s3":
            problems.append(
                "staging_customer_rehearsal requires storage_backend='s3'"
            )
        if s.email_provider != "resend" or not s.resend_api_key:
            problems.append(
                "staging_customer_rehearsal requires email_provider='resend' and a resend_api_key"
            )

    if problems:
        raise RuntimeError(
            "Refusing to start with environment=staging and invalid configuration:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )


settings = Settings()
_validate_production_config(settings)
_validate_staging_config(settings)
