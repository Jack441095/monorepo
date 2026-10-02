# Confirmation token alias on Live apply — 2 October 2026

An A2 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md).

## Reproduced defect and changed behavior

`handle_live_command` resolves the confirmation token as `confirm_token` or, failing
that, `confirmation_token`, and the FastAPI route does the same. Proposals hand the
client the key `confirmation_token`. But every apply branch in
`routes/daw_command_handler.py` then read `payload["confirm_token"]` again, so a client
that sent only `confirmation_token` reached the service with an empty token and was
refused. `handle_safe_live_action` had the same gap.

All nine sites now use the resolved token. When both keys are sent, `confirm_token` still wins.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_daw_command_handler.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- `test_daw_command_handler.py`: 12 passed. The alias is covered for the generic command,
  both MIDI clip schemas, clip duplication, rename, audition (play and stop), sample
  import and remove, and `handle_safe_live_action`.
- Each of the nine sites was mutated back to the old read in turn. All nine are caught
  (my first run left six surviving until the parametrized test was added). The file was
  restored and byte-compared.
- Full backend, run on the combined tree with the feedback slice: 3,500 passed, 12 skipped, no failures (124.42 s).

## Limits

- The services are faked; the test shows the token arrives, not that Live accepts it.
- Other `confirmation_token` readers (`doctor_handler`, `racks_handler`) read the token
  from the stored proposal and were not changed.
- `routes/daw_routes.py` still carries its own copy of `handle_live_command`; removing
  that duplicate owner is not done here.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/routes/daw_command_handler.py`
- `apps/backend/src/kenn/tests/test_daw_command_handler.py`
