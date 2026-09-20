# Song generation upgrade roadmap

This repo generates songs with **Markov + rules + best-of-K + postprocess**, not an end-to-end LLM. The upgrade path optimizes the **whole musical object**, not more inline heuristics.

## Phases

| Phase | Status | Focus |
|-------|--------|--------|
| **A** | Started | Align measurement: audit composite drives whole-song rerank; offline profile enables joint sampling |
| **B** | Started | Ridge reranker from `run_summary.csv`; JSONL candidate logging |
| **C** | Started | Joint plan locks harmony; Markov chorus pitch cell + hook blueprint |
| **D** | Planned | Phrase-level neural generator |

## Phase A (in tree)

- `composition/audit_aligned_score.py` — same composite as `scripts/batch_full_song_note_audit.py`
- `SongGenerator._score_candidate_song` blends legacy score + audit score when `audit_aligned_rerank_enabled` or `song_upgrade_phase_a_enabled`
- `core/song_upgrade_profile.apply_phase_a_profile()` — joint generation, offline quality, `section_k_samples >= 3`

### Try it

```bash
# Offline render (Phase C is default on CONFIG; no flag required)
.venv/bin/python main_render_full_song.py --emotion grief --k 3

# Pre-upgrade baseline
.venv/bin/python main_render_full_song.py --emotion grief --k 3 --legacy-composition

# Audit (Phase C default); baseline comparison: --legacy-composition
OUT_ROOT=/private/tmp/audit_phase_c_plus ./random_seed_comprehensive_musicality_audit.sh
```

### Config flags (`core/composition_config.py`)

- `song_upgrade_phase_a_enabled`
- `audit_aligned_rerank_enabled`
- `audit_aligned_rerank_weight` (default `0.55`)

## Phase B (in tree)

- `composition/song_rerank_model.py` — ridge regression on audit feature columns
- `scripts/train_song_rerank_from_audit.py` — fit from any `run_summary.csv`
- `scripts/log_song_rerank_candidates.py` — append JSONL rows from generation
- `song_rerank_model_path` — when set, `blend_rerank_scores` uses learned weights

### Train + use

```bash
# Fit from your latest audit folder
.venv/bin/python scripts/train_song_rerank_from_audit.py \
  /private/tmp/full_song_audit_post_refactor/full_song_seed_audit_20260525_155804 \
  --output artifacts/song_rerank/rerank_v1.json

# Render with learned reranker
.venv/bin/python main_render_full_song.py --emotion grief --k 4 \
  --song-upgrade-phase-b --song-rerank-model artifacts/song_rerank/rerank_v1.json
```

### Config flags

- `song_upgrade_phase_b_enabled`
- `song_rerank_model_path`
- `song_rerank_log_enabled` / `song_rerank_log_path`

## Phase C (in tree)

- `composition/joint_section_plan.py` — `JointSectionPlan` for chorus + verse/pre
- `composition/section_planner/joint_plan_stage.py` — runs in `prepare_section_harmony`
- Locks chord progression when `joint_plan_lock_harmony` and no external progression passed
- Sets `plan.joint_hook_blueprint` so melody uses the same hook skeleton as harmony

```bash
.venv/bin/python main_render_full_song.py --emotion grief --k 3 --song-upgrade-phase-c

# Full 2×28 emotion audit with Phase C profile enabled
OUT_ROOT=/private/tmp/audit_phase_c_plus ./random_seed_comprehensive_musicality_audit_phase_c.sh
```

Requires `joint_generation_enabled` (Phase C profile turns it on).

### Phase C+ (Markov conditioning, in tree)

- `joint_plan_markov_conditioning_enabled` — chorus Markov snaps to `hook_degrees` from `joint_section_plan`
- `PhrasePlanner.generate_plans(..., joint_hook_degrees=...)` sets hook anchor + arc waypoints
- `_lock_chorus_pitch_cell` in `phrase_generation.py` (mirrors verse cell lock)
- Skips post-Markov `_apply_chorus_hook_blueprint_to_melody` when joint blueprint is active (arp blueprint still applies)

Config: `joint_plan_markov_conditioning_enabled` (on by default; Phase C profile enables it).

## Next

1. Run arranged joint JSONL export + Markov retrain (see commands below).
2. Re-audit with Phase C and compare `counter_fit` / `descent_fit` / hook recurrence.
3. Retrain ridge reranker on larger `run_summary.csv`.
4. Phase D scoping (phrase-level neural generator).

### Audit helpers

| Script | Role |
|--------|------|
| `scripts/run_song_quality_audit.sh` | Arranged-song quality matrix (no WAVs); see `artifacts/quality_audits/README.md` |
| `tools/song_quality_audit.py` | Same audit via Python CLI; scores density, repetition, evaluation checks |
| `random_seed_comprehensive_musicality_audit.sh` | Baseline CONFIG, 2 runs/emotion |
| `random_seed_comprehensive_musicality_audit_phase_c.sh` | Phase C profile, `K=4` default |
| `random_seed_audit_script.sh` | Baseline + `analyze_random_seed_audit_deep.py` |
| `scripts/batch_full_song_note_audit.py --song-upgrade-phase-c` | Same as phase_c shell |

**Produce / live tuning:** use `main.py --producer-macro narrative` (or `cinematic` / `club` / `intimate`) for quick A/B of arrangement and mix contracts without editing CONFIG by hand. Pair with `SONG_QA_FAIL_UNDER=60 scripts/run_song_quality_audit.sh` after composition changes.

### Training loop (arranged joint JSONL → Markov)

```bash
# Export multi-section rows (enable export in CONFIG or use quality-mode render)
.venv/bin/python scripts/generate_arranged_joint_training_jsonl.py \
  --out artifacts/datasets/arranged_joint/v004/arranged_joint_training.jsonl \
  --songs-per-emotion 4 --quality-mode

# Optional reference blend
.venv/bin/python scripts/blend_melody_training_jsonl.py \
  --generated artifacts/datasets/arranged_joint/v004/arranged_joint_training.jsonl \
  --reference training_data/references/your_reference.jsonl \
  --reference-copies 8 \
  --out artifacts/datasets/arranged_joint/v004/blended.jsonl

# Retrain (see scripts/retrain_arranged_songs.sh)
bash scripts/retrain_arranged_songs.sh
```

## What not to do

- Add more postprocess passes without a shared plan (`composition/song_postprocess_pipeline.py` is already long).
- Tune `score_song` weights by hand instead of fitting to audit outcomes.
