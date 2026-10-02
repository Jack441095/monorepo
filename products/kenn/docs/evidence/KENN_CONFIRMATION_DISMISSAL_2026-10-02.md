# Confirmation dismissal — 2 October 2026

This records a bounded A3/A4 repair in [KENN_PLAN.md](../../KENN_PLAN.md).
It qualifies deterministic request behavior, not a real-Live release.

## Changed behavior

Dismiss used to hide a card while its held confirmation token remained usable.
The issuing chat can now revoke that token. Apply and revoke share the central
consumption lock, so a successful dismissal prevents a held card from executing.
A refused dismissal does not claim that an action already executing stopped.
Expired records are pruned, live revocation records survive until expiry and
pending-token storage has a 10,000-record limit that fails closed.

The HTTP route, its prefixed alias and FastAPI use the same revoke handler.
Malformed identifiers return 400; wrong-chat, expired, consumed or already
revoked tokens return 409. Neither the route nor its tests require Live I/O.
The frontend waits for acknowledgement, blocks concurrent Apply and keeps a
failed or uncertain dismissal retryable.

Pending state now counts live unconsumed tokens instead of a historical context
flag. Recipe construction revokes its hidden child tokens before issuing the
single parent token bound to the visible steps. Dismissing or consuming that
parent therefore clears the recipe's pending state.

Chat cancel revokes only its bound chat's pending tokens and invalidates that
chat's pending answer delivery. Its reply explicitly leaves inference running
and already executing or applied changes untouched. Streaming delivery uses
this shortcut in the separate stream repair.

## Verification

The initial central regressions failed before the revocation APIs existed.
Final compatibility checks passed 281 backend cases and 21 answer-upgrade cases.
The frontend passed 66 tests across eight source test files, including 53 focused
dismissal cases; typecheck and the production build passed. Temporary mutations
were caught for 28 backend and 14 frontend faults. All mutated sources were
restored. Existing locked frontend packages were restored with `npm ci`; package
manifests and the lockfile were unchanged.

The combined backend run, including the reference, observed-status, index and
stream repairs, passed **3,413 tests, with 12 skips and six existing warnings,
in 102.25 s**:

```sh
# From products/kenn/apps/backend/src
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

The skips concern optional MLX, sample-embedding and training runtimes/assets.
Warnings concern existing Starlette/httpx/anyio, Python audio compatibility and
the bundled OSC dispatcher escape sequence. No dependencies or CI were changed.
This result precedes the subsequent unused-helper cleanup.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/confirmation.py`: issuing, revoking, observing and
  consuming tokens under the shared lock.
- `apps/backend/src/kenn/core/live_recipe.py`: retire hidden child tokens.
- `apps/backend/src/kenn/core/chat_answer.py`: cancel shortcut only.
- `apps/backend/src/kenn/server.py`: pending-token observation and revoke route.
- `apps/backend/src/kenn/routes/daw_routes.py`: shared revoke handler.
- `apps/backend/src/kenn/routes/fastapi_app.py`: strict revoke request and route.
- `apps/backend/src/kenn/tests/test_confirmation_revocation.py`.
- `apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py`.
- `apps/backend/src/kenn/tests/test_server_smoke.py`: use an actually pending token.
- `apps/frontend/src/api/kenn.ts`, `api/paths.ts` and `api/kenn.test.ts`.
- `apps/frontend/src/composables/useKenn.ts` and `useKenn.test.ts`.
- `apps/frontend/src/components/KennActionCard.vue` and `KennRecipeCard.vue`.
- `apps/frontend/src/components/__tests__/KennActionCard.component.test.ts` and
  `KennRecipeCard.component.test.ts`.
- `docs/evidence/KENN_CONFIRMATION_DISMISSAL_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: bounded dismissal and cancel checks.
