# KENN execution roadmap

## Sequencing principle

Make the audited product reproducible, then prove the real Live safety loop, then improve intelligence. Optimizing or enlarging model behavior before stable project identity and real-host receipts would increase confidence faster than correctness.

## P0: reproducible baseline (days 0–5)

1. Put the intended canonical KENN tree under version control; preserve and triage the current dirty state. Remove or explicitly archive divergent duplicate trees after a file-level ownership review.
2. Repair clean-clone bootstrap: native build prerequisites, architecture-correct Node, Python lock/constraints, CMake presets and deterministic artifact locations.
3. Make CI run backend, scoped chat, Mix Review, frontend, native parity, plugin Release tests and JSON/schema validation.
4. Freeze the 1,275-test post-change backend baseline and benchmark receipts as comparison evidence, not hand-copied numbers.
5. Index the licensed/approved Ableton manual corpus and generate semantic embeddings with provenance; keep BM25 fallback visible.

Exit: a clean checkout on a supported Apple Silicon host reproduces the application, tests and optional native build without pre-existing binaries or untracked source.

## P0: real Live safety qualification (days 3–10)

1. Restore a supported Ableton Live + AbletonOSC test fixture and run the existing read-only qualification.
2. Use a disposable set to validate one operation from each mutation family: proposal, confirmation, precondition, apply, readback, receipt, retry/idempotency and inverse.
3. Exercise duplicate names, renamed/reordered/deleted targets, offline/reconnect, timeout, partial write, stale proposal and restart.
4. Capture versioned sanitized receipts and screen/Live state evidence. Never promote a mock result to real-host evidence.

Exit: all supported operations have verified real-host receipts or are disabled and truthfully surfaced.

## P1: canonical project graph and coproducer evaluation (weeks 2–4)

1. Build stable-ID, revisioned session and arrangement graphs from bounded batch observation.
2. Route all reference resolution and proposals through the graph; implement concise clarification for multiple candidates.
3. Run the versioned evaluation suite in `results/KENN_COPRODUCER_EVALUATION_SUITE_V1.json`, add blinded producer review, and publish per-stratum errors.
4. Add evidence/provenance to every factual explanation and calibrate abstention.
5. Implement inspectable scoped preference learning with held-out-user tests.

Exit: safety ≥0.95, target/tool ≥0.90, no unauthorized mutation, verified receipts 100%, musical/explanation median ≥4/5 on the defined held-out suite.

## P1: native analysis productionization (weeks 2–5)

1. Treat current C++ as opt-in while completing corpus parity, p95/p99 analysis, same-process copy/RSS profiling and malformed-file testing.
2. Add ASan/UBSan builds, TSan for shared state, explicit arm64/universal configurations and artifact provenance/SBOM.
3. Consolidate decode + analysis to minimize language crossings; retain a diagnosed Python fallback.
4. Promote bulk analysis if gates pass. Keep complete Mix Review native loudness optional unless end-to-end gain materially improves beyond the observed 1.13x.

Exit: ≥3x p95 end-to-end gain on representative files, parity within declared tolerances, sanitizer clean and clean-clone packaging proven.

## P2: integrations and arrangement depth (weeks 4–8)

1. Establish production-owned AudioGen endpoint/artifact contract, validate content and propose insertion with explicit target/readback.
2. Establish production SLO manifest/search handoff without copying source across repositories.
3. Add arrangement timeline/section reasoning and verified arrangement mutations on disposable sets.
4. Qualify local model/embedding inference only after comparing accuracy, cold/warm latency, memory and fallback behavior; ONNX Runtime/CoreML is a candidate, not a foregone conclusion.

## Next five concrete tasks

1. Inventory and commit the intended canonical KENN source in a clean review, excluding generated caches and binaries.
2. Reproduce the passing frontend test/build through clean `npm ci`, browser E2E and CI using a supported arm64 Node runtime.
3. Bring AbletonOSC online and run the read-only qualifier, then the disposable-set mutation matrix.
4. Build the revisioned project graph and stable-ID reference binder.
5. Run the native analysis promotion corpus with sanitizer and same-process memory/copy instrumentation.

## Dependency-aware implementation ledger

| Pri | Evidence / impact | Owner files/components | Change and language | Tests / benchmark gate | Risk, dependency, scope / done |
|---|---|---|---|---|---|
| P0 | Canonical product mostly untracked; releases cannot be reproduced | `products/kenn`, root `.gitignore`, CI | Review and track source/artifact boundaries; build-system work | Fresh-clone backend/frontend/native/plugin matrix | Owner triage; 2–4 days; done when a clean clone reproduces evidence |
| P0 | Real qualifier says AbletonOSC offline | `integrations/abletonosc`, `core/ableton_osc_bridge.py`, qualification scripts | Restore fixture and execute protocol; Python/Live Remote Script | Read-only then disposable-set mutation/readback/undo matrix | Requires Live/operator; 2–5 days; every enabled action gets a real receipt |
| P0 | Batch reply positional fallback and 1.5 s snapshot TTL can target stale/wrong state | `core/ableton_osc_bridge.py`, mutating services | Strict correlation IDs and forced fresh preconditions; Python | Reordered reply, timeout, stale snapshot and duplicate-name simulations plus real receipt | Protocol compatibility; 2–3 days; zero positional attribution |
| P0 | Nested OSC bundles and state maps can grow unbounded | `core/abletonosc_protocol.py`, `live_action_service.py`, `confirmation.py` | Decode depth/byte limits and TTL/size-bounded stores; Python | Malformed/deep bundle, long-uptime and expiry tests | Choose non-breaking limits; 1–2 days; bounded under adversarial load |
| P1 | Current frontend passes 5/5 tests and builds with bundled arm64 Node, but clean bootstrap/E2E remain | `apps/frontend`, lockfile, CI | Pin supported Node and qualify clean install/browser behavior | `npm ci`, unit tests, production build and E2E | Bootstrap/CI work; <1 day |
| P1 | Embeddings/manual corpus absent | retrieval/index builders and configured data roots | Versioned authorized ingestion and diagnostics; Python/model provider | Recall/precision gold set, citations, cold/warm latency, digest | Licensing/data provenance; 3–5 days |
| P1 | Stable project/arrangement identity incomplete | Live snapshot normalization, reference binder, proposal schemas | Revisioned typed graph; Python contracts | Rename/reorder/delete/duplicate/stale corpus; ≥0.90 target accuracy | Real Live observation; 1–2 weeks |
| P1 | Native analysis is fast but distribution proof is incomplete | `tooling/native/dsp_core`, `core/audio_analysis.py`, packaging CI | Retain C++20 kernels + Python orchestration/fallback | Corpus parity, ≥3x p95, same-process RSS/copies, ASan/UBSan, wheels | Numerical/platform drift; 1 week |
| P2 | AudioGen and SLO are contract-only in canonical checkout | `core/audiogen_*`, `core/slo_*`, adjacent owner endpoints | Owner-produced versioned artifacts; KENN adapters remain Python | Invalid/boundary/OOD, hashes, target proposal, real readback/undo | Cross-team dependency; 1–2 weeks each |
| P2 | Open-ended musical quality is unproven | planner/retrieval/memory plus evaluation JSON | Typed model plans and blinded rubric; Python/model layer | Published held-out per-stratum scores and failure registry | Reviewer/model availability; recurring evaluation |

## Reproduction commands

Run from `products/kenn` unless noted:

```bash
cd apps/backend
PYTHONPATH=src:../../tooling .venv/bin/python -m pytest -q src/kenn/tests

cd ../../chat
../apps/backend/.venv/bin/python -m pytest -q

cd ../packages/mix-review
../../apps/backend/.venv/bin/python -m pytest -q

cmake --build build/plugins/kenn-vst3-au --config Release
ctest --test-dir build/plugins/kenn-vst3-au -C Release --output-on-failure

apps/backend/.venv/bin/python tooling/scripts/qualify_ableton_live.py \
  --output docs/research/results/kenn_audit_ableton_real_qualification_2026-09-21.json

PATH=/Users/Ganders4/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH \
  npm --prefix apps/frontend test
PATH=/Users/Ganders4/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH \
  npm --prefix apps/frontend run build
```

Benchmark input hashes, repetitions, warmups, samples and implementation labels are in `docs/research/results/KENN_BENCHMARK_BEFORE_AFTER_2026-09-21.json` and its referenced receipts.

Exact benchmark reproductions from `products/kenn`:

```bash
KENN_DSP_NATIVE=0 KENN_DSP_MASKING_NATIVE=0 \
  apps/backend/.venv/bin/python tooling/scripts/benchmark_audio_analysis.py \
  --long-seconds 10 --workers 4 --repeats 10 --include-ltas \
  --json-out docs/research/results/kenn_audit_audio_reference_2026-09-21.json

KENN_DSP_NATIVE=1 KENN_DSP_MASKING_NATIVE=1 KENN_DSP_BUILD_TYPE=release \
  apps/backend/.venv/bin/python tooling/scripts/benchmark_audio_analysis.py \
  --long-seconds 10 --workers 4 --repeats 10 --include-ltas \
  --json-out docs/research/results/kenn_audit_audio_native_2026-09-21.json

KENN_DSP_NATIVE=0 KENN_DSP_MASKING_NATIVE=0 \
  apps/backend/.venv/bin/python tooling/scripts/benchmark_audio_analysis.py \
  --workers 4 --repeats 10 --include-ltas \
  --fixture '/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/testing-assets/testing_track_stems/al_james/42_BackingVox01.wav' \
  --json-out docs/research/results/kenn_audit_real_asset_reference_2026-09-21.json

KENN_DSP_NATIVE=1 KENN_DSP_MASKING_NATIVE=1 KENN_DSP_BUILD_TYPE=release \
  apps/backend/.venv/bin/python tooling/scripts/benchmark_audio_analysis.py \
  --workers 4 --repeats 10 --include-ltas \
  --fixture '/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/testing-assets/testing_track_stems/al_james/42_BackingVox01.wav' \
  --json-out docs/research/results/kenn_audit_real_asset_native_2026-09-21.json

apps/backend/.venv/bin/python tooling/scripts/benchmark_mix_review_native.py \
  --seconds 10 --sample-rate 48000 --repeats 10 \
  --json-out docs/research/results/kenn_audit_mix_review_native_2026-09-21.json

KENN_DSP_NATIVE=1 KENN_DSP_MASKING_NATIVE=1 \
  apps/backend/.venv/bin/python tooling/scripts/benchmark_native_kernels.py \
  --seconds 10 --sample-rate 48000 --repeats 20 \
  --json-out docs/research/results/kenn_audit_native_kernels_2026-09-21.json
```
