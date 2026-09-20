"""In-process provider registry (Phase 2C).

Static definitions + dynamic status. No database, network, or plugin system.
"""

from __future__ import annotations

from nite_ai.errors import DuplicateRegistrationError, ValidationError
from nite_ai.models.contracts import (
    ModelCapability,
    ProviderDefinition,
    ProviderStatus,
)
from nite_ai.permissions import PrivacyClass


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderDefinition] = {}
        self._status: dict[str, ProviderStatus] = {}

    def register(self, definition: ProviderDefinition) -> None:
        if definition.provider_id in self._providers:
            raise DuplicateRegistrationError(definition.provider_id, kind="provider")
        self._providers[definition.provider_id] = definition
        self._status[definition.provider_id] = ProviderStatus(definition.provider_id)

    def get(self, provider_id: str) -> ProviderDefinition:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise ValidationError(f"unknown provider: {provider_id}") from None

    def status(self, provider_id: str) -> ProviderStatus:
        try:
            return self._status[provider_id]
        except KeyError:
            raise ValidationError(f"unknown provider: {provider_id}") from None

    def report_failure(self, provider_id: str, detail: str = "") -> ProviderStatus:
        s = self.status(provider_id)
        new = ProviderStatus(
            provider_id=provider_id,
            healthy=s.consecutive_failures < 2,  # circuit opens at 3 consecutive failures
            detail=detail,
            consecutive_failures=s.consecutive_failures + 1,
        )
        self._status[provider_id] = new
        return new

    def report_success(self, provider_id: str) -> ProviderStatus:
        new = ProviderStatus(provider_id=provider_id, healthy=True, consecutive_failures=0)
        self._status[provider_id] = new
        return new

    def enumerate(self) -> tuple[ProviderDefinition, ...]:  # noqa: A003
        return tuple(sorted(self._providers.values(), key=lambda d: d.provider_id))

    def filter(
        self,
        *,
        capability: ModelCapability | None = None,
        local: bool | None = None,
        max_privacy_class: PrivacyClass | None = None,
        available_only: bool = True,
    ) -> tuple[ProviderDefinition, ...]:
        order = list(PrivacyClass)
        out = []
        for d in self.enumerate():
            if capability is not None and capability not in d.capabilities:
                continue
            if local is not None and d.local is not local:
                continue
            if (
                max_privacy_class is not None
                and order.index(d.max_privacy_class) < order.index(max_privacy_class)
            ):
                continue
            if available_only and (not d.available or not self.status(d.provider_id).healthy):
                continue
            out.append(d)
        return tuple(out)

    def __len__(self) -> int:
        return len(self._providers)
