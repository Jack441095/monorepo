"""Unit tests for Genre-Aware Target Profiles and Intelligent Track Taxonomy Classifier."""

from kenn.core.genre_profiles import (
    get_genre_profile,
    detect_genre_from_query,
    GENRE_PROFILES,
    DEFAULT_GENRE_PROFILE,
)
from kenn.core.track_classifier import (
    classify_track_name,
    analyze_session_arrangement,
    ROLE_CLASSIFICATIONS,
)


def test_genre_profile_lookup():
    hiphop = get_genre_profile("hip_hop")
    assert hiphop.genre == "hip_hop"
    assert hiphop.target_lufs == -9.0
    assert hiphop.sub_bass_weight == "heavy"

    acoustic = get_genre_profile("acoustic_folk")
    assert acoustic.genre == "acoustic_folk"
    assert acoustic.target_lufs == -16.0
    assert acoustic.target_crest_range_db == (12.0, 18.0)

    default_prof = get_genre_profile("unknown_genre")
    assert default_prof == DEFAULT_GENRE_PROFILE


def test_detect_genre_from_query():
    assert detect_genre_from_query("How do I mix heavy 808s in a trap beat?") == "hip_hop"
    assert detect_genre_from_query("What compression ratio should I use for EDM dance synth pads?") == "edm_pop"
    assert detect_genre_from_query("How do I get punchy drums in a heavy metal track?") == "rock_metal"
    assert detect_genre_from_query("What's the best LUFS target for an acoustic folk album?") == "acoustic_folk"
    assert detect_genre_from_query("How to set up a master limiter?") is None


def test_detect_genre_from_query_covers_the_remaining_two_genre_profiles():
    """GENRE_PROFILES has 6 keys; the test above only ever exercised 4 of
    them (plus the None case) -- rnb_soul and cinematic_game had no query
    ever proven to resolve to them."""
    assert detect_genre_from_query("How do I mix a neo soul bassline?") == "rnb_soul"
    assert detect_genre_from_query("What loudness target should I use for a cinematic trailer score?") == "cinematic_game"


def test_classify_track_name():
    assert classify_track_name("Voc Lead Main Dry").role == "vocal_lead"
    assert classify_track_name("BGV Harmony Left").role == "vocal_bg"
    assert classify_track_name("Kick In D112").role == "kick"
    assert classify_track_name("Snare Top").role == "snare"
    assert classify_track_name("Sub Bass 808").role == "sub_bass"
    assert classify_track_name("EGtr Rhythm R").role == "guitar"
    assert classify_track_name("Rhodes Piano").role == "keys"
    assert classify_track_name("Reverb Dly Return").role == "fx_send"
    assert classify_track_name("Random Name 123").role == "unknown"


def test_classify_track_name_covers_the_remaining_four_roles():
    """ROLE_CLASSIFICATIONS has 12 roles; the test above only ever exercised
    8 of them -- drum_bus, bass_synth, synth, and mix_bus had no track name
    ever proven to resolve to them."""
    assert classify_track_name("Drum Overheads").role == "drum_bus"
    assert classify_track_name("Bass Guitar DI").role == "bass_synth"
    assert classify_track_name("Synth Pad Lead").role == "synth"
    assert classify_track_name("Mix Bus Master").role == "mix_bus"


def test_analyze_session_arrangement():
    session_tracks = [
        {"name": "Voc Lead Main"},
        {"name": "Kick Drum"},
        {"name": "Sub Bass 808"},
        {"name": "EGtr Rhythm"},
        {"name": "Piano Keys"},
    ]

    res = analyze_session_arrangement(session_tracks)
    assert res["track_count"] == 5
    assert res["role_summary"]["vocal_lead"] == 1
    assert res["role_summary"]["kick"] == 1
    assert res["role_summary"]["sub_bass"] == 1

    # Check detected masking warnings
    warnings = res["masking_warnings"]
    assert len(warnings) >= 2
    pairs = [w["pair"] for w in warnings]
    assert ("Kick", "Bass") in pairs
    assert ("Lead Vocal", "Midrange Instruments (Guitar/Keys/Synth)") in pairs
    assert all(track["advisory_only"] is True for track in res["classified_tracks"])
    assert all("confidence_band" in track for track in res["classified_tracks"])
    assert all(warning["advisory_only"] is True for warning in warnings)


def test_arrangement_abstains_on_ambiguous_name_and_withholds_dsp_recipe():
    result = analyze_session_arrangement([
        {"index": 7, "name": "Lead Vocal Guitar", "type": "audio"},
        {"index": 8, "name": "Kick", "type": "audio"},
    ])

    ambiguous = result["classified_tracks"][0]
    assert ambiguous["track_index"] == 7
    assert ambiguous["role"] == "unknown"
    assert ambiguous["confidence_band"] == "low"
    assert set(ambiguous["candidates"]) == {"vocal_lead", "guitar"}
    assert ambiguous["suggested_high_pass_hz"] is None
    assert ambiguous["recommended_dsp_move"] == "Inspect the signal before recommending processing."
    assert result["masking_warnings"] == []
