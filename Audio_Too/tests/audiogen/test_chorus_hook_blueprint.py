from types import SimpleNamespace
import random

from composition.section_planner.planner import (
    _apply_bright_chorus_payoff_to_melody,
    _apply_chorus_hook_blueprint_to_arp_plan,
    _apply_chorus_hook_blueprint_to_melody,
    _select_seeded_chorus_hook_blueprint,
)


def _owner(seed: int = 123):
    rng = random.Random(seed)

    def drng(*items):
        txt = "|".join(str(x) for x in items)
        s = seed + sum(ord(ch) for ch in txt)
        return random.Random(s)

    return SimpleNamespace(rng=rng, deterministic_rng=drng)


def test_chorus_hook_blueprint_selection_is_seeded_and_stable() -> None:
    owner = _owner(99)
    plan = SimpleNamespace(emotion=SimpleNamespace(name="amusement"))

    a = _select_seeded_chorus_hook_blueprint(owner, plan, section_role="b", section_index=3)
    b = _select_seeded_chorus_hook_blueprint(owner, plan, section_role="tag", section_index=7)

    assert isinstance(a, dict)
    assert isinstance(b, dict)
    assert str(a.get("name", "")) == str(b.get("name", ""))
    assert str(a.get("family", "")) == "bright_motor"


def test_chorus_hook_blueprint_populates_arp_plan_cells() -> None:
    blueprint = {
        "span_bars": 2,
        "arp_steps_by_bar": [[0, 4, 8, 12], [0, 2, 8, 10]],
        "arp_density_mult_min": 1.15,
        "target_notes_per_bar_min": 7.5,
    }

    out = _apply_chorus_hook_blueprint_to_arp_plan({"density_mult": 0.9}, blueprint, bars=4)

    assert out["density_mult"] >= 1.15
    assert out["target_notes_per_bar"] >= 7.5
    assert out["onset_steps_by_bar"][0] == [0, 4, 8, 12]
    assert out["onset_steps_by_bar"][1] == [0, 2, 8, 10]
    assert out["onset_steps_by_bar"][2] == [0, 4, 8, 12]
    assert out["onset_steps_by_bar"][3] == [0, 2, 8, 10]


def test_chorus_hook_blueprint_rewrites_opening_melody_shape() -> None:
    plan = SimpleNamespace(
        beats_per_bar=4.0,
        melody_events=[
            (2, 64, 90, 0.0, 0.5, [64]),
            (2, 66, 90, 0.75, 0.5, [66]),
            (2, 67, 90, 1.25, 0.5, [67]),
            (2, 69, 90, 2.0, 0.5, [69]),
            (2, 71, 90, 4.5, 0.5, [71]),
        ],
    )
    blueprint = {
        "family": "bright_motor",
        "span_bars": 2,
        "melody_steps_by_bar": [[0, 4, 8, 12], [0, 4, 8, 12]],
        "melody_register_floor": 72,
    }

    _apply_chorus_hook_blueprint_to_melody(plan, blueprint, section_role="b")

    lead = [ev for ev in plan.melody_events if int(ev[0]) == 2]
    starts = [round(float(ev[3]), 2) for ev in lead[:4]]
    assert starts == [0.0, 1.0, 2.0, 3.0]
    pitches = [int(ev[1]) for ev in lead[:4]]
    assert pitches == sorted(pitches)


def test_chorus_hook_blueprint_preserves_extra_opening_notes_when_targets_are_fewer() -> None:
    plan = SimpleNamespace(
        beats_per_bar=4.0,
        bars=4,
        emotion=SimpleNamespace(name="disappointment"),
        melody_events=[
            (2, 64, 90, 0.0, 0.25, [64]),
            (2, 65, 90, 0.5, 0.25, [65]),
            (2, 67, 90, 1.0, 0.25, [67]),
            (2, 69, 90, 1.5, 0.25, [69]),
            (2, 71, 90, 2.0, 0.25, [71]),
            (2, 72, 90, 2.5, 0.25, [72]),
        ],
    )
    blueprint = {
        "family": "yearning_pulse",
        "span_bars": 2,
        "melody_steps_by_bar": [[0, 4, 10, 12], [0, 4, 8, 12]],
        "melody_register_floor": 72,
    }

    _apply_chorus_hook_blueprint_to_melody(plan, blueprint, section_role="b")

    lead = [ev for ev in plan.melody_events if int(ev[0]) == 2]
    assert len(lead) == 6


def test_bright_chorus_payoff_restates_hook_when_final_span_is_weak() -> None:
    plan = SimpleNamespace(
        beats_per_bar=4.0,
        bars=8,
        melody_events=[
            (2, 72, 90, 0.0, 0.5, [72]),
            (2, 74, 90, 1.0, 0.5, [74]),
            (2, 76, 90, 2.0, 0.5, [76]),
            (2, 77, 90, 3.0, 0.5, [77]),
            (2, 79, 90, 24.0, 0.5, [79]),
        ],
    )
    blueprint = {
        "family": "bright_motor",
        "span_bars": 2,
        "melody_register_floor": 72,
    }

    _apply_bright_chorus_payoff_to_melody(plan, blueprint, section_role="b")

    lead = [ev for ev in plan.melody_events if int(ev[0]) == 2]
    final_starts = [float(ev[3]) for ev in lead if float(ev[3]) >= 24.0]
    assert final_starts == [24.0, 25.0, 26.0, 27.0]


def test_bright_chorus_payoff_leaves_non_bright_family_unchanged() -> None:
    plan = SimpleNamespace(
        beats_per_bar=4.0,
        bars=8,
        melody_events=[
            (2, 72, 90, 0.0, 0.5, [72]),
            (2, 74, 90, 1.0, 0.5, [74]),
            (2, 76, 90, 2.0, 0.5, [76]),
            (2, 79, 90, 24.0, 0.5, [79]),
        ],
    )

    _apply_bright_chorus_payoff_to_melody(
        plan,
        {"family": "yearning_pulse", "span_bars": 2},
        section_role="b",
    )

    assert len(plan.melody_events) == 4
