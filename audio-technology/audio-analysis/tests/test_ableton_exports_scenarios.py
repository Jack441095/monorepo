"""Tests for ableton_exports.py — Ableton correction rack generation.

Covers:
- generate_correction_rack()     — 3 tests
"""

from __future__ import annotations

import gzip

from audio_analysis.integration.ableton_exports import generate_correction_rack


class TestGenerateCorrectionRack:

    def test_none_for_invalid_review(self):
        """Review not found → None."""
        result = generate_correction_rack("nonexistent", review_lookup=lambda rid: None, report_reader=lambda rn: {})
        assert result is None

    def test_returns_gzipped_xml(self):
        """Valid review → gzipped XML string."""
        def lookup(rid):
            return {"report_name": "report.json"}

        def reader(rn):
            return {
                "metrics": {
                    "bands": {"sub": 0.20, "bass": 0.15, "low_mids": 0.15, "mids": 0.25, "presence": 0.10, "sibilance": 0.05, "air": 0.10},
                },
                "reference": {
                    "metrics": {"bands": {"sub": 0.15, "bass": 0.15, "low_mids": 0.15, "mids": 0.25, "presence": 0.15, "sibilance": 0.08, "air": 0.07}},
                },
            }

        result = generate_correction_rack("r1", review_lookup=lookup, report_reader=reader)
        assert result is not None
        assert isinstance(result, bytes)

        # Verify it's valid gzip with XML
        decompressed = gzip.decompress(result).decode("utf-8")
        assert "<?xml" in decompressed
        assert "<Eq8>" in decompressed

    def test_bands_without_reference(self):
        """No reference bands → uses 0.15 defaults for ref."""
        def lookup(rid):
            return {"report_name": "report.json"}

        def reader(rn):
            return {"metrics": {"bands": {"sub": 0.20}}}  # ref not set

        result = generate_correction_rack("r1", review_lookup=lookup, report_reader=reader)
        assert result is not None
        decompressed = gzip.decompress(result).decode("utf-8")
        # Should have EQ8 bands
        assert "Frequency" in decompressed
