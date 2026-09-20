from types import SimpleNamespace

import pytest


def test_song_memory_captures_section_shape():
    from composition.song_memory import SongMemory

    plan = SimpleNamespace(
        section_role="b",
        chords=["I", "V", "vi", "IV", "I"],
        melody_events=[
            (2, 60, 90, 0.0, 1.0, [60]),
            (2, 64, 90, 1.0, 1.0, [64]),
            (2, 67, 90, 2.0, 1.0, [67]),
        ],
        phrase_intent_by_bar=[
            {"cadence_strength": 0.1},
            {"cadence_strength": 0.4},
            {"cadence_strength": 0.8},
        ],
        motif_development={"role": "statement"},
    )

    mem = SongMemory()
    mem.remember_section(plan, section_role="b", section_index=2)

    assert mem.section_count == 1
    assert mem.last_section_role == "b"
    assert mem.last_section_index == 2
    assert mem.last_chord_signature == ("I", "V", "vi", "IV")
    assert mem.last_register_center == (60 + 64 + 67) / 3.0
    assert mem.last_cadence_strength == pytest.approx(0.6)
    assert mem.last_motif_development == {"role": "statement"}
    assert list(mem.recent_roles) == ["b"]
    assert list(mem.recent_chord_signatures) == [("I", "V", "vi", "IV")]


def test_song_memory_captures_and_resets_chorus_hook():
    from composition.song_memory import SongMemory

    mem = SongMemory()
    mem.remember_chorus_hook(
        {
            "span": 8.0,
            "events": [
                {"start": 0.0, "dur": 1.0, "root_offset": 0, "velocity": 90},
                {"start": 1.0, "dur": 1.0, "root_offset": 4, "velocity": 90},
                {"start": 2.0, "dur": 1.0, "root_offset": 7, "velocity": 90},
            ],
        }
    )

    assert mem.chorus_hook_span == 8.0
    assert mem.chorus_hook_signature == (0, 4, 7)

    mem.reset()

    assert mem.section_count == 0
    assert mem.chorus_hook_signature == ()
    assert mem.chorus_hook_events == []


def test_composition_generator_resets_song_memory():
    from composition.engine import CompositionGenerator

    gen = CompositionGenerator(enable_perf_monitoring=False)
    gen.song_memory.section_count = 3
    gen.song_memory.recent_roles.append("a")
    gen._chorus_hook_memory = {"span": 4.0, "events": []}

    gen.reset_song_arrangement_state()

    assert gen.song_memory.section_count == 0
    assert list(gen.song_memory.recent_roles) == []
    assert gen._chorus_hook_memory is None
