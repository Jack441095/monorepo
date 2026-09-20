"""Live product integration tests: real Thursday + KENN capabilities through
the nite_ai platform. Skipped automatically if the platform package is not
installed (Audio_Too must remain runnable without it)."""

import io
import math
import struct
import wave

import pytest

pytest.importorskip("nite_ai")

from nite_ai.adapters import ProductAdapter  # noqa: E402
from nite_ai.capabilities import CapabilityRegistry  # noqa: E402
from nite_ai.contracts import AgentRequest, ResultStatus  # noqa: E402
from nite_ai.errors import ErrorCategory  # noqa: E402
from nite_ai.permissions import Permission  # noqa: E402


def make_request(capability_id, payload=None, granted=(Permission.READ,)):
    return AgentRequest(
        request_id="live-req-1",
        trace_id="live-trace-1",
        capability_id=capability_id,
        payload=payload or {},
        granted_permissions=tuple(granted),
    )


def synth_wav_bytes(seconds: float = 0.3, freq: float = 220.0) -> bytes:
    """Tiny synthetic mono WAV — no owner audio, stdlib only."""
    rate = 16000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            sample = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", sample)
        w.writeframes(bytes(frames))
    return buf.getvalue()


# ---------------------------------------------------------------- Thursday

def test_thursday_live_capability_through_platform():
    from thursday.platform_bridge import CAPABILITY_ID, handle_pending_alerts

    adapter = ProductAdapter("thursday")
    registry = CapabilityRegistry()
    adapter.register(registry, __import__(
        "thursday.platform_bridge", fromlist=["build_capability_definition"]
    ).build_capability_definition(), handle_pending_alerts)

    result = adapter.dispatch(make_request(CAPABILITY_ID))
    assert result.ok is True
    assert result.status == ResultStatus.SUCCESS
    assert result.request_id == "live-req-1"
    assert result.result["trace_id"] == "live-trace-1"
    assert isinstance(result.result["alert_count"], int)
    # read-only capability: no write permissions required or exercised
    assert registry.lookup(CAPABILITY_ID).risk.value == "low"


def test_thursday_adapter_permission_enforcement():
    from thursday.platform_bridge import CAPABILITY_ID, handle_pending_alerts, build_capability_definition

    adapter = ProductAdapter("thursday")
    adapter.register(CapabilityRegistry(), build_capability_definition(), handle_pending_alerts)
    denied = adapter.dispatch(make_request(CAPABILITY_ID, granted=()))
    assert not denied.ok and denied.error.category == ErrorCategory.PERMISSION_DENIED


# ------------------------------------------------------------------- KENN

def test_kenn_live_analysis_with_evidence_preserved():
    from kenn.platform_bridge import (
        CAPABILITY_ID,
        build_capability_definition,
        handle_mix_analyze,
    )

    adapter = ProductAdapter("kenn")
    registry = CapabilityRegistry()
    adapter.register(registry, build_capability_definition(), handle_mix_analyze)

    request = make_request(
        CAPABILITY_ID,
        payload={"wav_bytes": synth_wav_bytes(), "filename": "synth-tone.wav"},
        granted=(Permission.READ, Permission.PRIVATE_AUDIO),
    )
    result = adapter.dispatch(request)
    assert result.ok is True, getattr(result.error, "message", "unknown failure")
    assert result.request_id == "live-req-1"

    packet = result.evidence
    assert packet is not None and packet.source == "kenn.mix_review"
    measured = [f for f in packet.facts if f.confidence_kind.value == "measured"]
    assert measured, "at least one measured DSP fact expected"
    for fact in measured:
        assert fact.confidence_kind.value == "measured"
        assert fact.source == "kenn.mix_review"
    names = {f.name for f in packet.facts}
    assert "peak_dbfs" in names  # deterministic DSP metric present
    # no invented confidence: every fact is measurement-labelled
    assert all(f.confidence == 1.0 for f in packet.facts)


def test_kenn_adapter_rejects_missing_audio_structurally():
    from kenn.platform_bridge import CAPABILITY_ID, build_capability_definition, handle_mix_analyze

    adapter = ProductAdapter("kenn")
    adapter.register(CapabilityRegistry(), build_capability_definition(), handle_mix_analyze)
    bad = adapter.dispatch(make_request(CAPABILITY_ID, payload={},
                                       granted=(Permission.READ, Permission.PRIVATE_AUDIO)))
    assert not bad.ok
    assert bad.error.category == ErrorCategory.INVALID_INPUT


def test_no_automix_write_path_in_adapted_capability():
    """The adapted KENN surface exposes analysis only."""
    import kenn.platform_bridge as bridge

    src = open(bridge.__file__).read()
    assert "automix" not in src.lower().replace("no automix/write path", "")
    caps = bridge.build_capability_definition()
    assert all(p.value in {"read", "private_audio"} for p in caps.permissions)


def test_platform_importable_without_products():
    import subprocess
    import sys

    code = "import sys; import nite_ai; print(sorted(m for m in sys.modules if m.split('.')[0] in {'thursday','kenn'}))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0
    assert out.stdout.strip().endswith("[]")
