"""NITE AI Platform bridge for KENN.

Exposes one real, read-only KENN audio-analysis capability through the shared
``nite_ai`` contracts:

    audio.mix.analyze  ->  mix_review.analyze_wav(file_bytes, filename)

Boundary rules:
- nite_ai imported lazily (no hard Audio_Too dependency);
- the platform never imports this module;
- all mix semantics stay in KENN — the bridge only *translates* the real
  analysis report's metrics dict into structured EvidenceItems with measured
  confidence; no values are invented, no Automix/write path is reachable.
"""

from __future__ import annotations

from typing import Any

CAPABILITY_ID = "audio.mix.analyze"
CAPABILITY_VERSION = "0.1.0"

# Metric keys promoted into evidence facts, with units. Kept deliberately
# small and explicit: only deterministic, numeric, well-understood metrics.
_EVIDENCE_METRICS: tuple[tuple[str, str], ...] = (
    ("peak_dbfs", "dBFS"),
    ("rms_dbfs", "dBFS"),
    ("lufs_integrated", "LUFS"),
    ("crest_factor_db", "dB"),
    ("spectral_centroid_hz", "Hz"),
    ("stereo_width", ""),
)


def _nite_ai():
    import nite_ai  # lazy

    return nite_ai


def build_capability_definition():
    nite_ai = _nite_ai()
    return nite_ai.CapabilityDefinition(
        capability_id=CAPABILITY_ID,
        version=CAPABILITY_VERSION,
        description=(
            "Read-only mix analysis over in-memory WAV bytes returning "
            "structured evidence (real implementation: "
            "audio_analysis.mix_review.analyze_wav)"
        ),
        permissions=(nite_ai.Permission.READ, nite_ai.Permission.PRIVATE_AUDIO),
        risk=nite_ai.ActionRisk.LOW,
        latency_class=nite_ai.LatencyClass.FAST_ANALYSIS,
        max_privacy_class=nite_ai.PrivacyClass.PRIVATE_AUDIO,
        provider_id="kenn.mix_review",
    )


def _metrics_of(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def to_evidence_packet(report: dict[str, Any], request_id: str):
    """Translate a real KENN report into a shared EvidencePacket.

    Only measured numeric metrics are promoted, each labelled
    ConfidenceKind.MEASURED with confidence 1.0-by-measurement convention
    (deterministic DSP output). Nothing is inferred here.
    """
    nite_ai = _nite_ai()
    from audio_analysis.mix_features import metric_float  # real KENN helper

    metrics = _metrics_of(report)
    facts = []
    for key, unit in _EVIDENCE_METRICS:
        value = metric_float(metrics.get(key))
        if value is None:
            continue
        facts.append(
            nite_ai.EvidenceItem(
                name=key,
                value=value,
                unit=unit,
                source="kenn.mix_review",
                confidence_kind=nite_ai.ConfidenceKind.MEASURED,
                confidence=1.0,
                analysis_version=str(report.get("analysis_version") or "mix_review/unknown"),
            )
        )
    return nite_ai.EvidencePacket(
        packet_id=f"evidence.mixreview.{request_id}",
        source="kenn.mix_review",
        facts=tuple(facts),
        limitations=(
            "single-file snapshot; no reference track comparison" ,
        ),
    )


def handle_mix_analyze(request):
    """Platform CapabilityHandler wrapping real KENN analyze_wav."""
    payload = request.payload or {}
    file_bytes = payload.get("wav_bytes")
    filename = str(payload.get("filename") or "mix.wav")
    nite_ai = _nite_ai()

    if not isinstance(file_bytes, (bytes, bytearray)) or not file_bytes:
        return nite_ai.AgentResult(
            request_id=request.request_id,
            status=nite_ai.ResultStatus.FAILED,
            error=nite_ai.AgentError(
                category=nite_ai.ErrorCategory.INVALID_INPUT,
                message="payload.wav_bytes must be non-empty bytes",
                retryable=False,
                user_facing=True,
            ),
        )

    from audio_analysis.mix_review import mix_review as real_kenn  # real KENN code

    try:
        report = real_kenn.analyze_wav(bytes(file_bytes), filename, light=True)
    except Exception as exc:
        return nite_ai.AgentResult(
            request_id=request.request_id,
            status=nite_ai.ResultStatus.FAILED,
            error=nite_ai.AgentError(
                category=nite_ai.ErrorCategory.TOOL_FAILURE,
                message=f"kenn mix analysis failed: {exc}",
                retryable=False,
                details={"native_module": "audio_analysis.mix_review"},
            ),
        )

    flags = report.get("flags") if isinstance(report.get("flags"), list) else []
    return nite_ai.AgentResult(
        request_id=request.request_id,
        status=nite_ai.ResultStatus.SUCCESS,
        result={
            "flag_count": len(flags),
            # Structured passthrough of KENN's own flag dicts (product-owned).
            "flags": [
                {k: v for k, v in f.items() if isinstance(v, (str, int, float, bool))}
                for f in flags[:20]
            ],
            "trace_id": request.trace_id,
        },
        evidence=to_evidence_packet(report, request.request_id),
    )


def register(adapter):
    nite_ai = _nite_ai()
    registry = nite_ai.capabilities.CapabilityRegistry()
    adapter.register(registry, build_capability_definition(), handle_mix_analyze)
    return registry


__all__ = [
    "CAPABILITY_ID",
    "build_capability_definition",
    "handle_mix_analyze",
    "register",
    "to_evidence_packet",
]
