# Displayed track choices — 2 Oct 2026

The North Star's displayed-pair follow-up is verified with FakeLive. Engineering
did not connect to or write to the producer's running Live session.

## Behavior

`mute Vocal` with two tracks named Vocal asks for the displayed track number.
`track 2` prepares its mute proposal. After selection, `no, the other one`
prepares the other displayed track's proposal, including after applying the first.
The answer says the first change is still applied. Applying and undoing the second
change verifies readback and leaves the first change in place.

Choices retain the original command, track index, name and display position for
300 s in one session. Both identities are checked against a fresh snapshot.
Unselected pairs, three matches, rename, reorder, removal, expiry, unrelated
commands and another session cannot use the old pair. Explicit numbers or a
unique displayed name can select a track; a repeated duplicate name still asks
and preserves the original action and amount. Shared nicknames such as `vox`
also produce choices. Display positions work with non-contiguous track indices.

The session projection excludes confirmation tokens and returns a copy of choice
identities for diagnostics. Proposals still use the existing Apply/readback/receipt
boundary. Ambiguous choices skip model generation; a supplied model plan cannot
answer the producer's track-choice question.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_live_track_choices.py kenn/tests/test_live_conversation_context.py kenn/tests/test_live_command.py kenn/tests/test_live_intent.py kenn/tests/test_live_intent_natural.py kenn/tests/test_live_intent_rule_order.py kenn/tests/test_live_intent_corpus_replay.py kenn/tests/test_session_context.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_live_command.py::test_llm_plan_gets_one_structural_repair_attempt
```

- New coverage: 20 tests in `test_live_track_choices.py`, including parser and
  gateway behavior, isolation, stale choices, Apply and verified undo.
- Scoped suite: 520 passed in 2.87 s.
- Full backend: 3,109 passed, 12 skipped, one failed in 76.42 s. The sole failure
  is the pre-existing order-dependent structural-repair test recorded in the
  refactor handoff; it passes alone in 0.11 s.
- Seven mutations caught: expiry, position/index binding, name binding, pair
  cardinality, retention after Apply, model authority and nickname ambiguity.
  Each edited source file was restored and SHA-256 checked before the next run.
- Replay fixture: exactly two of 384 rows intentionally change. In the ambiguous
  snapshot, `the vocal on its own` and `vocal down 2 dB` now ask `which_track`
  instead of reporting no match. Both still have no action; 382 rows are unchanged.

Local run logs: `/tmp/kenn-track-choice-suite-2026-10-02.log` and
`/tmp/kenn-track-choice-mutations-2026-10-02.log`.

This closes the deterministic displayed-pair item. It does not qualify the full
five-turn model conversation or the Mac model-answer latency gate; both remain
open in the North Star.
