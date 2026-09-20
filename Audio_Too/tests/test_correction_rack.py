"""Regression test for standalone Ableton correction-rack generation."""

from __future__ import annotations

import gzip

from audio_analysis.mix_review import mix_review

MOCK_REVIEW_ID = "test-review-uuid"
MOCK_REVIEW = {
    "id": MOCK_REVIEW_ID,
    "title": "My Track",
    "report_name": "test_report.json",
}

MOCK_REPORT = {
    "metrics": {
        "bands": {
            "sub": 0.20,
            "bass": 0.30,
            "low_mids": 0.15,
            "mids": 0.12,
            "presence": 0.10,
            "sibilance": 0.08,
            "air": 0.05,
        }
    },
    "reference": {
        "metrics": {
            "bands": {
                "sub": 0.10,
                "bass": 0.15,
                "low_mids": 0.20,
                "mids": 0.24,
                "presence": 0.15,
                "sibilance": 0.12,
                "air": 0.04,
            }
        }
    },
}


def test_generate_correction_rack_standalone(monkeypatch) -> None:
    monkeypatch.setattr(
        mix_review,
        "review_by_id",
        lambda review_id: MOCK_REVIEW if review_id == MOCK_REVIEW_ID else None,
    )
    monkeypatch.setattr(
        mix_review,
        "read_report",
        lambda report_name: MOCK_REPORT if report_name == "test_report.json" else {},
    )

    adg_bytes = mix_review.generate_correction_rack(MOCK_REVIEW_ID)

    assert adg_bytes is not None
    decompressed = gzip.decompress(adg_bytes).decode("utf-8")
    assert "<Ableton" in decompressed

