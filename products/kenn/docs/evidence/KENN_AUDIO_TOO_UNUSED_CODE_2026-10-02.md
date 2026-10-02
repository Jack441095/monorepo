# Unused KENN and Audio_Too code — 2 October 2026

This bounded cleanup follows `dd682f0d`; source comparisons use
`b1d97ad105832105ff43701cd95d66388bdcbbbb`, with identical source at both revisions.
The wider audit remains open in [KENN_PLAN.md](../../KENN_PLAN.md).

## Exact changes

Paths are relative to the monorepo root.

| Source file | Removed code and retained behavior |
| --- | --- |
| `Audio_Too/scripts/generate_notes_from_transcripts.py` | Uncalled `_is_duplicate`; `_save_note` still rejects existing note files. |
| `Audio_Too/server/agents/Shared/agent_llm.py` | Uncalled `_ollama_generate_stream`; active chat/generate wrappers retain their complete, nonstreaming HTTP responses. |
| `Audio_Too/server/app/automix_worker.py` | Uncalled `_get_next_queued_job`; active loops retain atomic job claiming and leases. |
| `Audio_Too/server/app/studio_tips.py` | Uncalled `_dynamic_starter_extra`; public catalog still excludes private dashboard questions. |
| `products/kenn/apps/backend/src/kenn/core/midi_clip_service.py` | Second return after an unconditional return in `execute_remove`; public response, readback, receipts and Undo remain unchanged. |
| `products/kenn/apps/backend/src/kenn/core/live_recipe.py` | Unused `math` import. |
| `products/kenn/apps/backend/src/kenn/core/stem_unmasking.py` | Unused `math` import. |
| `products/kenn/apps/backend/src/kenn/core/vocal_surgeon.py` | Unused `asdict` import; retained dataclasses remain unchanged. |
| `products/kenn/apps/backend/src/kenn/core/stem_packager.py` | Unused `json` import. |
| `products/kenn/apps/backend/src/kenn/core/genre_profiles.py` | Unused `Any` import. |

Audio_Too source loses **66 lines**, including spacing. KENN source changes
**2 lines and removes 11**, solely for the five import bindings and unreachable
return. Caller, export, dynamic-registry and packaging checks precede deletion.
All remaining module AST statements match the original after precisely those
removals; all ten modules compile without importing or executing them. The MIDI
method's bytecode, constants, names and exception table are identical.

Three README corrections also accompany this batch:

- `products/kenn/chat/README.md` and `products/kenn/packages/chat/README.md`
  name the product-owned backend path and request-local retrieval policy. They
  remove obsolete external-checkout/global-disable claims and automatic index-build
  directions; local commands, runtime storage and deployment limits match current
  ownership. Deployment configuration examples remain configuration examples.
- `products/kenn/packages/mix-review/README.md` names implemented measurement
  families, conditional abstention and the current adapter command. It replaces
  retired qualification pointers with the sole plan and historical internal evidence,
  without treating source labels as release or human-listening qualification.

## Scoped verification

From `products/kenn/apps/backend/src`, with FakeLive, model switches off and
DB/chat/session/journal paths isolated under a temporary runtime:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_midi_clip_service.py kenn/tests/test_midi_generation_chat.py kenn/tests/test_idempotency_bounds.py kenn/tests/test_audit_p0_regressions.py kenn/tests/test_mix_recipes.py kenn/tests/test_subjective_translation.py kenn/tests/test_vocal_surgeon.py kenn/tests/test_stem_packager.py kenn/tests/test_stem_unmasking.py kenn/tests/test_genre_and_track_intelligence.py
```

Result: **75 passed in 1.37 s**, no failures, skips or warnings.

The Audio_Too launch from the monorepo root was:

```sh
products/kenn/apps/backend/.venv/bin/python /tmp/audio-too-helper-cleanup-verify-2026-10-02.py
```

Result: **21 passed in 1.80 s**: 14 existing mocked/pure cases plus seven temporary
offline cases at public seams. These cover transcript retries, existing-note
preservation, opt-in correction policy, public starters, complete HTTP response
wrappers and job claim/lease behavior. Four compiled-copy mutations are caught;
repository source was not mutated and no repository tests were added for absence
alone. Network, child processes and repository writes were blocked in that launch;
SQLite, Numba cache and pytest runtime paths were external and isolated.

An initial Audio_Too collection lacked the existing `nite_core` source root.
Adding the repository's existing `shared/` directory to that temporary launch's
`PYTHONPATH` resolved it without installation or repository configuration changes.
The real-Ollama test module was not collected.

Detailed commands, environment, hashes and logs are retained locally in
`/tmp/audio-too-helper-cleanup-2026-10-02/receipt.json` and
`/tmp/kenn-bounded-deletion-2026-10-02/receipt.json`. Parent review confirmed all ten
final source hashes match these receipts. Added local document links and command
paths resolve; `git diff --check` passes.

The earlier package-wrapper evaluation's two existing failures remain open and
were not rerun by this independent deletion batch. No full-suite, container,
plug-in, model-speed or release pass is claimed. No model call, index rebuild,
private audio intake, dependency/CI change or Live write occurred. The nine tracked
Audio_Too compatibility symlinks and active re-export/registry candidates remain.
