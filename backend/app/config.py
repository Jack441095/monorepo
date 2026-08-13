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

    # Email -- Section 63/64. "console" logs the email instead of sending it,
    # used for local/staging until a real transactional email provider is
    # configured. Never silently falls through to a real send in an
    # unconfigured environment.
    email_provider: str = "console"  # "console" | future: "postmark"/"ses"/etc.
    email_from_name: str = "NITE DSP"
    email_from_address: str = "noreply@localhost.invalid"

    # Downloads -- Section 51/52. Stands in for real object storage (S3-alike)
    # during staging; releases.storage_key is a path relative to this dir.
    mock_storage_dir: str = "./mock_storage"

    # Admin -- Section 73. Deliberately fail-closed: empty (the default)
    # means every admin endpoint refuses, full stop. This is the direct fix
    # for the exact gap docs/PRODUCTION_LICENSING_ARCHITECTURE.md flagged in
    # the dev licensing_server (POST /v1/admin/licenses has zero auth) --
    # that mistake must never be repeated here.
    admin_api_key: str = ""


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

    if problems:
        raise RuntimeError(
            "Refusing to start with environment=production and invalid configuration:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )


settings = Settings()
_validate_production_config(settings)
