from ai.markov.melody.beauty import lyrical_accept_score, score_lyrical_melody


def test_lyrical_scorer_prefers_stepwise_motif_with_cadence() -> None:
    lyrical = [
        (0, 1.0),
        (1, 0.5),
        (2, 0.5),
        (1, 1.0),
        (-1, 0.5),
        (0, 1.0),
        (1, 0.5),
        (2, 0.5),
        (0, 2.0),
    ]
    jumpy = [
        (0, 0.25),
        (4, 0.25),
        (1, 0.25),
        (5, 0.25),
        (2, 0.25),
        (6, 0.25),
        (3, 0.25),
        (6, 0.25),
        (1, 0.25),
    ]

    lyrical_score, lyrical_components = score_lyrical_melody(lyrical)
    jumpy_score, _ = score_lyrical_melody(jumpy)

    assert lyrical_score > jumpy_score
    assert lyrical_components["stepwise"] > 0.5
    assert lyrical_components["cadence"] > 0.7


def test_lyrical_accept_score_stays_in_unit_range_and_ignores_rests_for_leaps() -> None:
    melody = [(0, 1.0), (-1, 0.5), (1, 1.0), (2, 1.0), (0, 2.0)]

    score = lyrical_accept_score(melody)

    assert 0.0 <= score <= 1.0
    assert score > 0.5
