# SLO classification integration

SLO remains the classifier owner. KENN consumes classification results through a read-only boundary:

```text
SLO SQLite cache → KENN adapter → KENN GET routes → typed Vue API → SLO Library UX
```

## Backend

- Adapter: `apps/backend/src/kenn/core/slo_classification_adapter.py`
- HTTP routes: `apps/backend/src/kenn/server.py`
- Tests: `apps/backend/src/kenn/tests/test_slo_classification_adapter.py` and `test_slo_classification_routes.py`
- Schema: `kenn.slo-classifications/v1`
- Routes: `GET /api/slo/classifications` and `GET /api/slo/classifications/{sample_id}`
- Browser proxy form: `/kenn/api/slo/classifications`

The adapter opens SQLite with `mode=ro` and `PRAGMA query_only = ON`, strips absolute paths, returns opaque IDs, clamps confidence and preserves OOD/user-override semantics.

## Frontend

- API/types: `apps/frontend/src/api/sloClassification.ts`
- State: `apps/frontend/src/composables/useSloClassification.ts`
- UX: `apps/frontend/src/components/studio/SloClassificationPanel.vue`
- Fixtures: `apps/frontend/src/mocks/sloClassifications.ts`
- Tests: `apps/frontend/src/api/sloClassification.test.ts`

OOD classifications are displayed as **Needs review**, never as a guessed known class. Mock mode and production mode use the same normalized TypeScript contract.
