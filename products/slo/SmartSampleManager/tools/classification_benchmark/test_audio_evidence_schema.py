import pytest

from audio_evidence_schema import (
    AudioEvidenceRecord,
    EvidenceClaim,
    PhysicalMeasurement,
    from_legacy_taxonomy,
)


def test_legacy_adapter_separates_identity_and_form_without_changing_legacy():
    record = from_legacy_taxonomy(
        content_id="sha256:abc",
        source_path="/library/Bass_128_Cm.wav",
        category="Bass",
        subcategory="Bass Loop",
        secondary_tags=["Loop", "Foley"],
        confidence=0.82,
        winning_evidence="FILENAME",
        taxonomy_version=2,
        classification_model_version=4,
    )
    assert record.identity.value == "Bass"
    assert record.form.value == "loop"
    assert record.family.value == "Bass"
    assert record.attributes["Foley"].source == "legacy_secondary_tag"
    assert record.legacy["subcategory"] == "Bass Loop"
    assert record.as_dict()["legacy"]["secondary_tags"] == ["Loop", "Foley"]


def test_unknown_legacy_result_stays_unknown():
    record = from_legacy_taxonomy(
        content_id="sha256:def", source_path="/library/mystery.wav",
        category="", subcategory="", secondary_tags=[], confidence=0.0,
        winning_evidence="UNKNOWN", taxonomy_version=2,
        classification_model_version=4,
    )
    assert record.identity.state == "unknown"
    assert record.family.state == "unknown"
    assert record.form.state == "unknown"


def test_measurement_provenance_is_required():
    record = AudioEvidenceRecord(
        content_id="sha256:ghi",
        source_path="/library/kick.wav",
        identity=EvidenceClaim("Kick", 0.99, "audio_model", "predicted"),
        measurements={"attack": PhysicalMeasurement(0.01, "seconds", "envelope_v1")},
    )
    assert record.as_dict()["measurements"]["attack"]["method"] == "envelope_v1"


def test_invalid_confidence_fails_closed():
    record = AudioEvidenceRecord(
        content_id="sha256:jkl",
        source_path="/library/snare.wav",
        identity=EvidenceClaim("Snare", 1.1, "audio_model", "predicted"),
    )
    with pytest.raises(ValueError, match="confidence"):
        record.validate()

