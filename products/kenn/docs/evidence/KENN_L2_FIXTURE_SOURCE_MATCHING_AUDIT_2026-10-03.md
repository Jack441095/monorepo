# Which expected sources are matched by substring — 3 October 2026

L2 asks us to audit fixture exclusions, including substring matching, before claiming improved recall. This is the
matching half; we did not audit source tiers.

## What the scorers do

`tooling/scripts/evaluate_retrieval_modes.py` (`_source_matches`) counts a result as the expected source when each
`source_must_include` term appears, case-folded, anywhere in the chunk's `source` plus `title`. `_rank` takes the first
result that matches. `eval_chat_coverage.py` reads the same field. So a term is a substring, not a source id.

## How ambiguous the terms are

We loaded the current index (750 distinct sources) and, for every term in every fixture under `kenn/evals/`, counted how
many sources contain it.

| Fixture | Terms | Match more than one source | Match none |
| --- | ---: | ---: | ---: |
| `device_purpose_retrieval_cases` | 125 | 57 | 0 |
| `device_purpose_sealed_qwen8b` | 228 | 6 | 0 |
| `device_purpose_sealed_holdout` | 150 | 0 | 0 |
| `technique_purpose_retrieval_cases` | 50 | 1 (`room-acoustics`, 3 sources) | 0 |
| `questions` (default cases) | 92 | 1 (`clipping`, 27 sources) | 3 |
| `knowledge_upgrade_cases`, `internet_source_cases`, `conversation_cases` | 60 | 0 | 0 |
| `draft_feedback_cases` | 1 | 0 | 1 (`test-note.md`) |

`session_grounded_cases` keeps a single string in the field and is scored by a different script; it is left out. Our
first pass over it counted letters, which is why it looked fully ambiguous. That was our script's mistake.

## What it means

- **Most ambiguity is near-duplicate notes**, e.g. `ableton-looper-device.md` and `ableton-looper.md`, two Beat Repeat
  notes, three arpeggiator notes. Accepting either is defensible, and the sealed sets are mostly clear of it.
  `device_purpose_retrieval_cases` is the exception: 57 of 125 terms (46%) can be met by more than one source, and some
  are prefixes (`analog-`, `auto-pan`). Its recall will read a little generous. We did not re-score it.
- **`clipping` in `questions.json` is too loose.** The case `objective-clipping-not-a-style-choice` is satisfied by any
  of 27 sources whose name or title contains the word, including unrelated production-strategy notes.
- **Three default cases cannot pass on retrieval.** `business-pricing-scope-first`, `business-quote-before-mix` and
  `business-exact-cheap-price-pressure` expect `client-mix-pricing-and-quotes`, which no source in the index contains
  (we have not checked whether that is deliberate).
- `draft_feedback_cases` expects `test-note.md`, which is also absent; that looks like a leftover test case.

## Not changed

No scorer or fixture was edited: tightening a term changes every baseline that was measured with it, and we would want
before-and-after figures for that. Candidates, in order: make `_source_matches` match a whole file stem when the term
ends in `.md` or has no further hyphenated siblings; tighten `clipping`; decide the three business cases. Left for a
separate change with the baselines re-run.

Source tiers and the fixture exclusions in the build path (not the scorers) are not covered. C4 and C5 targets are
untouched. L2 stays open.
