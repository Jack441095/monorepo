# Advanced-question probe and the first hand-reported misses, 3 October 2026

Nothing here closes C1, C2 or C3. The probe is a way to find where KENN's answers fail; it is not a gate and its concept check is a keyword match, not a grade.

## What was added

- `tooling/evaluation/advanced_questions.json`: 47 cases in 14 groups (psychoacoustics, dynamics, EQ and phase, digital and gain staging, loudness, recording, space, synthesis, Ableton, diagnosis, scope, robustness, underspecified, invention, follow-up). `must_name` lists ideas a competent answer should contain; `must_not_name` lists things it must not bring up unprompted.
- `tooling/scripts/probe_advanced_questions.py`: asks a running companion each question in a fresh chat (a `follow_up_of` case reuses the earlier chat), follows the background model upgrade, and records for every row whether the model was attempted and whether its text was the one delivered. It stops after three questions if the model never runs, unless `--allow-template`. It flags a reply identical to an earlier reply to a different question, and a reply that names a `must_not_name` item.
- `apps/backend/src/kenn/tests/test_probe_advanced_questions.py`: 8 tests against a stub server (model answer credited to the model, rejected model answer leaves the template, model off marked as template, stop after three, `--allow-template`, repeat flag, alternatives in `must_name`, forbidden name flag).
- Output is three files next to `--output`: `.jsonl` and `.review.md` hold answer prose for hand grading and stay out of git; `.summary.json` is numbers only.

## Why the delivery field exists

Earlier on 3 October the companion on Jack's Mac was answering from the grounded template: `KENN_LLM_ENABLED` was not set, `is_enabled()` returned False, every answer logged `(fallback)` and Ollama held no model. A template reply reads like a real answer, so the first round of hand testing measured the wrong path.

## Hand-reported observations (screenshots, not reproduced in the cloud)

Template path, model off:

- A typo ("whasts your advice on white noise?") returned the canned greeting.
- "how about bass compression?" repeated the previous drum-compression answer word for word.
- "fab filter" was read as "filter" and answered with a generic EQ-versus-filter note; no FabFilter product knowledge was found in the source or product docs.
- "i need help mixing vocals" returned a background-vocals note only.
- "advice on pink noise mixing?" returned the monitor-calibration method.
- Technique answers open with the fixed `mix_diagnosis` line "Let's trace the symptom" whether or not a symptom was described.

Reply that appears to be model output (format differs from the template): "advice on mixing low end?" after "fab filter" in the same chat produced a chain naming FabFilter Pro-Q3, "Pro-D2" and "Timeless reverb", mud at 20-100 Hz, the bass panned right, and exact ratios and times. Whether the model was on, and whether the earlier "fab filter" turn leaked into its context, is not established. `lowend-fresh` and the `plugin-bleed-1` / `plugin-bleed-2` pair are there to separate those two explanations.

## Verification

From `products/kenn`, fake Live: `test_probe_advanced_questions.py` **8 passed in 3.6 s** (throwaway venv, Python with the repo's test dependencies). Against a local fake-Live companion with the model off, the runner stopped with exit 3 after three questions and `--allow-template` completed a five-question run. The cloud checkout has no knowledge index, so those answers' content was meaningless; this only checked the flow. The model-answer path was exercised only against the stub server.

## Limits

No real model, real index or real Live was used. The question set and keyword lists are mine and unreviewed by Jack. The probe sends chat questions only and never writes to Live. Raw answers belong outside git.
