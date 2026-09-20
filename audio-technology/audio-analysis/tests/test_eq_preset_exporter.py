"""Unit tests for EQ Preset Exporter."""

import json
from studio.audio_analysis.audio_analysis.export.eq_preset_exporter import (
    EQPresetExporter,
    ExportableBand,
)


def test_fabfilter_export():
    exporter = EQPresetExporter()
    exporter.add_band("peaking", 1000.0, gain_db=-3.5, q=1.2)
    exporter.add_band("highshelf", 8000.0, gain_db=2.0, q=0.707)

    payload = exporter.export_fabfilter_json()
    data = json.loads(payload)

    assert data["plugin"] == "FabFilter Pro-Q 3"
    assert data["band_count"] == 2
    assert data["bands"][0]["shape"] == "Bell"
    assert data["bands"][0]["gain_db"] == -3.5
    assert data["bands"][1]["shape"] == "HighShelf"


def test_ableton_eq_eight_export():
    exporter = EQPresetExporter()
    exporter.add_band("highpass", 80.0, q=0.707)
    exporter.add_band("peaking", 2500.0, gain_db=1.5, q=2.0)

    data = exporter.export_ableton_eq_eight_dict()

    assert data["device"] == "Eq8"
    assert data["band_count"] == 8
    assert data["bands"][0]["on"] is True
    assert data["bands"][0]["mode"] == "Highpass48"
    assert data["bands"][1]["mode"] == "Cutoff"
    assert data["bands"][7]["on"] is False  # Padding band


def test_svg_curve_export():
    exporter = EQPresetExporter()
    exporter.add_band("peaking", 1000.0, gain_db=4.0, q=1.0)
    svg = exporter.export_svg_curve(width=400, height=200)

    assert "<svg" in svg
    assert "</svg>" in svg
    assert "stroke=\"#00f0ff\"" in svg
