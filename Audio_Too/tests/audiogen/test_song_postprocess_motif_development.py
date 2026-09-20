from composition.song_postprocess.form_polish import (
    _apply_developed_motif_variation,
    develop_song_theme_and_rewrite_hooks,
)


def test_apply_developed_motif_variation_thins_verse_for_neutral():
    motif = [
        (0.0, 0.5, 0, 80),
        (0.5, 0.5, 2, 78),
        (1.0, 1.0, 4, 76),
        (2.0, 0.5, 2, 74),
        (2.5, 1.0, 0, 72),
        (4.0, 1.5, 2, 70),
    ]
    out = _apply_developed_motif_variation(
        motif,
        role="verse",
        primary_emotion="neutral",
        theme_family="neutral_arc",
    )
    assert len(out) == 3
    assert out[0][2] == 0
    assert out[1][0] == 2.25
    assert out[1][2] == 0


def test_apply_developed_motif_variation_leaves_chorus_untouched():
    motif = [(0.0, 0.5, 0, 80), (0.5, 0.5, 2, 78), (1.0, 1.0, 4, 76)]
    out = _apply_developed_motif_variation(
        motif,
        role="chorus",
        primary_emotion="joy",
        theme_family="bright_lift",
    )
    assert out == list(motif)


def test_develop_song_theme_rewrites_multiple_sections_for_joy():
    events = []
    for bar in range(16):
        start = float(bar * 4)
        events.append((1, 0, 70, start, 4.0, [60, 64, 67]))
    for offset in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5):
        events.append((2, 72 + int(offset) % 3, 82, 8.0 + offset, 0.5, [72 + int(offset) % 3]))
    for offset in (0.0, 0.5, 1.0, 1.5):
        events.append((2, 74 + int(offset) % 2, 80, 32.0 + offset, 0.5, [74 + int(offset) % 2]))
    for offset in (0.0, 0.5, 1.0, 1.5, 2.0):
        events.append((3, 67, 64, 8.0 + offset, 0.25, [67]))

    out, meta = develop_song_theme_and_rewrite_hooks(
        events,
        section_bars=[8, 8],
        section_roles=["chorus", "verse"],
        section_roots=[60, 60],
        section_emotions=["joy", "joy"],
        primary_emotion="joy",
        beats_per_bar=4.0,
        strength=0.82,
    )

    assert meta.get("enabled") is True
    assert int(meta.get("sections_developed", 0) or 0) >= 2
    assert len([ev for ev in out if ev[0] == 2]) >= 6
