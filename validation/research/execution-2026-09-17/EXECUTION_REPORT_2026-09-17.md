# EXECUTION REPORT — 2026-09-17 (plan of record: deep-research-2026-09-17)

> Pre-existing dirty trees were NOT disturbed. All commits on `exec/*` branches only (never main, never pushed, never mirrored). No secrets printed. No large blobs committed.

## Starting state (observed)
- monorepo on `ops/mirror-and-notes`, dirty (backend/app + tests in-progress modifications; products/platform/Audio_Too/etc untracked)
- products/slo on `main`, dirty (CMakeLists, PluginProcessor, SampleManagerEngine, taxonomy docs)
- products/nite-submit on `engineering/nite-submit-v1.1-beta`, dirty (artifact deletions + corpus results in progress)
- Shenrendao/KENN on `develop`, dirty (CHANGELOG, UX/index.html, docs/ reorganisation renames)
- Branches created (pointers, working trees untouched): monorepo `exec/I-T1-01..I-T1-06`

## TIER 1 receipts

### I-T1-01 canonicals + drift gate — DONE (tooling) / owner decision PENDING
- Branch: monorepo `exec/I-T1-01-canonicals`, commit `09bb007` (1 file, `scripts/drift-gate.sh`, 39 lines). Rollback: `git checkout ops/mirror-and-notes && git branch -D exec/I-T1-01-canonicals`.
- Before: no drift detector. After: `sh scripts/drift-gate.sh` → EXIT=1 with real drift: backend/app vs platform/backend/app differ in commerce.py, licensing.py, rate_limit.py, schemas.py; kenn-skeleton OK (0 .py); scaffolds OK (empty); tracked-secrets OK; tracked-binaries OK.
- Recommended canonicals (AWAITING_OWNER 7d): SLO→Nite-DSP/slo, Submit→nite-submit-private, KENN→kenn-standalone, platform→monorepo root, Thursday→pick one side, Audio_Too→private tooling. Deletions of duplicate skeletons NOT performed (owner confirm first). DoD: PARTIAL (gate script green-tooling done; deletions pending).

### I-T1-02 secrets hygiene — DONE (audit) / rotation N/A
- Branch: `exec/I-T1-02-secrets` (pointer, no commit — nothing to change). Before/after: `git ls-files | grep env|key` → only `backend/migrations/versions/6c3e9e1d4b7a_add_private_beta_release_channel.py` (filename) + `backend/staging_keys/licensing_signing_key.public` (public key, safe). Untracked-but-present (names only): Audio_Too/.env, Audio_Too/nitedsp/backend/.env + staging_keys, website/.env.local, platform/backend/.env + staging_keys, platform/website/.env.local — correctly UNTRACKED per .gitignore. No tracked private values found → no rotation required. DoD: YES (audit) with standing rule: keep .env untracked, never commit.

### I-T1-03 testability — DONE (backend+KENN reproduced) / SLO patch PREPARED
- Branch: `exec/I-T1-03-testability` (pointer; env fix lives in workspace `.venv`, outside product trees per guardrail).
- Backend before: `pytest --collect-only` → `ModuleNotFoundError: nacl` (0 collected). Fix: installed `backend/requirements.txt` into workspace `/Nite-DSP/.venv` (NOT into backend/). After (workdir=backend): **106 passed in 3.12s**. Note: invoking from monorepo root yields 9 collection errors (`No module named 'app'/'scripts'`) — sys.path expects backend/ cwd; CI `backend.yml` must `cd backend` or set PYTHONPATH (follow-up I-T2-06).
- KENN mix-review: **reproduced B F-03 exactly: 5 failed / 53 passed in 2.67s** — failures: 24-bit PCM, 32-bit float, calibrated LUFS vs BS.1770 (`KeyError: 'integrated_lufs'` at test_local_engine.py:372), true-peak inter-sample, full-benchmark qualified. R-03 premise VERIFIED.
- KENN full suite: 1136 collected, 5 collection errors — all environmental (`No module named 'pypdf'/'sklearn'`, system python3): test_calibrator, test_index_store_validation_cache, test_local_manual_opt_in, test_retrieval_evidence_classes, test_retrieval_index_candidate. Fix path: install KENN requirements into a venv (same pattern as backend).
- SLO CTest: confirmed 0 hits for enable_testing/add_test/CTest in CMakeLists.txt; custom `ssm_add_engine_test` helper (CMakeLists.txt:~760) builds executables without registering them. PREPARED patch (NOT applied — slo tree dirty on main): add `include(CTest)` + `enable_testing()` near top, plus one `add_test(NAME <t> COMMAND <t>)` line inside `ssm_add_engine_test` after `add_executable`. Awaiting clean tree. DoD: PARTIAL (2/3 receipts green).

### I-T1-04 dep pins — AUDITED / patch PREPARED
- Observed matrix: JUCE 8.0.2 pinned (FetchContent ✓), umappp 3.3.2 ✓, dr_libs 0.14.5 ✓, hnswlib 0.8.0 ✓; TagLib + ONNX Runtime brew `find_path` UNPINNED (host: taglib 2.3.1, onnx 1.29.0_3); Python 3.11 (KENN Docker) vs 3.12 (Audio_Too) vs 3.13 (CI + workspace venv); Swift-tools 5.9. No code change applied (dirty trees) — pin proposal in report: FetchContent or version-guard `find_package` for TagLib/ONNX; align CI python with Dockerfile. DoD: PARTIAL (matrix done, pins awaiting clean tree).

### I-T1-05 loopback fail-closed — HALF-DONE / flip AWAITING_OWNER
- DiskSweep: DONE-BY-CODE — `--no-llm` flag exists (`sidecar/cli.py:172,183,190`) and `--help` proves it; rules-only fallback automatic when Ollama unreachable (`ollama_client.py:11`, `classifier.py:150`). No change needed.
- KENN: default provider is `openai` (`source/kenn/llm/llm_rewrite.py:170`, model `gpt-4o-mini`, base `https://api.openai.com/v1` at :182; ollama base only when provider==ollama). Flipping default to ollama changes shipped behaviour → AWAITING_OWNER brand-promise decision (7d). PREPARED 1-line patch: `:170` default `"openai"` → `"ollama"` + UX disclosure line; not applied. Per REFUSALS, no cloud-by-default variant introduced by us. DoD: PARTIAL.

### I-T1-06 archive scaffolds — AUDITED / removal AWAITING_OWNER
- Listing: `products/nite-paraphrase/{engine,evals,tests}` 0 files (empty ✓); `products/nite-submit-windows/` 0 files (empty ✓); `products/nite-files/` source absent, only `.build/*.o` + `artifacts/Files-0.1.0-macOS.{dmg 456K, zip 220K}` (orphaned ✓). No deletions performed — bundled with I-T1-01 owner confirm (single deletion batch). DoD: PARTIAL.

## GATE 1 verdict: CONDITIONAL-GO
Tooling + audit + backend-green + KENN-repro complete. Code edits on dirty trees (SLO CTest, dep pins, KENN default flip, deletions) correctly deferred. No gate item is red due to our work — reds are owner-pending decisions, listed below.

## TIER 2 prep (no Tier-2 code changes made this pass)
- I-T2-01 Submit: toolchain PRESENT (`tools/{sign_and_notarize.sh,verify_release_artifacts.sh,verify_app_bundle.sh,run_release_checks.sh,...}`, artifacts Submit-1.0.0.{app,dmg,zip}+manifests). Execution needs Apple identity + notarisation upload → AWAITING_OWNER. Checklist prepared: `verify_release_artifacts.sh` → parity gate → `sign_and_notarize.sh` → publish receipt.
- I-T2-02 Paddle: HMAC verified by code (commerce.py:100-130); sandbox live-fire needs `paddle_api_key`/`paddle_webhook_secret` values → BLOCKED_ON_SECRET (paths only, never printed). Prepared: duplicate/replay/out-of-order webhook matrix for sandbox.
- I-T2-06 CI: backend.yml + website.yml `workflow_dispatch`-only confirmed; drift-gate.sh ready to wire (1 job line) once I-T1-01 canonicals decided. Patch prepared, not applied.
- I-T2-03/04/05 (SLO/KENN/DiskSweep): correctly HOLD — gated on R-01/R-03/R-05 numbers, which need full research runs.

## TIER 3: NOT STARTED (Gate 2 unmet by design — research runs are separate tasks)

## Research observations (numbers, not decisions)
- R-03 premise REPRODUCED (5F/53P, same tests). R-10 backend arm DONE (106 passed). R-07 signature arm DONE by code read; live-fire BLOCKED_ON_SECRET. R-01/R-02/R-04/R-05/R-06/R-08/R-09/R-11: premises hold from A/B reconciliation; runs not started (each is its own timeboxed task).

## Owner actions (the entire HOLD list)
1. Canonicals per product + approve deletion batch (I-T1-01/06) — 7d.
2. Local-first promise: KENN default ollama? Submit Sparkle disclosure? (I-T1-05) — 7d.
3. Apple identity + notarisation go-ahead (I-T2-01) — 14d.
4. Paddle sandbox secrets for live-fire (I-T2-02) — 14d.
5. Clean-tree windows for SLO CTest + dep pins (I-T1-03/04) — schedule with repo owners.

## Self-check
Branches: 6 exec/* on monorepo, 1 commit (09bb007, additive only); zero main commits; zero pushes (no remote writes performed); zero secret values in outputs; zero blobs committed; every I-ID has receipt above; HOLD items cite kill-criteria/owner gates. Per-task before/after commands quoted. Rollback for the single commit: branch delete (above).
