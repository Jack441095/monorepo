def test_section_boundary_melodic_pickups_aim_at_next_opening():
    from composition.song_postprocess import add_section_boundary_melodic_pickups

    events = [
        (2, 60, 80, 0.0, 1.0, [60]),
        (1, 48, 70, 0.0, 4.0, [48, 52, 55]),
        # Next section opening target.
        (2, 67, 92, 8.0, 1.0, [67]),
    ]

    out, meta = add_section_boundary_melodic_pickups(
        events,
        section_bars=[2, 2],
        section_roles=["a", "b"],
        beats_per_bar=4.0,
        strength=0.8,
    )

    pickups = [ev for ev in out if int(ev[0]) == 2 and 7.0 <= float(ev[3]) < 8.0]
    assert meta["added_pickups"] == 2
    assert [int(ev[1]) for ev in pickups] == [65, 66]


def test_song_generator_applies_full_song_melodic_pickup_postprocess():
    from composition.song_generator import SongGenerator, SongSectionSpec

    class _Composer:
        def __init__(self):
            self.arrangement_policy = type("Policy", (), {"form_mode": "default"})()
            self._last_section_motif_development = {}

        def reset_song_arrangement_state(self):
            pass

        def generate_section(self, **kwargs):
            idx = int(kwargs.get("section_index", 0) or 0)
            if idx == 0:
                return [(2, 60, 80, 0.0, 1.0, [60])]
            return [(2, 67, 92, 0.0, 1.0, [67])]

    sg = SongGenerator(composer=_Composer())
    song = sg.generate_song(
        [
            SongSectionSpec("neutral", bars=2, root_note=60),
            SongSectionSpec("neutral", bars=2, root_note=60),
        ],
        arrangement_form="wave",
        seed=0,
    )

    pickups = [ev for ev in song.events if int(ev[0]) == 2 and 7.0 <= float(ev[3]) < 8.0]
    assert len(pickups) >= 1
    assert (song.metadata or {}).get("song_postprocess", {}).get("added_pickups") >= 1


def test_melody_reprise_restates_hook_opening_in_later_chorus():
    from composition.song_postprocess import add_melody_reprises

    events = [
        # First chorus source motif.
        (2, 60, 90, 0.0, 1.0, [60]),
        (2, 62, 90, 1.0, 1.0, [62]),
        (2, 64, 90, 2.0, 1.0, [64]),
        # Later chorus has unrelated opening that should be replaced.
        (2, 67, 88, 8.0, 1.0, [67]),
        (2, 65, 88, 9.0, 1.0, [65]),
        (2, 63, 88, 10.0, 1.0, [63]),
    ]

    out, meta = add_melody_reprises(
        events,
        section_bars=[2, 2],
        section_roles=["b", "b"],
        beats_per_bar=4.0,
        strength=0.8,
    )

    reprise = [ev for ev in out if int(ev[0]) == 2 and 8.0 <= float(ev[3]) < 11.0]
    assert meta["reprises_written"] == 1
    assert meta["notes_replaced"] == 3
    assert [int(ev[1]) for ev in reprise[:3]] == [67, 69, 71]


def test_song_generator_applies_melody_reprise_metadata():
    from composition.song_generator import SongGenerator, SongSectionSpec

    class _Composer:
        def __init__(self):
            self.arrangement_policy = type("Policy", (), {"form_mode": "pop"})()
            self._last_section_motif_development = {}

        def reset_song_arrangement_state(self):
            pass

        def generate_section(self, **kwargs):
            idx = int(kwargs.get("section_index", 0) or 0)
            if idx == 2:
                return [
                    (2, 60, 90, 0.0, 1.0, [60]),
                    (2, 62, 90, 1.0, 1.0, [62]),
                    (2, 64, 90, 2.0, 1.0, [64]),
                ]
            if idx == 4:
                return [
                    (2, 67, 88, 0.0, 1.0, [67]),
                    (2, 65, 88, 1.0, 1.0, [65]),
                    (2, 63, 88, 2.0, 1.0, [63]),
                ]
            return [(2, 55 + idx, 70, 0.0, 0.5, [55 + idx])]

    sg = SongGenerator(composer=_Composer())
    sections = [SongSectionSpec("neutral", bars=2, root_note=60) for _ in range(5)]
    song = sg.generate_song(sections, arrangement_form="pop", seed=0)

    meta = (song.metadata or {}).get("song_postprocess", {}).get("melody_reprise", {})
    assert int(meta.get("reprises_written") or 0) >= 1
    target_notes = [ev for ev in song.events if int(ev[0]) == 2 and 32.0 <= float(ev[3]) < 35.0]
    assert [int(ev[1]) for ev in target_notes[:3]] == [67, 69, 71]


def test_professionalizer_shapes_hook_register_and_dynamic_arc():
    from composition.song_postprocess import professionalize_song_form

    events = [
        (2, 55, 80, 0.0, 1.0, [55]),   # verse
        (3, 60, 60, 0.5, 0.25, [60]),  # verse decoration eligible for thinning
        (2, 57, 90, 8.0, 1.0, [57]),   # chorus too low; should octave-lift
        (2, 59, 90, 9.0, 1.0, [59]),
        (2, 60, 90, 10.0, 1.0, [60]),
    ]

    out, meta = professionalize_song_form(
        events,
        section_bars=[2, 2],
        section_roles=["a", "b"],
        beats_per_bar=4.0,
        strength=0.8,
    )

    chorus = [ev for ev in out if int(ev[0]) == 2 and float(ev[3]) >= 8.0]
    assert meta["enabled"] is True
    assert meta["register_shifted_notes"] >= 3
    assert [int(ev[1]) for ev in chorus[:3]] == [69, 71, 72]
    assert int(chorus[0][2]) > 90


def test_professionalizer_derives_outro_fragment_from_hook():
    from composition.song_postprocess import professionalize_song_form

    events = [
        (2, 60, 90, 0.0, 1.0, [60]),
        (2, 62, 90, 1.0, 1.0, [62]),
        (2, 64, 90, 2.0, 1.0, [64]),
        (2, 55, 70, 8.0, 1.0, [55]),
    ]

    out, meta = professionalize_song_form(
        events,
        section_bars=[2, 2],
        section_roles=["b", "outro"],
        beats_per_bar=4.0,
        strength=0.8,
    )

    outro = [ev for ev in out if int(ev[0]) == 2 and 8.0 <= float(ev[3]) < 11.0]
    assert meta["hook_fragment_notes"] >= 2
    assert len(outro) >= 2


def test_song_generator_applies_professionalizer_metadata():
    from composition.song_generator import SongGenerator, SongSectionSpec

    class _Composer:
        def __init__(self):
            self.arrangement_policy = type("Policy", (), {"form_mode": "wave"})()
            self._last_section_motif_development = {}

        def reset_song_arrangement_state(self):
            pass

        def generate_section(self, **kwargs):
            idx = int(kwargs.get("section_index", 0) or 0)
            if idx == 1:
                return [(2, 57, 90, 0.0, 1.0, [57]), (2, 59, 90, 1.0, 1.0, [59]), (2, 60, 90, 2.0, 1.0, [60])]
            return [(2, 55 + idx, 70, 0.0, 0.5, [55 + idx])]

    sg = SongGenerator(composer=_Composer())
    song = sg.generate_song(
        [SongSectionSpec("neutral", bars=2, root_note=60), SongSectionSpec("neutral", bars=2, root_note=60)],
        arrangement_form="wave",
        seed=0,
    )

    meta = (song.metadata or {}).get("song_postprocess", {}).get("professionalizer", {})
    assert meta.get("enabled") is True
    assert "velocity_scaled_events" in meta
