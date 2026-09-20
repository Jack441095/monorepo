from composition.event import Event
from composition.section_plan import SectionPlan
from composition.section_planner.planner import SectionPlanner
from data.music_data import EMOTION_BY_NAME


def _plan(role: str = "a") -> SectionPlan:
    return SectionPlan(
        emotion=EMOTION_BY_NAME["neutral"],
        root_note=60,
        bars=2,
        beats_per_bar=4.0,
        section_role=role,
    )


def _ev(ch: int, midi: int, start: float, dur: float = 0.5, vel: int = 80) -> Event:
    return Event(channel=ch, midi=midi, velocity=vel, start_beats=start, duration_beats=dur, notes=[midi])


def test_collision_manager_thins_short_arp_near_busy_lead_grid() -> None:
    from audiogen_core.config import CONFIG

    events = [
        _ev(2, 72, 0.0),
        _ev(2, 74, 0.5),
        _ev(2, 76, 1.0),
        _ev(3, 74, 0.52, dur=0.25),
        _ev(0, 48, 0.0, dur=1.0),
    ]

    old_layers_indep = getattr(CONFIG.composition, "arp_melody_layers_fully_independent", True)
    CONFIG.composition.arp_melody_layers_fully_independent = False
    try:
        out = SectionPlanner._apply_arrangement_collision_manager_typed(events, _plan("a"), strength=1.0)
    finally:
        CONFIG.composition.arp_melody_layers_fully_independent = old_layers_indep

    assert any(int(ev.channel) == 2 for ev in out)
    assert any(int(ev.channel) == 0 for ev in out)
    assert not any(int(ev.channel) == 3 and abs(float(ev.start_beats) - 0.52) < 1e-6 for ev in out)


def test_collision_manager_softens_chord_stab_that_masks_lead() -> None:
    events = [
        _ev(2, 72, 0.0),
        _ev(2, 74, 0.5),
        _ev(2, 76, 1.0),
        Event(channel=1, midi=0, velocity=90, start_beats=0.5, duration_beats=1.0, notes=[67, 72, 76]),
    ]

    out = SectionPlanner._apply_arrangement_collision_manager_typed(events, _plan("b"), strength=1.0)
    chord = next(ev for ev in out if int(ev.channel) == 1)

    assert int(chord.velocity) < 90


def test_collision_manager_keeps_chorus_strong_arp_hit_but_softens_it() -> None:
    events = [
        _ev(2, 72, 0.0),
        _ev(2, 74, 0.5),
        _ev(3, 74, 0.0, dur=0.25, vel=80),
    ]

    out = SectionPlanner._apply_arrangement_collision_manager_typed(events, _plan("b"), strength=1.0)
    arp = next(ev for ev in out if int(ev.channel) == 3)

    assert int(arp.velocity) < 80
