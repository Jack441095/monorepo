# C1/C2 planner bake-off on the Mac (2026-09-23)

Harness: `tooling/scripts/planner_bakeoff.py` — KENN's real `_generate_llm_plan`
(real system prompt, schema-constrained Ollama decoding, `validate_llm_plan`,
one repair) on the fake demo snapshot. No Live, no writes. 100 drafted
phrasings (`tooling/data/natural_holdout_candidates.jsonl`, owner review
pending): 79 explicit actions, 21 that should get a clarifying question.
Scoring: accepted plan with the right action and track, or a clarify when one
is expected. Ollama 0.34.2 on this Mac (Metal).

| Planner | Accepted | Correct | Actions correct | Clarify correct | p50 | p95 |
|---|---|---|---|---|---|---|
| Rule-based parser (`handle_command`, no LLM) | — | **42%** | 22/79 | **20/21** | ~1 ms | ~1 ms |
| `qwen2.5:1.5b` (current LoRA base) | 38% | 12% | 11/79 | 1/21 | 4.4 s | 11.0 s |
| `qwen2.5:7b-instruct` | 72% | **56%** | 52/79 | 4/21 | 12.7 s | 28.7 s (5 timeouts at 20 s) |

## What failed

- **qwen2.5:1.5b** mostly broke the plan contract, not the language: dB values
  and units for `set_volume` (the contract wants a 0–1 normalized value), and
  track names that are not exact snapshot matches.
- **qwen2.5:7b** understands phrasing well but acts on vague requests ("make the
  snare quieter", "crank the synth") instead of asking; also confused "hats left
  20" (pan) with volume. Too slow for interactive use on this Mac.
- **Rule-based parser** is safe and instant and clarifies correctly, but covers
  few phrasings: volume 1/12, focus 0/6, sends 0/3, slang 0/4.

## Constrained decoding (C1)

Every model reply was valid JSON with the exact schema constant, an allowed
action and no unknown fields; the remaining rejections are contract meaning
(units, ranges, exact names), enforced by `validate_llm_plan`.

## Decisions this points to

1. Grow the rule-based parser for common relative phrasings ("up/down N dB",
   focus, sends) — the cheapest accuracy gain, instant and safe.
2. Let the planner emit user-facing values and units (dB, %) and have KENN
   convert them, instead of asking a small model to do the normalization.
3. C6: fine-tune a small model on a larger, contract-correct corpus that
   includes clarify examples, targeting 7B-level understanding at 1–2 s.
4. Keep the LLM in shadow; nothing here meets the promotion thresholds.
