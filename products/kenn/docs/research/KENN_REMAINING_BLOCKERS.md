# KENN remaining blockers

## Release blockers

| Blocker | Evidence now | Why it blocks | Unblock proof |
|---|---|---|---|
| Real Ableton offline | Real read-only qualification returned AbletonOSC offline | No real mutation/readback/undo reliability claim is valid | Versioned real-host read-only and disposable mutation receipts |
| Browser qualification missing | Hosted core and native matrices are green; frontend install, audit, tests and build also pass locally | Browser-level startup, fallback, proposal and recovery behavior remain unqualified | Browser E2E on supported hosts with failure-only traces |
| Retrieval assets missing | The clean checkout is configured for BM25-only fallback, but has no approved lexical corpus/index; the embedding index and runtime assets are also absent, so the active mode is unavailable | Lexical and semantic behavior, latency and quality are unmeasured | Approved versioned corpus and indexes, retrieval gold set and quality/latency report |
| Ableton manual not indexed | Grounding audit reports zero manual chunks | Advice cannot be claimed manual-grounded | Licensed/approved corpus ingestion plus citation/answer evaluation |
| Duplicate divergent KENN trees remain locally | canonical, legacy, product-root and standalone copies differ; only the canonical tree is in the reviewed source boundary | Local operators can still edit the wrong runtime | Owner-approved archive/retention action after backup; keep import-path CI |
| Native promotion evidence incomplete | Hosted macOS and Windows wheel builds, import checks, fallback checks and parity tests pass | Distributability is established for the tested runners, but release integrity and representative-corpus promotion evidence remain incomplete | Signed and hashed artifacts plus approved-corpus parity, performance and sanitizer evidence |
| Full realtime proof incomplete | Release plugin tests pass, but the performance test is a kernel and the build is not TSan | Data races/deadline failure may remain in full callback | TSan/control-thread suite and full callback deadline matrix |

## Capability blockers

- AudioGen: the KENN typed contract exists, but the producer implementation is outside the canonical checkout and no real generation-to-Live receipt was produced.
- SLO: the KENN manifest validator exists, but production C++ source is in the adjacent checkout and no live manifest/index handoff exists.
- Arrangement: synthetic evaluation passes four cases, but real Live arrangement execution was not authorized or qualified.
- Open-ended coproducer behavior: the 111/111 result covers deterministic parser vocabulary. It does not establish reference resolution, musical judgment or model generalization.
- Restart durability: confirmation/proposal semantics fail closed, but seamless durable recovery of in-flight action state is not proven.
- Security and tenancy: local-only defaults and CORS were tightened, but authentication, multi-user isolation, secret handling and threat modeling are not production-qualified.

## Implementation-ready next steps

| Work item | First owned change | Completion evidence |
|---|---|---|
| Durable action state | Persist proposals, confirmations, idempotency keys and receipts from `core/live_action_service.py`, `core/confirmation.py`, `core/idempotency_bounds.py` and `core/receipt_contract.py` in one versioned store with expiry and project/session identity. | Restart tests prove replay rejection, confirmation expiry, receipt continuity and fail-closed behavior without duplicate mutation. |
| Startup reconciliation | Add an explicit uncertain-action ledger and startup reconciler that compares the last precondition, intended mutation and fresh Live readback before enabling further writes. | Crash-at-each-boundary tests end in reconciled success, safe inverse proposal or a visible blocked state; none silently retry. |
| Real-host Live qualification | Bring AbletonOSC online for the existing read-only qualifier, then use an explicitly authorized disposable set for one bounded action at a time. | Sanitized receipts cover proposal, confirmation, fresh precondition, mutation, readback, exact identity-bound undo and second readback. |
| Authorized retrieval index | Ingest only an approved corpus through `retrieval/corpus_ingest.py`, build versioned lexical and embedding artifacts, and bind model and source digests in the manifest. | BM25 and hybrid evaluation report recall, ranking, citations, cold/warm latency and failure behavior; health reports hybrid only with both index and model loaded. |
| AudioGen handoff | Connect the existing typed artifact contract to a production-owned generator endpoint, validate the artifact, and route insertion through the normal Live proposal path. | A generation-to-artifact-to-disposable-Live receipt proves target identity, readback and undo; invalid or missing artifacts fail closed. |
| SLO handoff | Define the production manifest, model identity, taxonomy, confidence/OOD thresholds and search contract consumed by the existing `core/slo_*` adapters. | Versioned fixtures prove manifest validation, representative and OOD classification, search handoff and visible unavailable-state behavior. |
| Browser E2E | Add a supported browser runner for startup, health/fallback display, chat, proposal confirmation, stale-state rejection and offline recovery. | The clean hosted run publishes repeatable browser results with screenshots or traces retained only on failure. |
| Native promotion gate | Run Python/native parity and performance on an approved representative corpus, including malformed files, p95/p99 latency, same-process RSS/copies and sanitizer coverage. | Promotion requires declared numerical tolerances, at least 3x p95 end-to-end gain, clean sanitizers and reproducible wheels; otherwise Python remains the diagnosed fallback. |

## Explicitly rejected shortcuts

- Do not call mock Ableton qualification “Live tested.”
- Do not promote the complete Mix Review native path for a 1.13x p50 gain.
- Do not rewrite network/policy/retrieval orchestration in C++ without a measured bottleneck.
- Do not enable direct plugin-to-Live writes; keep the companion service and confirmation/readback authority.
- Do not infer object identity from names or positions when stable IDs/revision checks are unavailable.
- Do not silently treat BM25 fallback as semantic retrieval.
- Do not edit the adjacent AudioGen/SLO checkout from KENN without a separately owned integration change.

## Evidence caveats

The main and adjacent repositories were both dirty before the audit. Existing modifications were preserved. The adjacent checkout was read only. Fresh measurements are host-specific, mostly synthetic, and do not substitute for a supported-machine distribution. Local audit commits were created with descriptive metadata; contaminated older local-only history is excluded from publication.
