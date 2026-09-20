"""Tests for model contracts, registry, routing, privacy enforcement, fallback."""

import pytest

from nite_ai.errors import ErrorCategory
from nite_ai.models import (
    CostClass,
    ModelCapability,
    ModelConstraints,
    ModelRequest,
    ProviderDefinition,
    ProviderRegistry,
    RoutingDecision,
    rank_candidates,
)
from nite_ai.models.mocks import EchoProvider, FailingProvider
from nite_ai.permissions import PrivacyClass


def local_provider(pid="ollama.local", tier=PrivacyClass.PRIVATE_PROJECT):
    return ProviderDefinition(
        provider_id=pid,
        version="1.0.0",
        capabilities=(ModelCapability.TEXT_REASONING,),
        local=True,
        max_privacy_class=tier,
    )


def remote_provider(pid="openai.remote", tier=PrivacyClass.PUBLIC):
    return ProviderDefinition(
        provider_id=pid,
        version="1.0.0",
        capabilities=(ModelCapability.TEXT_REASONING,),
        local=False,
        max_privacy_class=tier,
        cost_class=CostClass.LOW,
    )


def make_request(**overrides):
    fields = dict(
        request_id="mr-1",
        trace_id="trace-1",
        messages=({"role": "user", "content": "hello"},),
    )
    fields.update(overrides)
    return ModelRequest(**fields)


def test_constraints_normalise_local_only() -> None:
    c = ModelConstraints(local_only=True)
    assert c.remote_allowed is False


def test_provider_privacy_tier() -> None:
    p = local_provider(tier=PrivacyClass.USER_TEXT)
    assert p.can_handle_privacy(PrivacyClass.USER_TEXT)
    assert not p.can_handle_privacy(PrivacyClass.PRIVATE_AUDIO)


def test_registry_duplicate_rejected() -> None:
    reg = ProviderRegistry()
    reg.register(local_provider())
    with pytest.raises(Exception):
        reg.register(local_provider())
    assert len(reg) == 1


def test_registry_filters_by_local_and_capability() -> None:
    reg = ProviderRegistry()
    reg.register(local_provider())
    reg.register(remote_provider())
    assert [d.provider_id for d in reg.filter(local=True)] == ["ollama.local"]
    assert len(reg.filter(capability=ModelCapability.TEXT_REASONING)) == 2
    assert reg.filter(capability=ModelCapability.EMBEDDING) == ()


def test_routing_prefers_local_then_cheap() -> None:
    reg = ProviderRegistry()
    reg.register(remote_provider("a.remote"))
    reg.register(local_provider("b.local"))
    decision = rank_candidates(reg, make_request(constraints=ModelConstraints()))
    # local-first wins even though the remote sorts first alphabetically at same cost? local flag dominates.
    assert decision.candidate_order[0] == "b.local"


def test_private_audio_never_routes_to_remote() -> None:
    """Core privacy guarantee: sensitive data cannot reach a low-tier remote."""
    reg = ProviderRegistry()
    reg.register(remote_provider())  # PUBLIC tier only
    constraints = ModelConstraints(
        allowed_privacy_classes=frozenset({PrivacyClass.PRIVATE_AUDIO})
    )
    decision = rank_candidates(reg, make_request(constraints=constraints))
    assert decision.candidate_order == ()
    assert ("openai.remote", "privacy class exceeds provider tier") in decision.rejected


def test_local_only_excludes_remote_from_fallback() -> None:
    reg = ProviderRegistry()
    failing_local = FailingProvider(local_provider(), retryable=True)
    echo_remote = EchoProvider(remote_provider())
    reg.register(failing_local.definition)
    reg.register(echo_remote.definition)
    from nite_ai.models.routing import ModelRouter

    router = ModelRouter(reg, {failing_local.definition.provider_id: failing_local,
                               echo_remote.definition.provider_id: echo_remote})
    result = router.route(make_request(constraints=ModelConstraints(local_only=True)))
    assert not result.ok
    assert failing_local.calls == 1
    assert echo_remote.calls == 0  # never touched — privacy/local-only held under fallback


def test_bounded_fallback_reports_provenance() -> None:
    reg = ProviderRegistry()
    failing = FailingProvider(local_provider("p1.local"), message="boom")
    ok = EchoProvider(local_provider("p2.local"))
    reg.register(failing.definition)
    reg.register(ok.definition)
    from nite_ai.models.routing import ModelRouter

    router = ModelRouter(reg, {"p1.local": failing, "p2.local": ok})
    result = router.route(make_request(), max_attempts=2)
    assert result.ok and result.content == "echo:hello"
    assert result.execution.fallback_from_provider_id == "p1.local"
    assert "boom" in result.execution.fallback_reason
    assert failing.calls == 1 and ok.calls == 1


def test_non_retryable_failure_stops_chain() -> None:
    reg = ProviderRegistry()
    fatal = FailingProvider(local_provider("f.local"), retryable=False)
    other = EchoProvider(local_provider("o.local"))
    reg.register(fatal.definition)
    reg.register(other.definition)
    from nite_ai.models.routing import ModelRouter

    router = ModelRouter(reg, {"f.local": fatal, "o.local": other})
    result = router.route(make_request())
    assert not result.ok
    assert other.calls == 0


def test_pinned_unavailable_does_not_widen_search() -> None:
    reg = ProviderRegistry()
    reg.register(remote_provider())
    req = make_request(preferred_provider_id="does.not.exist")
    decision = rank_candidates(reg, req)
    assert decision.candidate_order == () and decision.pinned_unavailable


def test_circuit_opens_after_consecutive_failures() -> None:
    reg = ProviderRegistry()
    reg.register(local_provider("c.local"))
    for _ in range(3):
        reg.report_failure("c.local")
    assert reg.status("c.local").healthy is False
    assert reg.filter() == ()  # excluded from compliant candidates
    reg.report_success("c.local")
    assert reg.status("c.local").healthy is True
