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
- **Usability with producers.** The L3 producer questions (can they inspect and edit a suggestion, do they understand a
  partial-change receipt) need people, not fake Live.
- **A gain-staging undo is not linked to the change it reversed.** Its receipt carries no action_id, so "Undo that" stops
  on it rather than walking past. It only stops; it never redoes a change.

## Closed after the requal (9 Oct, merged at 757ae30f)

Each fix had its own branch and an adversary review. The full suite on merged main gives 4395 passed and 137 skipped in a
clean worktree. The frontend gives 69 passed and `vue-tsc` is clean.

- **A recipe undo could overwrite a later hand edit.** Recipe undo now compares each step's readback with Live, and
  refuses by naming the moved control (`draft/recipe-undo-stale`).
- **"Undo that" refused after a card that was refused before writing.** Those receipts now carry `write_attempted: False`,
  and the walk skips them. A failure after the write went out still stops it (`draft/undo-skip-prewrite`).
- **The Undo button on an undo card redid the change.** Undo cards no longer offer Undo (`draft/undo-card-no-redo`).
- **"Undo that" after the card's Undo button redid the change.** This was found in review. The HTTP undo route now
  records the undo link, and device-parameter undos are keyed by the id their receipt carries. Before, they were never
  linked from chat either (`draft/button-undo-link`).
- **The mud card could describe a pan it never read.** "Add a compressor to clear the mud" reached the translator
  without a mixer read and called a sub panned 30% left "mono-centered". The mixer is now read before any mix metaphor is
  translated. A sweep of 359 phrasings found none reaching the translator without fader values (`draft/mud-mixer-read`).
