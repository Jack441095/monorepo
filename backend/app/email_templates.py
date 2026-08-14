"""
Production email content -- Phase 5.5, Section 19-20.

Every template returns (subject, body) as plain text (the "console" email
provider logs plain text; a future real provider can add HTML rendering on
top of the same subject/body without changing callers). All links are built
from `settings.nite_dsp_public_url`/`nite_dsp_api_url` -- never hardcoded,
never localhost outside local development (config.py's production
validator already refuses to start if those settings still point at
localhost in production). NITE DSP is always the sender brand; Smart
Sample Manager is always the product name, matching the approved identity
(docs/FINAL_PRODUCT_IDENTITY.md).

Not every template here has a live trigger yet -- e.g. `trial_started` has
no trial-issuance endpoint (Phase 4 correctly deferred building one; see
docs/PHASE_5_5_FINAL_SYNTHESIS.md). Writing the template content ahead of
the feature is not the same as building the feature speculatively -- it's
content, wired in the moment the feature exists, not a new code path.
"""
from __future__ import annotations

from .config import settings

_SIGNOFF = "\n\n-- NITE DSP"


def _account_url() -> str:
    return f"{settings.nite_dsp_public_url}/account"


def magic_link(raw_token: str, ttl_seconds: int) -> tuple[str, str]:
    link = f"{settings.nite_dsp_public_url}/auth/verify?token={raw_token}"
    minutes = ttl_seconds // 60
    body = (
        f"Click below to sign in to your NITE DSP account (expires in {minutes} minutes):\n"
        f"{link}\n\n"
        "If you didn't request this, you can safely ignore this email -- no account changes "
        "were made." + _SIGNOFF
    )
    return "Your NITE DSP sign-in link", body


def beta_invite(license_key: str, product_name: str, expires_at_iso: str | None) -> tuple[str, str]:
    expiry_note = f"\nThis beta access expires on {expires_at_iso}." if expires_at_iso else ""
    body = (
        f"You've been invited to the {product_name} private beta.\n\n"
        f"Your license key: {license_key}\n\n"
        f"Sign in at {_account_url()} with this email address, then download and activate "
        f"{product_name} from your account.{expiry_note}\n\n"
        "Thanks for helping us test -- questions or issues, just reply to this email."
        + _SIGNOFF
    )
    return f"You're invited to the {product_name} private beta", body


def beta_entitlement_issued(license_key: str, product_name: str, expires_at_iso: str | None) -> tuple[str, str]:
    expiry_note = f" Access expires on {expires_at_iso}." if expires_at_iso else ""
    body = (
        f"Your {product_name} beta access is ready.\n\n"
        f"License key: {license_key}\n"
        f"Manage your license at {_account_url()}.{expiry_note}"
        + _SIGNOFF
    )
    return f"Your {product_name} beta access is ready", body


def purchase_confirmation(product_name: str, amount_display: str, license_key: str) -> tuple[str, str]:
    body = (
        f"Thanks for purchasing {product_name}!\n\n"
        f"Amount charged: {amount_display}\n"
        f"License key: {license_key}\n\n"
        f"Download and activate from your account: {_account_url()}"
        + _SIGNOFF
    )
    return f"Your {product_name} purchase is complete", body


def trial_started(product_name: str, expires_at_iso: str) -> tuple[str, str]:
    body = (
        f"Your {product_name} trial has started and is active until {expires_at_iso}.\n\n"
        f"Manage your trial at {_account_url()}."
        + _SIGNOFF
    )
    return f"Your {product_name} trial has started", body


def license_ready(product_name: str, license_key: str) -> tuple[str, str]:
    body = (
        f"Your {product_name} license is ready.\n\n"
        f"License key: {license_key}\n"
        f"Activate it from your account: {_account_url()}"
        + _SIGNOFF
    )
    return f"Your {product_name} license is ready", body


def refund_confirmation(product_name: str, amount_display: str) -> tuple[str, str]:
    body = (
        f"Your refund for {product_name} ({amount_display}) has been processed.\n\n"
        "If you didn't request this refund, please reply to this email right away."
        + _SIGNOFF
    )
    return f"Your {product_name} refund is confirmed", body


def new_sign_in_notice(approx_time_iso: str) -> tuple[str, str]:
    """Not wired to a trigger yet -- magic-link sign-in is itself the
    account-recovery mechanism (no separate password to reset), so there is
    no distinct "recovery" flow. This covers the adjacent case Section 19
    asks for: notifying an account owner that a sign-in happened, for
    whenever session/device tracking is built."""
    body = (
        f"Your NITE DSP account was signed into at approximately {approx_time_iso}.\n\n"
        "If this wasn't you, no password exists to reset -- simply don't use any sign-in "
        "link you didn't request, and contact support if you're concerned."
        + _SIGNOFF
    )
    return "New sign-in to your NITE DSP account", body
