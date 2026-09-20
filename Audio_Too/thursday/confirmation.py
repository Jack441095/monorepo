"""Backwards-compat shim — canonical implementation moved to nite_core."""

from nite_core.confirmation import (  # noqa: F401
    DEFAULT_TTL_SECONDS,
    issue_confirmation,
    verify_confirmation,
)
