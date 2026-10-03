# KENN template-path fixes, 3 Oct 2026

Three bugs from Jack's screenshots, all on the template (no-model) path. Each was reproduced first with a failing test, then fixed.

## What was wrong and what changed

1. **Canned banter for real questions.** "whats your advice on white noise?" and "what do you think of cheese?" got "I'm here! Ask me about mixing...". `weak_match_answer` (`core/chat_formatting.py`) now only uses the banter lines for short remarks ("hmm ok", "nice one"). Anything that asks for something gets the "I don't have a solid note on that one" reply and a question about which part of the session it is for.
2. **Follow-up kept the old instrument.** "how about bass compression?" after a drum-compression answer searched with the drum words and repeated the drum answer. `_swap_followup_subject` (`core/chat_routing.py`) drops drums/bass/vocals words from the earlier turn when a "how about / what about" follow-up names a different one. Same-instrument follow-ups are untouched, and the model hint line uses the same history.
3. **"Let's trace the symptom" on advice questions.** Any mix topic was classed as `mix_diagnosis`. `classify_answer_mode` now sends how/what/why/advice/tips questions with no symptom wording (my, sounds, too, harsh, can't, ...) to `quick_fix` or `deep_explanation`. "my vocal sounds harsh" and "why does my kick sound thin?" still get the diagnosis shape.

## Verification

Fake Live, throwaway venv, from `products/kenn`:

- New tests: `test_weak_match_questions.py`, `test_answer_mode_advice.py` (9 passed), the added cases in `test_history_boundaries.py`. Each failed before its fix.
- Full backend suite: 4045 passed, 137 skipped, 10 failed. The failures are the same set as the earlier cloud baseline, apart from two timing/environment cases: `test_latency_budget.py::test_tier1_short_circuit_sub_millisecond` failed once under suite load (4.4 ms against a 2 ms budget) and passes 3 of 3 times alone and on the unmodified tree; `test_personal_path_gate.py` passed this time.

## Limits

The cloud checkout has no knowledge index, so these were checked at the routing and formatting level, not by reading real retrieved answers. Not fixed: "fab filter" being read as "filter", "i need help mixing vocals" returning only a background-vocals note (retrieval and coverage), and the model-path invention about FabFilter plugins. Those need the real index and a model run through the advanced-question probe on the Mac.
