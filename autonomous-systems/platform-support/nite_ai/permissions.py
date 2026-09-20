"""Permission scopes, action risk levels, and privacy classes.

Machine contracts only — no auth UI, no enforcement runtime in Phase 1.
Derived from Thursday's PermissionScope/ActionRisk model and the platform
architecture privacy classes.
"""

from __future__ import annotations

from enum import Enum

from nite_ai.errors import ValidationError


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    NETWORK = "network"
    EXECUTE = "execute"
    PRIVATE_AUDIO = "private_audio"
    PRIVATE_PROJECT = "private_project"
    SEND_EXTERNAL = "send_external"
    DESTRUCTIVE = "destructive"


class ActionRisk(str, Enum):
    """Consequence ceiling of an operation (converged from Thursday ActionRisk)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def requires_elevated_permissions(self) -> bool:
        return self in {ActionRisk.HIGH, ActionRisk.CRITICAL}


class PrivacyClass(str, Enum):
    PUBLIC = "public"
    USER_TEXT = "user_text"
    PRIVATE_PROJECT = "private_project"
    PRIVATE_AUDIO = "private_audio"
    SECRET = "secret"


_PRIVACY_TO_MIN_PERMISSION: dict[PrivacyClass, Permission | None] = {
    PrivacyClass.PUBLIC: None,
    PrivacyClass.USER_TEXT: None,
    PrivacyClass.PRIVATE_PROJECT: Permission.PRIVATE_PROJECT,
    PrivacyClass.PRIVATE_AUDIO: Permission.PRIVATE_AUDIO,
    PrivacyClass.SECRET: None,  # SECRET data never leaves its origin; no permission grants it
}

# Permissions whose exercise implies data may leave the machine / be destroyed.
EXTERNAL_PERMISSIONS = frozenset({Permission.NETWORK, Permission.SEND_EXTERNAL})


def required_permission_for(privacy: PrivacyClass) -> Permission | None:
    """The permission a component must hold to touch data of this class."""
    return _PRIVACY_TO_MIN_PERMISSION[privacy]


def validate_risk(risk: ActionRisk, permissions: tuple[Permission, ...]) -> None:
    """HIGH/CRITICAL risk operations must declare explicit permissions."""
    if risk.requires_elevated_permissions and not permissions:
        raise ValidationError(
            f"{risk.value} risk operations must declare at least one permission"
        )
    if risk is ActionRisk.CRITICAL and Permission.DESTRUCTIVE not in permissions:
        raise ValidationError("critical risk operations must declare the destructive permission")


__all__ = [
    "ActionRisk",
    "EXTERNAL_PERMISSIONS",
    "Permission",
    "PrivacyClass",
    "required_permission_for",
    "validate_risk",
]
