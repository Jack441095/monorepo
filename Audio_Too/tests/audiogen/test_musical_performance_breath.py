from composition.event import Event
from composition.section_plan import SectionPlan
from composition.section_planner.section_finalize import _apply_melody_phrase_boundary_breath_typed
from audiogen_core.config import CONFIG
from data.music_data import EMOTION_BY_NAME


def _plan() -> SectionPlan:
    plan = SectionPlan(
        emotion=EMOTION_BY_NAME["neutral"],
        root_note=60,
        bars=8,
        beats_per_bar=4.0,
    )
    plan.timeline_targets = {
        "phrase_role_by_bar": [
            "opening",
            "answer",
            "continuation",
            "cadence",
            "opening",
            "answer",
            "continuation",
            "cadence",
        ],
        "breath_window": [0.0, 0.0, 0.0, 0.7, 0.7, 0.0, 0.0, 0.0],
    }
    return plan


def test_melody_phrase_boundary_breath_shortens_lead_note_before_new_phrase():
    prior = (
        CONFIG.composition.melody_phrase_breath_enabled,
        CONFIG.composition.melody_phrase_breath_beats,
        CONFIG.composition.melody_phrase_breath_min_note_beats,
    )
    try:
        CONFIG.composition.melody_phrase_breath_enabled = True
        CONFIG.composition.melody_phrase_breath_beats = 0.25
        CONFIG.composition.melody_phrase_breath_min_note_beats = 0.20
        out = _apply_melody_phrase_boundary_breath_typed(
            [Event(2, 72, 90, 15.0, 2.0, [72])],
            _plan(),
        )
    finally:
        (
            CONFIG.composition.melody_phrase_breath_enabled,
            CONFIG.composition.melody_phrase_breath_beats,
            CONFIG.composition.melody_phrase_breath_min_note_beats,
        ) = prior

    assert len(out) == 1
    assert out[0].duration_beats == 0.75


def test_melody_phrase_boundary_breath_leaves_nonlead_and_tiny_notes_alone():
    prior = (
        CONFIG.composition.melody_phrase_breath_enabled,
        CONFIG.composition.melody_phrase_breath_beats,
        CONFIG.composition.melody_phrase_breath_min_note_beats,
    )
    try:
        CONFIG.composition.melody_phrase_breath_enabled = True
        CONFIG.composition.melody_phrase_breath_beats = 0.25
        CONFIG.composition.melody_phrase_breath_min_note_beats = 0.50
        events = [
            Event(1, 0, 80, 15.0, 2.0, [60, 64, 67]),
            Event(2, 72, 90, 15.6, 1.0, [72]),
        ]
        out = _apply_melody_phrase_boundary_breath_typed(events, _plan())
    finally:
        (
            CONFIG.composition.melody_phrase_breath_enabled,
            CONFIG.composition.melody_phrase_breath_beats,
            CONFIG.composition.melody_phrase_breath_min_note_beats,
        ) = prior

    assert out[0].duration_beats == 2.0
    assert out[1].duration_beats == 1.0
