from __future__ import annotations

from composition.song_generator import SongGenerator, SongSectionSpec


def test_default_form_reuses_chorus_progression_within_song():
    """
    Regression: in `default` form, chorus sections (role 'b') should share the same
    chord progression within a single song render so choruses match.
    """
    sg = SongGenerator()
    # Default form: ("intro", "a", "pre_chorus", "b", "a", "b", "outro")
    sections = [SongSectionSpec("joy", bars=4, root_note=60) for _ in range(7)]
    song = sg.generate_song(sections, arrangement_form="default", seed=0)

    meta = song.metadata or {}
    progs = list(meta.get("section_chord_progressions", []) or [])
    assert len(progs) == 7

    # Choruses are sections 3 and 5.
    assert progs[3] == progs[5]


def test_default_form_reuses_verse_progression_within_song():
    """
    Regression: in `default` form, verse sections (role 'a') should share the same
    chord progression within a single song render so verses feel like variations
    over a stable harmonic skeleton.
    """
    sg = SongGenerator()
    sections = [SongSectionSpec("sadness", bars=4, root_note=60) for _ in range(7)]
    song = sg.generate_song(sections, arrangement_form="default", seed=0)

    meta = song.metadata or {}
    progs = list(meta.get("section_chord_progressions", []) or [])
    assert len(progs) == 7

    # Verses are sections 1 and 4.
    assert progs[1] == progs[4]

