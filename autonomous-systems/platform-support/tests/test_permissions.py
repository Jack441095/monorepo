"""Tests for permissions, risk, and privacy class contracts."""

import pytest

from nite_ai.errors import ValidationError
from nite_ai.permissions import (
    ActionRisk,
    Permission,
    PrivacyClass,
    required_permission_for,
    validate_risk,
)


def test_risk_requires_permissions_for_elevated() -> None:
    with pytest.raises(ValidationError):
        validate_risk(ActionRisk.HIGH, ())
    validate_risk(ActionRisk.MEDIUM, ())  # fine
    validate_risk(ActionRisk.HIGH, (Permission.READ,))  # fine


def test_critical_requires_destructive_permission() -> None:
    with pytest.raises(ValidationError):
        validate_risk(ActionRisk.CRITICAL, (Permission.READ,))
    validate_risk(ActionRisk.CRITICAL, (Permission.DESTRUCTIVE,))


def test_privacy_to_permission_mapping() -> None:
    assert required_permission_for(PrivacyClass.PUBLIC) is None
    assert required_permission_for(PrivacyClass.PRIVATE_AUDIO) is Permission.PRIVATE_AUDIO
    assert required_permission_for(PrivacyClass.SECRET) is None  # never grantable


def test_secret_rejects_external_flow_by_design() -> None:
    # SECRET has no granting permission; documented invariance check.
    assert PrivacyClass.SECRET not in {
        p for p in PrivacyClass if required_permission_for(p) is not None
    }
