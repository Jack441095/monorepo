"""NITE AI Platform bridge for Thursday.

Exposes one real, read-only Thursday capability through the shared
``nite_ai`` contracts:

    thursday.alerts.pending  ->  thursday.monitor.get_pending_alerts()

Boundary rules:
- nite_ai is imported lazily so Audio_Too never hard-depends on it;
- the platform never imports this module (inversion of control);
- no Thursday personality/session/orchestration semantics move to the platform;
- results are structured dicts from monitor.py — no prose parsing.
"""

from __future__ import annotations

from typing import Any

CAPABILITY_ID = "thursday.alerts.pending"
CAPABILITY_VERSION = "0.1.0"


def _nite_ai():
    import nite_ai  # lazy: Audio_Too runs without the platform installed

    return nite_ai


def build_capability_definition():
    nite_ai = _nite_ai()
    return nite_ai.CapabilityDefinition(
        capability_id=CAPABILITY_ID,
        version=CAPABILITY_VERSION,
        description=(
            "Read-only retrieval of Thursday's pending proactive alerts "
            "(real implementation: thursday.monitor.get_pending_alerts)"
        ),
        permissions=(nite_ai.Permission.READ,),
        risk=nite_ai.ActionRisk.LOW,
        provider_id="thursday.monitor",
    )


def handle_pending_alerts(request):
    """Platform CapabilityHandler wrapping the real Thursday implementation."""
    from thursday.monitor import get_pending_alerts  # real Thursday code

    nite_ai = _nite_ai()
    try:
        alerts: list[dict[str, Any]] = get_pending_alerts()
    except Exception as exc:  # translate native failure into shared taxonomy
        return nite_ai.AgentResult(
            request_id=request.request_id,
            status=nite_ai.ResultStatus.FAILED,
            error=nite_ai.AgentError(
                category=nite_ai.ErrorCategory.DEPENDENCY_UNAVAILABLE,
                message=f"thursday.monitor unavailable: {exc}",
                retryable=True,
                severity=nite_ai.Severity.MEDIUM,
                details={"native_module": "thursday.monitor"},
            ),
        )

    return nite_ai.AgentResult(
        request_id=request.request_id,
        status=nite_ai.ResultStatus.SUCCESS,
        result={
            "alert_count": len(alerts),
            # Structured passthrough of Thursday's own alert dicts.
            "alerts": [
                {k: v for k, v in alert.items() if isinstance(v, (str, int, float, bool))}
                for alert in alerts
            ],
            "trace_id": request.trace_id,
        },
    )


def register(adapter) -> None:
    """Register this capability with a nite_ai ProductAdapter."""
    nite_ai = _nite_ai()
    registry = nite_ai.capabilities.CapabilityRegistry()
    adapter.register(registry, build_capability_definition(), handle_pending_alerts)
    return registry


__all__ = [
    "CAPABILITY_ID",
    "build_capability_definition",
    "handle_pending_alerts",
    "register",
]
