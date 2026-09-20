# Melody Markov architecture (quick reference)

## Two chains

- **IntervalMarkov**: pitch motion as scale-degree deltas between **voiced** notes.
- **RhythmMarkov**: IOI / note durations (including durations of rest events when present in training data).

Generation is sequential: sample duration, then interval, then harmony/tension/masking layers. See `ai/markov/melody/note_generator/` (`_rhythm.py` / `_interval.py` / `_core.py`).

## Rhythm–pitch coupling (two directions, two flags)

| Direction | `CompositionConfiguration` | Location |
|-----------|----------------------------|----------|
| **Interval → duration** (large leap → longer next note, etc.) | `melody_rhythm_pitch_coupling_enabled`, `melody_rhythm_pitch_coupling_strength` | `_select_rhythm` |
| **Duration → interval** (short note → stepwise next, long note → wider leap) | `melody_interval_duration_coupling_enabled`, `melody_interval_duration_coupling_strength` | `_select_interval` |

These are independent toggles; both can be on.

## Breath timeline

Section planning can attach `breath_window` per bar to `timeline_targets`. That list is threaded as `breath_window_by_bar` into `MelodyGenerator.generate_with_phrases` and downstream.

- **Rest bias (post-pass):** `melody_breath_rest_bias_enabled`, `melody_breath_rest_bias_strength` scale `insert_rests` probability by bar.
- **Rhythm sparsity (sampling):** `melody_breath_rhythm_bias_enabled`, `melody_breath_rhythm_bias_strength` bias `_select_rhythm` toward longer IOIs on high-breath bars.

## REST tokens (staged)

- **Training:** `melody_train_rest_safe_intervals_enabled` (default true): interval n-grams use only **voiced** degrees; deltas are not computed through `degree < 0` rests.
- **Generation:** `melody_generation_rest_tokens_enabled` and `melody_rest_token_step_probability`: the phrase loop may emit `(-1, duration)` rests while keeping a separate last voiced degree for pitch motion.

## Joint rhythm–pitch rerank

`melody_joint_rhythm_pitch_rerank_enabled`, `melody_joint_rhythm_pitch_rerank_strength`, optional `melody_joint_rhythm_pitch_rerank_k` (top-K duration support before reweighting; 0 = full support): duration choice is reweighted using the interval Markov marginal so duration and expected pitch motion agree before the interval is sampled (`_select_rhythm`).
