"""Stage 11.4 — mastering targets config: numeric targets vs. real standards.

Every assertion below cites the same source named in the module's
docstring/``MasteringTarget.citation`` field, so this test doubles as a
second, independent place those citations are checked against the actual
numbers shipped in the config.
"""

from __future__ import annotations

import pytest

from audio_analysis.export.mastering_targets import (
    BROADCAST,
    CD,
    MASTERING_TARGETS,
    STREAMING,
    VINYL,
    get_mastering_target,
    target_as_dict,
)


def test_all_four_required_contexts_present():
    assert set(MASTERING_TARGETS) == {"streaming", "cd", "vinyl", "broadcast"}


def test_streaming_matches_cross_platform_convention():
    # Spotify loudness-normalization spec + iZotope's streaming mastering
    # guide: -14 LUFS integrated, -1 dBTP true peak ceiling is documented
    # as the safe cross-platform target for Spotify/YouTube/Tidal.
    assert STREAMING.integrated_lufs_target == pytest.approx(-14.0)
    assert STREAMING.true_peak_ceiling_dbtp == pytest.approx(-1.0)
    assert STREAMING.is_formal_standard is False


def test_broadcast_matches_ebu_r128():
    # EBU R128 (2014): Programme Loudness -23.0 LUFS integrated, +/-0.5 LU
    # tolerance; Maximum True Peak Level -1.0 dBTP.
    assert BROADCAST.integrated_lufs_target == pytest.approx(-23.0)
    assert BROADCAST.true_peak_ceiling_dbtp == pytest.approx(-1.0)
    assert BROADCAST.tolerance_lu == pytest.approx(0.5)
    assert BROADCAST.is_formal_standard is True
    assert "EBU R128" in BROADCAST.standard_name


def test_cd_matches_red_book_container_and_documented_convention():
    # IEC 60908 (Red Book) mandates no loudness target ("as mastered") --
    # only the 16-bit/44.1kHz PCM container. -9 LUFS / -0.3 dBTP below are
    # documented mastering-industry convention, not part of IEC 60908
    # itself, and the target correctly flags that with is_formal_standard.
    assert CD.integrated_lufs_target == pytest.approx(-9.0)
    assert CD.true_peak_ceiling_dbtp == pytest.approx(-0.3)
    assert CD.is_formal_standard is False


def test_vinyl_has_correct_physical_cutting_constraints():
    # Vinyl mastering conventions (Masterdisk/Sage Audio/Furnace Mfg):
    # mono-sum bass below ~150 Hz (cutting stylus reproduces L-R
    # difference as vertical groove modulation -- excessive out-of-phase
    # bass de-rails the stylus), high-frequency roll-off from ~15 kHz, and
    # sibilance de-essing focused on ~3-10 kHz (cutting-head mistracking).
    assert VINYL.mono_below_hz == pytest.approx(150.0)
    assert VINYL.high_freq_rolloff_start_hz == pytest.approx(15000.0)
    assert VINYL.sibilance_deess_band_hz == (3000.0, 10000.0)
    # Vinyl runs quieter than CD/streaming to preserve cuttable dynamic range.
    assert VINYL.integrated_lufs_target < CD.integrated_lufs_target
    assert VINYL.is_formal_standard is False


def test_vinyl_true_peak_ceiling_is_within_documented_headroom_range():
    # Furnace Mfg / Gearspace consensus: safe pre-master peak roughly
    # -3 to -6 dBFS/dBTP for a vinyl cut.
    assert -6.0 <= VINYL.true_peak_ceiling_dbtp <= -3.0


def test_get_mastering_target_is_case_insensitive_and_validates():
    assert get_mastering_target("STREAMING").context == "streaming"
    assert get_mastering_target(" vinyl ").context == "vinyl"
    with pytest.raises(ValueError, match="Unknown mastering context"):
        get_mastering_target("cassette")


def test_target_as_dict_round_trips_all_fields():
    d = target_as_dict(VINYL)
    assert d["context"] == "vinyl"
    assert d["mono_below_hz"] == 150.0
    assert d["sibilance_deess_band_hz"] == [3000.0, 10000.0]
    assert "Masterdisk" in d["citation"] or "Sage Audio" in d["citation"]


def test_every_target_cites_a_named_source():
    for target in MASTERING_TARGETS.values():
        assert target.citation and len(target.citation) > 20
        assert target.standard_name
