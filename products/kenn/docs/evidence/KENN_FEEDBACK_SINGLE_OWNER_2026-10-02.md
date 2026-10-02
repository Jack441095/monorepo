# Feedback route single owner — 2 October 2026

An A2/A3 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and was found while
tracing the duplicated HTTP owners.

## Reproduced defect and changed behavior

`/api/feedback` had two owners that disagreed. The FastAPI handler in
`routes/chat_routes.py` answered "Feedback recorded." for any rating and stored nothing.
The stdlib handler in `routes/feedback_handler.py` validates the rating and stores through
`demo_feedback`, and answers 503 when that module is missing, which is the case in this
tree. So the FastAPI path claimed a rating it had thrown away.

`feedback_handler.feedback_result(payload) -> (status, body)` now holds the logic and both
entry points call it. FastAPI returns 503 when nothing can store the rating, 400 for a
rating the store does not know, and 201 with the stored row otherwise.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_feedback_single_owner.py
```

- `test_feedback_single_owner.py` (new) covers the missing store, rejected ratings, a stored
  row and stdlib/FastAPI parity. Five deliberate mutations were each caught; the edited
  files were restored and byte-compared.
- Full backend, run on the combined tree with the token alias slice: 3,500 passed, 12 skipped, no failures.

## Limits

- `demo_feedback` is missing from the tree, so the stdlib server also answers 503 on
  `/api/feedback`. Feedback is therefore not stored anywhere today. Restoring the module
  or routing to `save_session_feedback` needs a decision and is not done here.
- No in-repo caller of the route was found.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/routes/feedback_handler.py`: `feedback_result`.
- `apps/backend/src/kenn/routes/chat_routes.py`: `handle_feedback` delegates to it.
- `apps/backend/src/kenn/tests/test_feedback_single_owner.py` (new).
