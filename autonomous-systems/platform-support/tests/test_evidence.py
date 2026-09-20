"""Tests for evidence contracts: provenance, confidence kinds, serialization."""

import json

import pytest

from nite_ai.contracts import ConfidenceKind, EvidenceItem, EvidencePacket
from nite_ai.errors import ValidationError


def test_packet_payload_round_trip() -> None:
    item = EvidenceItem(
        name="low_mid_excess_db",
        value=3.2,
        unit="dB",
        source="kenn.mix_review",
        confidence_kind=ConfidenceKind.MEASURED,
        confidence=0.95,
        analysis_version="features-2026.08.1",
    )
    packet = EvidencePacket(
        packet_id="evidence.mixreview.001",
        source="kenn.mix_review",
        facts=(item,),
        limitations=("single-channel snapshot",),
    )
    d = packet.payload()
    text = json.dumps(d, sort_keys=True)
    assert json.loads(text) == d  # deterministic
    assert d["facts"][0]["confidence_kind"] == "measured"


def test_confidence_requires_kind() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(name="x", value=1.0, confidence=0.9)


def test_confidence_range_enforced() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(name="x", value=1.0, confidence=1.5, confidence_kind=ConfidenceKind.MEASURED)


def test_reasoning_confidence_distinct_from_measured() -> None:
    measured = EvidenceItem(name="a", value=1, confidence=0.9, confidence_kind=ConfidenceKind.MEASURED)
    reasoned = EvidenceItem(name="b", value="masking", confidence=0.7, confidence_kind=ConfidenceKind.REASONING)
    assert measured.confidence_kind is not reasoned.confidence_kind


def test_packet_id_validation() -> None:
    with pytest.raises(ValidationError):
        EvidencePacket(packet_id="Bad ID!", source="src")
    with pytest.raises(ValidationError):
        EvidencePacket(packet_id="ok.id.1", source="")
