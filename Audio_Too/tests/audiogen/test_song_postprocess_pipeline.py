from dataclasses import dataclass

from composition.song_postprocess_pipeline import (
    POSTPROCESS_PASS_ORDER,
    resolve_primary_emotion_for_postprocess,
    run_whole_song_postprocess,
)


@dataclass
class _Section:
    emotion_name: str
    bars: int = 8
    root_note: int = 60


def test_postprocess_pass_order_has_unique_keys():
    assert len(POSTPROCESS_PASS_ORDER) == len(set(POSTPROCESS_PASS_ORDER))
    assert POSTPROCESS_PASS_ORDER[0] == "melody_reprise"
    assert POSTPROCESS_PASS_ORDER[-6] == "final_chorus_strength_guard"
    assert POSTPROCESS_PASS_ORDER[-5:] == (
        "final_phrase_boundary_breath",
        "final_lead_singability_guard",
        "final_bass_motion_guard",
        "final_bar_velocity_smoother",
        "final_lead_arp_overlap_guard",
    )


def test_resolve_primary_emotion_prefers_verse_role():
    sections = [
        _Section("gratitude", bars=8),
        _Section("love", bars=8),
    ]
    roles = ["intro", "verse"]
    assert resolve_primary_emotion_for_postprocess(sections, roles) == "love"


def test_run_whole_song_postprocess_returns_events_and_meta():
    events = [
        (2, 64, 90, 0.0, 1.0, [64]),
        (0, 60, 80, 0.0, 4.0, [60, 64, 67]),
    ]
    sections = [_Section("joy", bars=8), _Section("joy", bars=8)]
    roles = ["verse", "chorus"]
    out, meta, primary = run_whole_song_postprocess(
        events,
        sections=sections,
        roles_for_post=roles,
        section_bars_for_post=[8, 8],
        composer=None,
    )
    assert isinstance(out, list)
    assert len(out) >= 1
    assert isinstance(meta, dict)
    assert primary == "joy"
