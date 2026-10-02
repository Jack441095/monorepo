# Public-wrapper index isolation — 2 October 2026

This records a bounded A3 repair in [KENN_PLAN.md](../../KENN_PLAN.md).

## Reproduced behavior and repair

Importing either public knowledge wrapper disabled the shared model environment
and could redirect the shared corpus through its configured index override.
Both imports now preserve the caller's model policy and default corpus. Each
wrapper retains retrieval-only request policy and selects its read corpus in a
`ContextVar` scope restored in `finally`, including nested, thread and async use.
An invalid override returns the existing unavailable-index abstention shape
without reading the default corpus or creating a directory.

Lexical bundles and embedding matrices reserve their existing default cache and
keep at most two alternate bundles each. Alternate artifact fingerprints detect
in-place replacements, including equal-size replacements. Status describes the
selected corpus instead of borrowing a warmed default matrix or its failure.
Semantic cache versions include a digest of the selected corpus identity as well
as its version, so equal version labels in different corpora cannot share answers.
Default build, promotion and write destinations retain their existing ownership.

## Verification

The three scoped commands passed 132 cases, including 28 new cases. Four
temporary-copy mutations were caught: each wrapper's import-time model disable,
ignored read selection and removed lexical replacement fingerprint. No model,
network or Live calls were used. Original scoped stdout was returned by tools
and was not retained as files; these are recorded command results.

```sh
# From products/kenn/apps/backend/src: 31 passed in 0.36 s
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_read_index_context.py kenn/tests/test_retrieval_status.py kenn/tests/test_index_store_validation_cache.py kenn/tests/test_semantic_cache_versioning.py kenn/tests/test_retrieval_index_candidate.py

# From products/kenn: 49 passed in 5.15 s
apps/backend/.venv/bin/python -m pytest -q -p no:randomly chat/tests/test_app.py chat/tests/test_import_isolation.py

# From products/kenn/packages/chat: 52 passed in 1.47 s
../../apps/backend/.venv/bin/python -m pytest -q -p no:randomly tests/test_app.py
```

The combined backend run passed **3,413 tests, 12 skips and six existing warnings
in 102.25 s**, including the concurrent reference, status, cancellation and stream
repairs. It precedes the subsequent unused-helper cleanup. Optional runtime and
asset skips remain; no dependencies, index rebuild or CI changes were made.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/retrieval/index_store.py`: scoped read-corpus owner.
- `apps/backend/src/kenn/retrieval/retrieval.py`: selected matrix cache and status.
- `apps/backend/src/kenn/core/chat_retrieval.py`: selected lexical cache.
- `apps/backend/src/kenn/core/session_memory.py`: corpus identity in cache versions.
- `apps/backend/src/kenn/tests/test_read_index_context.py`.
- `apps/backend/src/kenn/tests/test_retrieval_status.py`.
- `chat/app.py` and `chat/tests/test_app.py`.
- `chat/tests/test_import_isolation.py`: fresh-process checks for both wrappers.
- `packages/chat/app.py` and `packages/chat/tests/test_app.py`.
- `docs/evidence/KENN_WRAPPER_INDEX_ISOLATION_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: bounded wrapper-import and corpus-isolation check.
