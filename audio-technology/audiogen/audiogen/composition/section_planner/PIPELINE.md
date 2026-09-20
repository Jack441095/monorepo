# Section planner pipeline

`planner.py` is now a thin assembly shell (~150 lines): it holds `__init__`,
the `prepare_section_events`/`finalize_section_events` delegating wrappers,
the `_apply_*_typed` QA aliases, and composes `SectionPlanner` from four
mixins (2026-07-14 split). Heavy logic lives in stage modules below.

## Module map

| Module | ~Lines | Responsibility |
|--------|--------|----------------|
| `planner.py` | 150 | `SectionPlanner` class assembly, `__init__`, build/prepare/finalize delegating wrappers, QA aliases |
| `planner_hook_memory_mixin.py` | 130 | Chorus-reference overrides, final-chorus-payoff state plumbing, cross-lane motif bus, chorus-hook-memory glue, counter-melody thinning (static helpers) |
| `planner_arrangement_dynamics_mixin.py` | 720 | Verse-sentence/timeline/arrangement-energy-matrix target shaping, whole-song energy + director, song-blueprint target blending (static helpers) |
| `planner_build_mixin.py` | 770 | `_build_section_once` + `build_section` — the per-section build orchestration |
| `planner_harmony_voicing_mixin.py` | 320 | `prepare_section_harmony` + `prepare_section_voicing` |
| `section_event_build.py` | 3100 | `prepare_section_events` — Markov melody/arp, hooks, counter stage |
| `section_finalize.py` | 2050 | `finalize_section_events` — QA typed passes, humanization, assembly |
| `chorus_hook_memory.py` | 185 | Capture/apply chorus hook across sections |
| `lead_texture_guards.py` | 285 | Arp bed, perceptual scale, supportive arp |
| `chorus_hook_blueprint.py` | 380 | Hook blueprints + apply |
| `melody_event_guards.py` | 660 | Cadence repair, leaps, repeats |
| `section_event_qa.py` | 1500 | Typed velocity/gesture/collision/contrast QA |
| `counter_melody_stage.py` | 440 | Counter-melody pipeline |
| `section_dynamics_stage.py` | 240 | Tension arc + form contrast |
| `chorus_reference.py`, `final_chorus_payoff.py`, `motif_bus.py`, … | small | Focused overrides |

`section_event_build.py` and `section_finalize.py` are each, structurally, a
single very long function (`prepare_section_events` / `finalize_section_events`)
with deep nested-closure control flow and hundreds of interdependent local
variables (11 levels of indentation in places) rather than a set of
independent top-level functions. That shape makes them safe to *relocate*
wholesale but not safe to mechanically split further without semantic
restructuring (threading dozens of implicit closure variables through
explicit parameters) that risks changing behavior in this DSP/composition
pipeline — so, unlike `planner.py`, they were intentionally left as single
files in the 2026-07-14 decomposition pass.

## Entry points

```python
from composition.section_planner.planner import SectionPlanner

planner = SectionPlanner(owner)
plan = planner.build_section(...)           # → planner_build_mixin
plan = planner.prepare_section_events(...)  # → section_event_build
plan = planner.finalize_section_events(...) # → section_finalize
```

### Direct module access (debugging)

```python
from composition.section_planner.section_event_build import prepare_section_events
from composition.section_planner.section_finalize import finalize_section_events
from composition.section_planner.chorus_hook_memory import capture_chorus_hook_memory
from composition.section_planner.section_event_qa import _apply_arrangement_collision_manager_typed
```

`SectionPlanner._apply_*_typed` and `_capture_chorus_hook_memory` remain as aliases.

### Whole-song polish

`composition/song_postprocess_pipeline.py` — see `composition/ARRANGEMENT_MERGE.md`.

## Size history

| Phase | `planner.py` lines |
|-------|-------------------|
| Original | ~10,011 |
| Phase 1 (guards + QA extract) | ~7,258 |
| Phase 2 (build/finalize/memory) | ~2,024 |
| Phase 3 (mixin split: hook_memory/arrangement_dynamics/build/harmony_voicing) | **~150** |
