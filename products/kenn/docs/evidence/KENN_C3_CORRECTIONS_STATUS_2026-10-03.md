# Where the conversation work stands, 3 October 2026 (end of session)

Branch `fix/review-critical-2026-10-02`. Pushed: `d69db4b1` (invented analysis fixed). Main is still `ce8e2a49`.
Not committed: the correction handling below, in the working tree only.

## Done and pushed

- Five-turn runner and six scripted conversations (`e36fb8c7`), first real-model run written up in
  [KENN_C3_FIVE_TURN_FIRST_RUN_2026-10-03.md](KENN_C3_FIVE_TURN_FIRST_RUN_2026-10-03.md).
- Asking about an analysis that never ran now says so (`d69db4b1`, 12 tests, KENN suite 3,571 passed / 5 skipped).
  Wording-based; renders and stem scans are not covered.

## Done in the working tree, not committed

`core/chat_routing.py`: `is_correction_query` ("No, ...", "Sorry, it is the guitar, not the vocal", "I meant X, not Y")
now counts as a follow-up, so the chat history is used. The search for a correction takes the last two user turns and
drops the "not the vocal" part. "And the attack?" is a follow-up too. The model is told it is a correction through
`history_context_line`. Tests: `tests/test_correction_followups.py` (10 pass).

Checked without the model: the drum-bus and attack turns now search with the earlier question and use history.

Still wrong: "Sorry, it is the acoustic guitar that is muddy, not the vocal." still takes the Ableton controller route
(`orchestrator.py` classifies the query alone, with no history), so it gets the canned low-end reply, not the model.
Fixing that means giving the orchestrator the history or skipping it for corrections. Not done.

Not changed: "Cancel that, I will do it myself." is still searched against the previous question. Clarify replies
("What was the problem with it?") still ignore history. Topic changes still carry old context.

## Full suite

First run stopped at one failure, `test_server_smoke.py::test_main_chat_can_combine_explicit_mix_review_and_plugin_evidence`
(3,199 passed before it). It passes alone, with and without this change. It is the order-dependent smoke failure seen
before with a stale pytest cache; cause still unknown. The second full run, fresh cache dir, was clean: 3,581 passed,
5 skipped, 0 failed (the smoke test passed that time, so it is flaky by order, not broken by this change).

## Deep research on speed

Workflow `wf_79bf1216-30a` was in its verify phase (5 searches and 21 source fetches done) when this was written. It
costs a lot of agents. Its report has not been read; nothing from it is in the plan yet. Treat any web number as a
shortlist only, and new dependencies or model files need Jack's OK.

## Next, in order

1. Read the second full-suite result; commit the correction work only if it is clean apart from the known smoke test.
2. Give the orchestrator the history for correction turns.
3. Read the research report and pick one or two speed experiments for C2.
4. The 15 s gate is still failed on both surfaces; C1, C2, C3 stay unticked.
