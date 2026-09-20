"""Unit tests for KENN Commercial Stem Packaging & Release Certificate (V6.0)."""

from __future__ import annotations

import pytest
from kenn.core.stem_packager import StemPackager, get_stem_packager


def test_standard_5_stem_grouping():
    """Validates that session tracks are accurately mapped into standard 5 delivery tiers."""
    packager = StemPackager()
    tracks = [
        {"name": "Kick 909", "volume": 0.90},
        {"name": "Snare Top", "volume": 0.85},
        {"name": "Hihat Closed", "volume": 0.70},
        {"name": "Sub 808 Bass", "volume": 0.88},
        {"name": "Electric Guitar Lead", "volume": 0.80},
        {"name": "Super Saw Synth", "volume": 0.78},
        {"name": "Main Lead Vocal", "volume": 0.85},
        {"name": "White Noise Sweep FX", "volume": 0.65},
    ]

    plan = packager.generate_stem_plan(tracks=tracks)

    assert plan.stem_count == 5
    tier_ids = [t.tier_id for t in plan.tiers]
    assert "01_DRUMS" in tier_ids
    assert "02_BASS" in tier_ids
    assert "03_INSTRUMENTS" in tier_ids
    assert "04_VOCALS" in tier_ids
    assert "05_FX" in tier_ids

    drums_tier = next(t for t in plan.tiers if t.tier_id == "01_DRUMS")
    assert "Kick 909" in drums_tier.track_names
    assert "Snare Top" in drums_tier.track_names

    bass_tier = next(t for t in plan.tiers if t.tier_id == "02_BASS")
    assert "Sub 808 Bass" in bass_tier.track_names

    vox_tier = next(t for t in plan.tiers if t.tier_id == "04_VOCALS")
    assert "Main Lead Vocal" in vox_tier.track_names


def test_stem_true_peak_validation():
    """Asserts stems satisfy <= -0.5 dBTP compliance gate."""
    packager = get_stem_packager()
    plan = packager.generate_stem_plan(tracks=[])

    assert plan.all_compliant is True
    for stem in plan.tiers:
        assert stem.peak_dbtp <= -0.5
        assert stem.dc_offset_clean is True


def test_master_delivery_certificate_sha256():
    """Asserts certificate contains valid cryptographic provenance and signature."""
    packager = StemPackager()
    meta = {
        "title": "Midnight Mirage",
        "artist": "Nite DSP",
        "bpm": 126.0,
        "key": "G Minor",
        "mqm_score": 92.4,
        "mqm_grade": "S",
    }
    plan = packager.generate_stem_plan(tracks=[], project_metadata=meta)
    cert = plan.certificate

    assert cert.song_title == "Midnight Mirage"
    assert cert.artist == "Nite DSP"
    assert cert.bpm == 126.0
    assert cert.musical_key == "G Minor"
    assert cert.mqm_score == 92.4
    assert cert.mqm_grade == "S"
    assert len(cert.sha256_provenance) == 64  # Valid SHA-256 length
    assert cert.signature.startswith("KENN-RELEASE-")

