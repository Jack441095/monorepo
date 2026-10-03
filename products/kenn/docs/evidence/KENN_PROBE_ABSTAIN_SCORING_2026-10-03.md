# Probe scoring for questions that should abstain, 3 October 2026

The Mac baseline reported `scope` recall 0.0. Part of that was the scorer, not KENN. Two of the three `abstain_or_clarify` cases were being scored on concept recall, which only makes sense when the case is answered. `trap-offtopic` has no expected ideas; `trap-third-party-plugin` expects "dynamic eq" and "de-ess", so an honest "I don't have a note on that" scored 0.0.

## What changed

`tooling/scripts/probe_advanced_questions.py` only.

- `judge` sets `handled_as_expected` on `abstain_or_clarify` cases: true when the answer carries the abstention prefix, or when the template's own clarifying reply (`weak_match`) was the delivered answer. A model answer that replaced the template does not count.
- When a case is handled that way its `concept_recall` is `None`, so it drops out of the mean. An abstain case that was answered instead keeps its recall, which covers the "general dynamic-EQ de-essing framed as general" outcome the case note allows.
- The summary adds `expected_abstain_handled` ("1 of 2") per category and overall, only where such cases exist. Still numbers only.

Five tests in `test_probe_advanced_questions.py`. All five failed before the change and pass after.

## What this does not show

- It changes how the next probe is read, not how KENN behaves. No Mac or model number moves until the probe is rerun.
- The model never abstaining is still open. Nothing in the cloud can measure it: there is no index and no model here. The Pro-Q 3 case is the one to read by hand, since the unasked-brand guard does not apply when the user names the brand.
- The `psychoacoustics` gap (no note on the precedence effect in the index) is the other session's retrieval work; see the [precedence alias receipt](KENN_C2_PRECEDENCE_ALIAS_RETRIEVAL_2026-10-03.md). Nothing here touches it.
