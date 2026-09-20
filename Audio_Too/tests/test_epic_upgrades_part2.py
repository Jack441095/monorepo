"""Tests for Mix Review Lab Epic Upgrades Part 2 backend features."""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

# Add Website and audio_analysis_tool directories to path
BUSINESS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BUSINESS_ROOT / "server" / "app"))
sys.path.insert(0, str(BUSINESS_ROOT / "studio" / "audio_analysis"))

from audio_analysis.mix_review import mix_review  # noqa: E402


def test_generate_correction_rack(monkeypatch) -> None:
    # Setup mock data for review and report
    mock_review_id = "test-review-uuid"
    mock_review = {
        "id": mock_review_id,
        "title": "My Track",
        "report_name": "test_report.json"
    }

    mock_report = {
        "metrics": {
            "bands": {
                "sub": 0.20,
                "bass": 0.30,
                "low_mids": 0.15,
                "mids": 0.12,
                "presence": 0.10,
                "sibilance": 0.08,
                "air": 0.05
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
                    "air": 0.04
                }
            }
        }
    }

    monkeypatch.setattr(mix_review, "review_by_id", lambda rid: mock_review if rid == mock_review_id else None)
    monkeypatch.setattr(mix_review, "read_report", lambda rname: mock_report if rname == "test_report.json" else {})

    # Generate corrective Ableton device rack
    adg_bytes = mix_review.generate_correction_rack(mock_review_id)
    assert adg_bytes is not None

    # Decompress using gzip and check string content
    decompressed = gzip.decompress(adg_bytes).decode("utf-8")

    # Assert root tag and schema attributes
    assert "<Ableton" in decompressed
    assert 'Creator="Ableton Live 11"' in decompressed

    # Band 0 (Sub: 30Hz): mix=0.20, ref=0.10. gain_db = 10 * log10(0.10/0.20) = -3.01 dB
    # Band 2 (Low Mids: 280Hz): mix=0.15, ref=0.20. gain_db = 10 * log10(0.20/0.15) = 1.25 dB
    assert 'Frequency Value="30.0"' in decompressed
    assert 'Gain Value="-3.01"' in decompressed or 'Gain Value="-3.00"' in decompressed
    assert 'Frequency Value="280.0"' in decompressed
    assert 'Gain Value="1.25"' in decompressed or 'Gain Value="1.24"' in decompressed


def test_analyze_stems_masking_calculation() -> None:
    # Define two dummy stems with distinct frequency properties
    stems = [
        {
            "name": "Kick.wav",
            "file_bytes": b""
        },
        {
            "name": "Vocal.wav",
            "file_bytes": b""
        }
    ]

    result = mix_review.analyze_stems_masking(stems)
    assert "stems" in result
    assert "masking_matrix" in result

    stems_list = result["stems"]
    assert len(stems_list) == 2
    assert stems_list[0]["name"] == "Kick"
    assert stems_list[1]["name"] == "Vocal"

    # Kick should have dominant low/bass frequencies based on fallback classifier
    assert stems_list[0]["bands"]["sub"] > stems_list[1]["bands"]["sub"]

    # Check masking matrix values
    matrix = result["masking_matrix"]
    assert matrix["Kick"]["Kick"] == 1.0
    assert matrix["Vocal"]["Vocal"] == 1.0
    
    # Overlap between Kick and Vocal fallback classification should be round-tripped
    overlap_kv = matrix["Kick"]["Vocal"]
    assert 0.0 <= overlap_kv <= 1.0


def test_handle_stems_upload_endpoint() -> None:
    # Test upload with empty files parameter
    bad_result = mix_review.handle_stems_upload("multipart/form-data; boundary=boundary", b"")
    assert bad_result["ok"] is False
    assert "No stems uploaded" in bad_result["error"]
