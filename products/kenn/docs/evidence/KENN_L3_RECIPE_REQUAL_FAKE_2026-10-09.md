# L3 recipe requalification on fake Live — 8–9 October 2026

L3 asks for at least 15 recipes qualified on fake Live first, then on a disposable real set that Jack schedules. This note covers
the fake half against main at `a646f1de`. L3 stays open until the real-Live rerun.

## Result

14 of 15 recipes qualified. Each one ran Propose, Apply, readback and Undo, and the mixer ended back where it started.
`glue_drum_bus` fails because the fake fixture has no Glue Compressor template; it needs real Live.

| Run | Commit | Passed | Mixer back at start |
| --- | --- | ---: | --- |
| Before the fixes | `fbc12419` | 14/15 | yes |
| After merging the three branches below | `a646f1de` | 14/15 | yes |

Raw results are in `kenn-evaluation-data/2026-10-08-recipe-requal/`:
- `fake-main-fbc12419.json` and `fake-main-a646f1de.json`, from `tooling/scripts/qualify_recipes_live.py`.
- `card-texts-main-a646f1de.json`, which holds the card, applied, undo-card and undone text for every recipe.

## What the requal found, and what was fixed

1. **"Undo that" refused after a stale card.** A recipe that aborted and read back as fully restored still counted as the
   latest change. `undo_target` stopped on it, so the producer's previous change could not be undone. A clean
   `failed_rolled_back` is now skipped. Plain `failed` and `partial_recovery` still stop the walk, because the set may hold a
   change we could not verify. Merged in `d7001ae8`.
2. **A garbled device readback could skip the rollback.** The post-write parameter parse sat outside the `try`. An exception
   there left no step receipt, so the rollback would skip a step that had already written, and the recipe still reported
   itself cleanly restored. The parse is now inside the `try` (`d7001ae8`).
3. **Stale-card and partial-failure behaviour had no end-to-end test.** Now tested through `handle_command` (`851d0697`):
   - A renamed track writes nothing.
   - A stale second step rolls back the first step it already wrote, and the producer's own 40% send is left alone.

   The rollback test was mutation-checked: it fails with `_restore_step` disabled.
4. **Cards a producer could not read.** Fixed in `a646f1de`:
   - Every recipe undo card read "I can set recipe on 'ableton_recipe' from None to None". It now lists each value it puts back.
   - Single-send undo cards said "0.4 normalized". They now say "from 40% to 0%".
   - The Compressor Threshold card never showed the -3 dB it was about to set. It now reads "0.0 dB -> -3.0 dB".
   - The low-end-mud card promised to centre a sub bass the demo set does not have. It now describes only the moves it makes.
   - The low-end-mud recipe never centred a panned sub at all, because it read a pan key track snapshots do not carry.

After the merge, no card or undo card across the 15 recipes contains "None", "normalized" or "ableton_recipe". The
stale-card probe applies an old "Give the vocal some space" card after the producer moved the delay send. It gets
`failed_rolled_back` with one step restored. "Undo that" then offers to put that send back from 40% to 0%, and the mixer ends
where it started.

Stop and cancel is covered by the existing confirmation tests, for example
`test_recipe_has_one_pending_confirmation_and_retires_hidden_child_tokens` in `test_confirmation_revocation.py`.

## Review

Each change was on its own branch and was attacked by a read-only adversary reviewer before merge. Verdicts:
- Undo fix: merge.
- Stale-card tests: merge.
- Card wording: merge with nits. Two nits were fixed before merge: a card shows our converted value only when a measured
  profile exists, and the mud recipe reads either pan key.

The full KENN suite on merged main gives 4505 passed and 1 failed. The failure is
`test_llm_task_switch.py::test_command_planner_can_be_enabled_without_chat_llm`. The main checkout's local, gitignored
`products/kenn/.env` sets `KENN_LLM_ENABLED=1`, and that test assumes no global switch. The test passes in a clean worktree.

## Still open

- **Real-Live rerun** on a disposable set, on a night Jack schedules. It also qualifies `glue_drum_bus`, and checks that the mud
  recipe's new pan-to-centre write behaves on a real sub.
- **A recipe undo can overwrite a later hand edit.** Recipe `propose_undo` does not compare the step readback with the current
  value. This predates the requal.
- **"Undo that" still refuses when the previous change failed before writing anything.** Those receipts are plain `failed`.
  They need a "no write attempted" marker before the walk can skip them safely.
- **"Undo the plan" redoes the change after an undo recipe is applied.** The button on that card calls `propose_undo` on the
  undo's own receipt.
- **Other phrasings may build the mud card without a mixer read.** Phrasings other than "Fix the low-end mud" may reach the
  translator without a mixer snapshot, so the card could describe a pan it never read.
- **Usability with producers.** The L3 producer questions (can they inspect and edit a suggestion, do they understand a
  partial-change receipt) need people, not fake Live.
