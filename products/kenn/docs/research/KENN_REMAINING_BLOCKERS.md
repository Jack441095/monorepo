# KENN remaining blockers

## Release blockers

| Blocker | Evidence now | Why it blocks | Unblock proof |
|---|---|---|---|
| Real Ableton offline | Real read-only qualification returned AbletonOSC offline | No real mutation/readback/undo reliability claim is valid | Versioned real-host read-only and disposable mutation receipts |
| Browser and hosted CI qualification | Fresh `npm ci`, zero-vulnerability audit, tests and build passed locally | Browser behavior and the newly added hosted workflows have not yet produced remote receipts | Green core/native workflows plus browser E2E on supported hosts |
| Semantic retrieval assets missing | `embeddings.npy` absent; BM25 fallback warning | Intended semantic behavior, latency and quality are unmeasured | Rebuilt versioned index, retrieval gold set and quality/latency report |
| Ableton manual not indexed | Grounding audit reports zero manual chunks | Advice cannot be claimed manual-grounded | Licensed/approved corpus ingestion plus citation/answer evaluation |
| Duplicate divergent KENN trees remain locally | canonical, legacy, product-root and standalone copies differ; only the canonical tree is in the reviewed source boundary | Local operators can still edit the wrong runtime | Owner-approved archive/retention action after backup; keep import-path CI |
| Native packaging not reproducible | Local extension exists and matches a fresh build, but no clean-clone wheel matrix was proven | Local success does not establish distributability | CI-built signed/hashed artifacts for supported ABI/architectures |
| Full realtime proof incomplete | Release plugin tests pass, but the performance test is a kernel and the build is not TSan | Data races/deadline failure may remain in full callback | TSan/control-thread suite and full callback deadline matrix |

## Capability blockers

- AudioGen: the KENN typed contract exists, but the producer implementation is outside the canonical checkout and no real generation-to-Live receipt was produced.
- SLO: the KENN manifest validator exists, but production C++ source is in the adjacent checkout and no live manifest/index handoff exists.
- Arrangement: synthetic evaluation passes four cases, but real Live arrangement execution was not authorized or qualified.
- Open-ended coproducer behavior: the 111/111 result covers deterministic parser vocabulary. It does not establish reference resolution, musical judgment or model generalization.
- Restart durability: confirmation/proposal semantics fail closed, but seamless durable recovery of in-flight action state is not proven.
- Security and tenancy: local-only defaults and CORS were tightened, but authentication, multi-user isolation, secret handling and threat modeling are not production-qualified.

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
