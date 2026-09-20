from composition.harmony_pacing import apply_harmony_pacing_to_tokens, harmony_pacing_for_section


def test_verse_harmony_pacing_holds_early_motion() -> None:
    plan = harmony_pacing_for_section("a", 8)
    tokens = ["I:maj", "IV:maj", "V:dom", "vi:min", "IV:maj", "V:dom", "I:maj", "I:maj"]

    out = apply_harmony_pacing_to_tokens(tokens, plan)

    assert plan.motion_multiplier < 1.0
    assert out[1] == out[0]


def test_pre_chorus_harmony_pacing_allows_motion() -> None:
    plan = harmony_pacing_for_section("pre_chorus", 8, next_role="b")

    assert plan.motion_multiplier > 1.0
    assert plan.min_change_spacing == 1


def test_bridge_harmony_pacing_marks_one_surprise_bar() -> None:
    plan = harmony_pacing_for_section("a_prime", 8)

    assert plan.surprise_bars
    assert 1 <= next(iter(plan.surprise_bars)) <= 6


def test_cadence_bars_are_not_forced_to_hold() -> None:
    plan = harmony_pacing_for_section("outro", 4)
    tokens = ["I:maj", "IV:maj", "V:dom", "I:maj"]

    out = apply_harmony_pacing_to_tokens(tokens, plan)

    assert out[-1] == "I:maj"
