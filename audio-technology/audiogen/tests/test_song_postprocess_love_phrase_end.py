from composition.song_postprocess.scale_guards import repair_song_phrase_end_chord_tones


def _sparse_love_phrase_end_events():
    # C-major harmony; lead lands late with a non-chord tone near the 4-bar phrase end.
    return [
        (1, 60, 80, 0.0, 16.0, [60, 64, 67]),
        (2, 73, 88, 15.34, 0.16, [73]),
    ]


def test_repair_phrase_end_love_inserts_tighter_cadence_than_amusement():
    events = _sparse_love_phrase_end_events()
    _out_amuse, meta_amuse = repair_song_phrase_end_chord_tones(
        events,
        section_bars=[4],
        section_roles=["b"],
        section_roots=[60],
        section_emotions=["amusement"],
        beats_per_bar=4.0,
        primary_emotion="amusement",
    )
    _out_love, meta_love = repair_song_phrase_end_chord_tones(
        events,
        section_bars=[4],
        section_roles=["b"],
        section_roots=[60],
        section_emotions=["love"],
        beats_per_bar=4.0,
        primary_emotion="love",
    )

    assert int(meta_love.get("notes_repaired", 0)) > int(meta_amuse.get("notes_repaired", 0))
