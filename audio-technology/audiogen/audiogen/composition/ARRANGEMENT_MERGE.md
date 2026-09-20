# Arrangement profile merge order

This documents how section-level arrangement numbers are composed before audio events are built. Use it when tuning emotions, tension arcs, or counter/arp floors so changes land in the intended layer.

## Pipeline (section planner → policy)

Rough order inside `ArrangementPolicy.arrangement_curve` and related planner hooks:

1. **BASE_CURVE** — role defaults (velocity, density, layer weights) from arrangement templates.
2. **Role curve** — per-section role targets (intro / verse / chorus / …).
3. **Emotion overrides** — `EmotionProfile` scalars and section emotion name (constant primary when `arranged_disable_emotion_arc`).
4. **Section role profiles** — `data/emotion_section_role_profiles.py` (counter mult, layer emphasis per role).
5. **Default-form contrast polish** — `section_dynamics_stage.apply_default_form_contrast_polish` (intro vs chorus register/velocity contrast).
6. **Tension arc dynamics** — `section_dynamics_stage.apply_final_tension_arc_dynamics` using `data/tension_arc_dynamics.py` (`flat` / `fall` / `rise` / `spike` → `section_dynamic`, `melody_vel_scale`).
7. **Arp suppression guard** — primary emotions with suppressed arp bed (`emotion_arp_bed_suppressed`) via planner/policy; full-song strip in postprocess.

Counter-melody (ch5) runs in the planner after the curve is largely fixed:

- `counter_melody_stage.run_counter_melody_stage` — generate → filter → thin vs lead → presence multiplier → restore floor.

See `composition/section_planner/PIPELINE.md` for extracted stage modules.

## Whole-song postprocess (after stitch)

`composition/song_postprocess_pipeline.py` defines the pass order (`POSTPROCESS_PASS_ORDER`) and runs all passes via `run_whole_song_postprocess()`. `song_generator.py` calls that single entry point; metadata keys are stored under `meta["song_postprocess"]`.

| Phase | Module | Examples |
|-------|--------|----------|
| Form / theme | `song_postprocess/form_polish.py` | reprises, theme development, professionalizer, bright/reflective chorus shaping |
| Scale / harmony | `song_postprocess/scale_guards.py` | lead snap, full-arrangement scale guard, phrase-end repair, strong-beat anchor |
| Texture floors | `song_postprocess/texture_floors.py` | chorus counter/arp floors, arp ducking, ambient non-chorus arp, strip arp outside chorus |

**Professionalizer** (`professionalize_song_form`) runs mid-chain and again uses tension arc via `apply_tension_arc_to_professionalizer_velocities` (same module as section dynamics).

**Scale guards** use `_scale_emotion_name_for_section` so stitched songs respect constant primary emotion + per-section roots.

## Where to edit

| Goal | First place to look |
|------|---------------------|
| Counter audibility | `counter_melody_stage.py`, `texture_floors.reinforce_chorus_counterline_floor`, `emotion_section_role_profiles` |
| Intro→chorus velocity arc | `tension_arc_dynamics.py`, `section_dynamics_stage.py`, audit arc-aware fit in `scripts/batch_full_song_note_audit.py` |
| In-key / scale | `scale_guards.py`, `melody_emotion_profiles`, planner `scale_setup` |
| Arp only in chorus (disgust etc.) | `emotion_profiles`, planner arp guard, `strip_arp_outside_chorus_for_suppressed_primary` |

## Audits

- Full-seed note audit: `scripts/batch_full_song_note_audit.py` / `random_seed_comprehensive_musicality_audit.sh`
- Tonality compare: `scripts/compare_emotion_tonality.py`
