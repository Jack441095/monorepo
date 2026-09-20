"""Stage 9.3 — Ableton Live Set (.als) exporter structural validation tests.

There is no Ableton Live installation available in this environment, so
these tests validate the only thing that *can* be checked without Live
itself: the exported .als gunzips to well-formed XML shaped like Ableton's
documented Live Set schema (Ableton root with MajorVersion/SchemaVersion,
LiveSet > Tracks > AudioTrack with Name/DeviceChain/Mixer, a MasterTrack
with a Limiter). This is NOT a round-trip import test — see
studio/audio_analysis/audio_analysis/integration/daw_integration.py's module
docstring for the specific approximations (dB-to-fader-position curve,
Compressor2/Eq8 parameter tag names) that have not been verified against a
real Ableton Live session.
"""

from __future__ import annotations

import gzip

from audio_analysis.integration import daw_integration as daw
from audio_analysis.mixdown.mix_decision_engine import BusMixConfig, MixPlan, StemMixConfig


def _sample_plan() -> MixPlan:
    stems = [
        StemMixConfig(
            stem_name="kick.wav",
            instrument="kick",
            gain_db=-2.5,
            pan=0.0,
            eq_bands=[
                {"type": "highpass", "frequency": 25.0, "q": 0.707, "gain_db": 0.0},
                {"type": "peaking", "frequency": 60.0, "q": 1.0, "gain_db": 1.5},
            ],
            compressor={"ratio": 4.0, "attack_ms": 20.0, "release_ms": 150.0, "threshold_db": -16.0, "makeup_gain_db": 0.0},
        ),
        StemMixConfig(
            stem_name="vocal.wav",
            instrument="vocal",
            gain_db=1.2,
            pan=0.0,
            reverb_send=0.12,
            reverb_type="plate",
            reverb_decay_s=1.6,
            compressor={"ratio": 3.5, "attack_ms": 10.0, "release_ms": 80.0, "threshold_db": -16.0, "makeup_gain_db": 0.0},
        ),
        StemMixConfig(stem_name="guitar.wav", instrument="guitar", gain_db=-5.0, pan=-0.35, stereo_width=0.65),
    ]
    bus = BusMixConfig(
        bus_compressor={"ratio": 2.5, "attack_ms": 30.0, "release_ms": 150.0, "threshold_db": -12.0, "makeup_gain_db": 0.0},
        limiter_ceiling_db=-1.0,
        saturation_drive_db=0.5,
        saturation_mix=0.4,
    )
    return MixPlan(stems=stems, bus=bus, genre="pop", target_lufs=-14.0, mix_goal="pop_vocal", decisions_log=["test"])


def test_als_bytes_are_gzip_and_well_formed_xml():
    plan = _sample_plan()
    als_bytes = daw.als_bytes_for_delivery(plan)
    xml_bytes = gzip.decompress(als_bytes)  # raises if not valid gzip
    assert xml_bytes.startswith(b"<?xml")
    assert b"<Ableton" in xml_bytes


def test_als_structural_validation_passes_all_checks():
    plan = _sample_plan()
    als_bytes = daw.als_bytes_for_delivery(plan)
    report = daw.validate_als_bytes(als_bytes)
    assert report["ok"], report
    assert report["checks"]["audio_track_count"] == 3
    assert report["checks"]["has_master_track"] is True
    assert report["checks"]["master_has_limiter"] is True
    assert not report["errors"]


def test_als_export_writes_a_real_file(tmp_path):
    plan = _sample_plan()
    out_path = daw.export_als(plan, tmp_path / "mixdown.als")
    assert out_path.exists()
    report = daw.validate_als_bytes(out_path.read_bytes())
    assert report["ok"], report


def test_als_rejects_garbage_input():
    report = daw.validate_als_bytes(b"not gzip data")
    assert report["ok"] is False
    assert report["errors"]


def test_pan_maps_directly_no_conversion():
    # Pan is documented (module docstring) as a direct -1..+1 mapping —
    # the one high-confidence conversion in this exporter.
    assert daw._pan_to_live_pan(-1.0) == -1.0
    assert daw._pan_to_live_pan(0.0) == 0.0
    assert daw._pan_to_live_pan(1.0) == 1.0
    assert daw._pan_to_live_pan(2.5) == 1.0  # clamped


def test_gain_conversion_is_monotonic_and_bounded():
    # Approximate curve (see module docstring) — only assert the invariants
    # that must hold for *any* reasonable fader curve: monotonic increasing,
    # bounded to [0, 1], and unity-ish around 0 dB.
    values = [daw._db_to_live_volume(db) for db in (-60, -24, -12, -6, 0, 3, 6)]
    assert values == sorted(values)
    assert all(0.0 <= v <= 1.0 for v in values)
    assert 0.7 < daw._db_to_live_volume(0.0) < 1.0
