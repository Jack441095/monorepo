# ZERO-TRUST FULL BASELINE — 2026-09-17

> Method: source code + configs + git + live commands only. All `*.md` reports ignored as evidence. Format: `OBSERVED:` → `INFERRED (HIGH/MED/LOW)` → `UNVERIFIED:`.
> Workspace root: `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP` (not a git repo — OBSERVED via `find -maxdepth 5 -name .git`).
> Output dir: `Nite-DSP-Operations/monorepo/validation/audits/baseline-v2-2026-09-17/` (new, allowed).
> No product source modified. No secret values printed (paths only). No destructive commands run.

## 0. Method + receipts

Commands run (verbatim summary):
- `du -sh` top-level: monorepo 46G, testing-assets 57G, Shenrendao 2.0G, workspace 55M, Client-Work 35M
- `find ... -name .git`: 12 git boundaries (monorepo, Audio_Too, layer-alignment, platform-support, thursday, platform, kenn-evaluation, nite-submit, slo, KENN-standalone, 2x client repos)
- `git -C <repo> remote -v / log --oneline / status --short / ls-files` for monorepo, products/slo, nite-submit, KENN
- `rg TODO|FIXME`, `rg http|ollama|telemetry|paddle|webhook`, `pytest --collect-only` (backend → ImportError: No module named 'nacl')
- 4 parallel source-only subagents (SLO, KENN, small-products, platform/Audio_Too) with file:line citations

Skipped (explicit): full C++/Swift builds (`cmake --build`, `swift build`), full pytest runs, DAW load, notarisation check, large JSON/ONNX/WAV inspection. Reason: timebox + toolchain isolation; marked UNVERIFIED below.

## 1. Executive summary

Estate in one paragraph: one 46G monorepo checkout containing ~6 real product codebases (SLO JUCE/C++, KENN Python+JUCE, NITE Submit Swift, DiskSweep C++/Swift/Python, FastAPI backend, Next.js website) plus large internal tooling (Audio_Too, Thursday x2, research, archive), one 2G standalone KENN repo, one 57G testing-assets blob, and client-work stream. Git hygiene is the single biggest risk: monorepo tracks only 215 files with `products/`, `platform/`, `Audio_Too/`, `research/` etc UNTRACKED (`??` in status), while real history lives in nested repos (slo → Nite-DSP/slo, nite-submit → nite-submit-private, KENN → kenn-standalone).

Verdict table:

| Product | Stage | Verdict | Score/50 | One-line reason |
|---|---|---|---|---|
| SLO | Alpha | HARDEN | 28 | Real JUCE engine + 53 test mains, no CTest, unpinned ONNX/TagLib, no clean-build proof |
| KENN standalone | Alpha | HARDEN | 27 | 1920 .py + approval gate in code, loopback Ollama, but 700+ tests unrun, no DAW proof |
| NITE Submit | RC | SHIP AFTER FIXES | 38 | Real Swift pkg, 13 test files, Trash-safe, only Sparkle update as network |
| DiskSweep | Alpha | HARDEN | 30 | Trash-first + dry-run default verified in code, privileged-helper gated, Ollama loopback |
| NITE Files | Orphaned | SUNSET/ARCHIVE | 8 | No source, only .dmg/.zip + .build objects |
| NITE Paraphrase | Scaffold | CONTINUE RESEARCH | 10 | engine/evals/tests empty (0 files); backend paraphrase.py proxies missing server |
| NITE Submit Windows | Empty | SUNSET | 2 | 0 files |
| Platform backend | Alpha | HARDEN | 29 | Paddle HMAC verify present, sandbox-gated, but tests don't collect (missing nacl) |
| Platform website | Alpha | HARDEN | 30 | Next 16.3/React 19.2, 29 routes, production gate exists, e2e unrun |
| Audio_Too / Thursday | Internal tooling | CONSOLIDATE | 20 | 681 test files + Thursday x2 divergent (169 vs 288 files), Apple-only, unrun |

Top 10 risks (P0 first):
1. P0 — Monorepo canonical-source ambiguity: most product dirs untracked; editing monorepo checkout ≠ editing history. Evidence: `git ls-files | wc -l = 215`, `git status --short` shows `?? products/ platform/ Audio_Too/` etc.
2. P0 — Secrets sprawl (paths only): `.env` at Audio_Too/, Audio_Too/nitedsp/backend/, platform/backend/, `.env.local` x2, `staging_keys/` x3, `.vercel/.env.production.local`. Tracked: only `.env.example` + `licensing_signing_key.public` — INFERRED MED safe, but UNVERIFIED private keys untracked status per-repo.
3. P1 — SLO unpinned critical deps: `SmartSampleManager/CMakeLists.txt:129-134` TagLib + ONNX via brew `find_path` (fatal if missing :136-137); host taglib 2.3.1 / onnx 1.29.0_3 — works-on-my-machine risk.
4. P1 — No reproducible-build proof: SLO presets exist (`CMakePresets.json:17-60` ssm-dev/qualification/release-candidate/sanitize) but no build run in audit; KENN `Dockerfile:2 python:3.11-slim` unbuilt; Submit `swift build` unrun.
5. P1 — Test suites unexecuted: SLO 53 mains with custom `ssm_*` groups but `enable_testing/add_test/CTest` = 0 hits (`CMakeLists.txt`); KENN ~700 tests unrun; backend `pytest --collect-only` fails `ModuleNotFoundError: nacl` (`backend/tests/conftest.py:19`).
6. P1 — KENN monorepo copy is empty skeleton: `monorepo/products/kenn` = 7 files, 0 .py vs standalone 1920 .py — anyone editing monorepo copy edits nothing.
7. P1 — NITE Files orphaned artifact: `products/nite-files/artifacts/Files-0.1.0-macOS.{dmg 445K, zip 215K}`, 0 .swift, only `.build/*.o` — cannot rebuild, cannot patch.
8. P2 — Thursday divergence: `Audio_Too/thursday` 169 files vs `autonomous-systems/thursday` 288 files, `diff -rq` divergent — fix-wrong-checkout risk.
9. P2 — Platform divergence: `platform/` vs monorepo `backend/+website/` — `diff -rq` shows commerce.py/licensing.py/page.tsx differ; platform-only `fly.toml`, `.env`, `mock_storage/NITESubmit*.zip`, `licensing_signing_key.private` (path only).
10. P2 — CI manual-only: `.github/workflows/backend.yml + website.yml` are `on: workflow_dispatch` only; `mirror-to-personal.yml` is `push main` with `--force` to `Jack441095/monorepo` via token — no per-product gates for SLO/KENN/Submit/DiskSweep.

Top 10 opportunities: (1) SLO undo-sort + quarantine as cross-product safety lib; (2) DiskSweep Trash-first sidecar pattern for Submit/SLO; (3) KENN approval-gate receipt for AutoMix; (4) licensing_server (SLO) + backend licensing/commerce merge; (5) Submit Sparkle appcast as template for SLO/DiskSweep updates; (6) SLO PANNs embedding service for KENN mix-review; (7) shared THIRD_PARTY_NOTICES pipeline (only Submit/SLO/KENN have them); (8) single CI gate (lint+build+test+package smoke) per product; (9) paraphrase backend (172 lines) as fastest new revenue if engine built; (10) testing-assets manifest as sellable corpus (licence check first).

Single most important decision this month: declare canonical repo per product (slo→Nite-DSP/slo? nite-submit→private? KENN→kenn-standalone? platform→monorepo or platform sub-repo?) and either track or delete the duplicate skeletons — everything else multiplies risk until this is fixed.

## 2. Estate map + canonical sources

Repo boundaries (OBSERVED `git remote -v`):
- `monorepo/` → `github.com/Nite-DSP/monorepo` (tracks 215 files only; log `55c1e5a fix website em-dash`)
- `monorepo/products/slo` → `github.com/Nite-DSP/slo` (log `dc855be test: reproduce reversed audition tempo`; dirty: CMakeLists, PluginProcessor, SampleManagerEngine, taxonomy docs)
- `monorepo/products/nite-submit` → `nite-submit-private https://github.com/Nite-DSP/nite-submit` (log `1e086a6 simplify Submit three-step workflow`)
- `Shenrendao/KENN` → `github.com/Jack441095/kenn-standalone` (log `3c82fe9 301 notes total`; dirty: CHANGELOG, UX/index.html, docs/ reorganised)
- `monorepo/Audio_Too`, `platform`, `autonomous-systems/thursday`, `platform-support`, `layer-alignment`, `kenn-evaluation`, `shared/design-system` — nested `.git` present, remotes not enumerated (UNVERIFIED)
- `Client-Work/client-websites`, `crystal-carpentry-salisbury` — separate client repos (out of scope)

Canonical-source table:
| Product | Canonical (inferred) | Duplicate/skeleton | Blast radius |
|---|---|---|---|
| SLO | products/slo (Nite-DSP/slo) | products-archive/slo (frozen lineage, UNVERIFIED diff) | Fix archive = dead fix |
| KENN | Shenrendao/KENN (1920 .py) | monorepo/products/kenn (0 .py, 7 cache files) | Edit monorepo copy = no-op |
| Platform | UNVERIFIED (platform/ vs monorepo backend+website diverge) | Audio_Too/nitedsp/, products/slo/nitedsp/, archive slo-ux-v3/nitedsp/ | Deploy wrong copy = stale Paddle/entitlement |
| Thursday | UNVERIFIED | Audio_Too/thursday (169) vs autonomous-systems/thursday (288) | Fix wrong side = lost fix |
| Submit | products/nite-submit (private repo) | nite-submit-windows/ (0 files) | — |
| NITE Files | NONE (orphaned) | artifacts only | Cannot patch |

Hygiene: `.gitignore` correctly ignores `.env`, `*.onnx`, `*.wav`, `*.zip`, `build/`, `dist/` — OBSERVED `monorepo/.gitignore`. Tracked binaries: `git ls-files | grep dmg|zip|onnx|wav|db|tgz` = 0 hits in monorepo (Models/*.onnx untracked or nested-repo). Tracked secrets: only `backend/.env.example`, `backend/staging_keys/licensing_signing_key.public` (public key, safe). Du listing proves bulk is data: testing-assets 57G must never enter git.

## 3. Per-product reviews

### 3.1 SLO — Sample Library Optimiser
- OBSERVED: real root `SmartSampleManager/` (no `products/slo/Source/`). `Source/` 113 entries: `PluginProcessor.cpp/.h`, `SampleManagerEngine.cpp/.h`, `AbletonTaxonomy.cpp/.h`, `AbletonXmpWriter.cpp`, `Licensing/LicenseManager.cpp/.h`, `SortFileSafety.h`, `TestCacheDbIsolation.h`. `CMakeLists.txt:1` cmake 3.22, `:88` JUCE 8.0.2 FetchContent, `:99` umappp 3.3.2, `:113` dr_libs 0.14.5, `:123` hnswlib 0.8.0, `:129-134` TagLib+ONNX brew-unpinned, `:202` libsodium, `:476-493` `juce_add_plugin FORMATS VST3 AU Standalone PRODUCT_NAME SLO`, `:523-532` model bundle copy. Presets `:17-60` dev/qualification/release-candidate/sanitize. `Models/`: `panns_cnn10_embedding.onnx` 82K + `.data` 23M.
- Build: UNVERIFIED (no build run). INFERRED MED: presets sane, but brew deps = fragile.
- Tests: OBSERVED 53 `Test*/test_*` mains, custom `SSM_TEST_TARGETS` ~35 (`:1180-1194`), groups `ssm_qual_*` (`:1233-1264`); `enable_testing|add_test|CTest` = 0. TODO/FIXME in Source = 0. INFERRED: real suite, non-standard harness, unrun → coverage UNKNOWN.
- Safety: OBSERVED `SortFileSafety.h:45` bans move/copy deletes; prod moves only cache quarantine `SampleManagerEngine.cpp:1234-1303`, legacy migration `:649-661`, XMP backup `AbletonXmpWriter.cpp:107`; `getCacheDbFile()` → `sample_cache.sqlite3` `:545-565`; `UndoSortResult/journalPath/undoLastSort` `SampleManagerEngine.h:763-799`, UI `PluginEditor.h:73,244`; test isolation `TestCacheDbIsolation.h:21-42`, `SSM_TEST_BINARY` fail-closed `:516,524`. INFERRED HIGH: Trash-safe-by-design, undo present.
- Privacy: OBSERVED no curl/telemetry/analytics in Source; `http` only XMP namespaces + LicenseManager `juce::URL` HTTPS-except-localhost default `http://localhost:8420` (`LicenseManager.h:58-79`, `.cpp:9-131`); ONNX local `#include <onnxruntime_cxx_api.h>` (`SampleManagerEngine.cpp:9`). INFERRED HIGH: local-only holds for engine.
- Commercial: `Licensing/LicenseManager` + `licensing_server/` + `THIRD_PARTY_NOTICES.txt` exist; entitlement vs backend integration UNVERIFIED.
- Claim grades: VST3/AU/Standalone target B (code complete, no binary proof); quarantine+undo B; local-only B; classification accuracy F (no run).

### 3.2 KENN (standalone canonical)
- OBSERVED: `source/kenn/*.py` (server, orchestrator, autonomous_agent, mixing_doctor, telemetry, routes/fastapi_app), `core/` 100+ files (confirmation, action_policy, path_safety, receipt_contract, ollama_deliberative), `llm/` (kenn_lm, mlx_inference, llm_rewrite, paraphrase_engine), `chat/app.py`, `mix-review/core/local_engine.py`, `automix/adapter.py`, `vst3-plugin/CMakeLists.txt` + PluginProcessor/Editor + 8 test mains. `requirements.txt:1-21` fastapi/httpx/numpy/onnx/librosa/sklearn/pyloudnorm/pytest (torch banned); `Dockerfile:2 python:3.11-slim`, EXPOSE 8090. 777 test_*.py (incl. chat/mix-review/automix suites). `pytest.ini` norecursedirs third_party/AbletonOSC.
- Safety: OBSERVED `automix/adapter.py:92,128,159` `awaiting_human_approval`, test `test_requires_approval_without_calling_engine:26`; `mix-review/evaluation/listening_protocol.py:12,52-53` blocks without approval_reference; `core/confirmation.py` exists but not wired to adapters (grep). `dry_run` = 0 hits. INFERRED MED: approval pattern real but partial.
- Privacy: OBSERVED `llm_rewrite.py:25 httpx`, `:182` base `http://127.0.0.1:11434/v1` ollama else `https://api.openai.com/v1`, provider env `AUDIO_TOO_LLM_PROVIDER` default openai `:170`; `ollama_deliberative.py:26-66` loopback-only enforced; `telemetry.py:22-85` local jsonl `beta_telemetry.jsonl`; `chat/app.py` zero network hits. INFERRED MED: local-default with OpenAI fallback if env set — P1 if shipped as "local-only" without pinning provider=ollama.
- Monorepo copy: OBSERVED 0 .py, 7 cache files — E (contradicted as copy).
- Claim grades: chat/BM25 B (code present, unrun); mix-review engine B; automix C (adapter+gate, render engine external per code comments — UNVERIFIED); DAW load F.

### 3.3 NITE Submit — Swift macOS
- OBSERVED: `Package.swift:1-12` swift-tools 5.9, targets NiteSubmitCore/cli/App/tests; `Sources/nitesubmit-cli/main.swift:1-5` commands suggest/copy/rename/pack/optimize/batch/organize/validate/review; 13 `*test*.swift` incl. Archive/Corpus/Detector/UpdateEngine; `ArchiveEngine.swift:105` zero-network archives; `Settings.swift:147` no-network entitlement hook; only network `NiteSubmitApp/main.swift:114 URLSession` + `UpdateEngine.swift:69 defaultAppcastURL https://www.nitedsp.co.uk/submit/appcast.xml` + test fixture releases.nitedsp.com. Nested repo `nite-submit-private`, log `1e086a6`.
- INFERRED HIGH: local-only promise holds except user-initiated Sparkle update — document it. Verdict SHIP AFTER FIXES (needs `swift build/test` proof + notarisation/parity gate run).

### 3.4 DiskSweep
- OBSERVED: `CMakeLists.txt:9-16` scanner/policycheck/parity/helper; `scanner/main.cpp`, `privileged-helper/helper.cpp:1,20,51` moves ONLY to Trash + `DstInsideTrash` + `IsBlocked`; `sidecar/cli.py:8,60,75-77,204` never-deletes-unless-trash, `~/.Trash/Disksweep`, dry-run-only; `ui/ScanStore.swift:19,101` dry-run + undo restores; `contracts/*.schema.json`; `SHIPLIST`; `sidecar/ollama_client.py:7,11` `OLLAMA_URL http://127.0.0.1:11434`, classifier falls back rules-only `:150`. Only hard-delete `cli.py:71` prunes old Trash/Disksweep runs.
- INFERRED HIGH: Trash-only + dry-run default verified by code. UNVERIFIED: helper privilege escalation review, rules-vs-LLM accuracy.

### 3.5 NITE Files / Paraphrase / Submit-Windows
- Files: OBSERVED `artifacts/Files-0.1.0-macOS.dmg 445K + .zip 215K`, 0 .swift, only `.build/*.o` (FileOperations, FolderScanner, OrganizationRulesEngine) — INFERRED HIGH orphaned, cannot rebuild → SUNSET/ARCHIVE.
- Paraphrase: OBSERVED `engine/ evals/ tests/` 0 files; `backend/app/paraphrase.py` 172 lines proxies SSE from missing `engine/server.py`, free-tier limiter `:10-13` — Grade D (claimed only) → RESEARCH.
- Windows: OBSERVED 0 files — SUNSET.

### 3.6 Platform backend (FastAPI)
- OBSERVED: `backend/app/` 19 modules; `requirements` fastapi==0.141.1, uvicorn 0.52.1, SQLAlchemy 2.0.52, alembic 1.19.1, pydantic 2.13.4, PyNaCl 1.6.2; alembic 7 versions; `commerce.py:11-13,99-130` HMAC-SHA256 `{ts}:{raw}` + `compare_digest`, max age 5d `:97`, fail-closed on no-secret/malformed/replay; `config.py:77` sandbox default, `:97` checkout disabled, `:212-246` production guards. Tests do not collect: `conftest.py:19 from nacl.signing` → `ModuleNotFoundError: nacl` on system python. TODO in app = 0 hits (rg). INFERRED MED: webhook correct by code, deploy safety gated, but backend unrun.

### 3.7 Platform website (Next.js)
- OBSERVED: `package.json` next 16.3.0, react 19.2.8, TS ^5, paddle-js ^1.6.4; 29 `page.tsx`; `scripts/check-production-config.mjs` exists, wired `build:production`. INFERRED: stack modern; build/e2e UNVERIFIED (unrun).

### 3.8 Audio_Too / Thursday / autonomous-systems / shared
- OBSERVED: `Audio_Too/main.py:1-989`, commands start/status/kenn-ready/setup/fetch-models/agent/ableton/audiogen/demo/smoke/check/full-test/automix-local/package/verify/eval/bench/audit; `pyproject` ruff line-length 100 py312, pytest testpaths tests+scripts/setup; 681 test_*.py; requirements loose + hashed lock. Thursday: 169 vs 288 files, divergent. Workflows: backend.yml + website.yml `workflow_dispatch` only (pytest/compileall; npm ci/lint/build/e2e); mirror `--force` to personal. INFERRED: internal tooling, not shippable as-is → CONSOLIDATE.

## 4. Cross-cutting findings

| ID | Sev | Product | Title | OBSERVED | INFERRED | Impact | Fix | Effort |
|---|---|---|---|---|---|---|---|---|
| F-01 | P0 | estate | Most work untracked in monorepo | `ls-files=215`, `status` shows `?? products/ platform/ Audio_Too/ research/ validation/` | HIGH canonical ambiguity | Wrong-checkout fixes, lost history | Declare canonical per product; track or delete skeletons | M |
| F-02 | P0 | estate | Env/keys sprawl | `.env` x3, `.env.local` x2, `staging_keys/` x3, `.vercel/.env.production.local` (paths only) | MED hygiene ok (only .example+public tracked) | Leak risk | Single secrets doc + gitignore audit + rotate if ever tracked | S |
| F-03 | P1 | slo | Unpinned brew deps | `CMakeLists.txt:129-134` TagLib/ONNX find_path | HIGH fragile build | CI/red-machine failure | Pin versions or vendor + hash | M |
| F-04 | P1 | estate | No build proof | No cmake/swift/docker build run in audit | HIGH | Ship claims unverified | Run preset builds + record receipts | M |
| F-05 | P1 | estate | Tests unrun/broken harness | SLO no CTest; KENN 700+ unrun; backend collect fails `nacl` | HIGH | Silent regression | Fix backend venv, wire ctest, run + gate | M |
| F-06 | P1 | kenn | Monorepo copy empty | 0 .py vs 1920 .py | HIGH | Confusion | Delete or submodule to standalone | S |
| F-07 | P1 | nite-files | Orphaned artifact | 445K dmg + 215K zip, 0 source | HIGH | Unpatchable | Archive + remove from sale surface | S |
| F-08 | P2 | thursday | Divergent copies | 169 vs 288 files | HIGH | Lost fixes | Pick canonical, delete other | S |
| F-09 | P2 | platform | Backend/website diverge | commerce/licensing/page.tsx differ; platform-only fly.toml/.env/private key path | MED | Deploy stale | Canonical + diff register | M |
| F-10 | P2 | estate | CI manual only | backend/website `workflow_dispatch`; no SLO/KENN/Submit/DiskSweep gates; mirror `--force` | HIGH | No regression net | Add per-product lint+build+test+smoke; protect main; non-force mirror | M |
| F-11 | P2 | kenn/disksweep | Cloud fallback in local products | KENN default provider openai (`llm_rewrite.py:170,182`); DiskSweep Ollama loopback w/ rules fallback | MED | Privacy contradiction if shipped as local-only | Pin provider=ollama + fail-closed; document | S |
| F-12 | P3 | estate | Licence gaps | NOTICES exist only Submit/SLO/KENN-third_party; PANNs/CLAP/model/sample-pack licences unverified; 57G testing-assets licence unknown | MED | Distro block | Per-component licence table + asset licence pass | M |

Version matrix (OBSERVED): CMake ≥3.22; JUCE 8.0.2; umappp 3.3.2; dr_libs 0.14.5; hnswlib 0.8.0; TagLib brew-unpinned (host 2.3.1); ONNX brew-unpinned (host 1.29.0_3); Swift-tools 5.9; Python Dockerfile 3.11 vs Audio_Too py312 vs CI python 3.13; Next 16.3 / React 19.2 / TS 5 / Node 22 (CI) / paddle-js 1.6.4; FastAPI 0.141.1 / Pydantic 2.13.4 / SQLAlchemy 2.0.52 / Alembic 1.19.1. Drift flagged: Python 3.11 vs 3.12 vs 3.13; platform vs monorepo backend pins (UNVERIFIED full diff).

## 5. Quality matrix (D1-D10, 0-5; truth scored low because no prior docs trusted + no runs)

| D | SLO | KENN | Submit | DiskSweep | Files | Paraphrase | Backend | Website | Audio_Too |
|---|---|---|---|---|---|---|---|---|---|
| D1 truth | 2 | 2 | 3 | 3 | 1 | 1 | 2 | 2 | 2 |
| D2 tests | 3 | 3 | 4 | 3 | 0 | 0 | 2 | 2 | 2 |
| D3 safety/privacy | 4 | 3 | 5 | 4 | 1 | 1 | 3 | 3 | 2 |
| D4 supply chain | 2 | 3 | 3 | 3 | 0 | 1 | 3 | 3 | 2 |
| D5 build/release | 2 | 2 | 3 | 3 | 0 | 0 | 2 | 3 | 2 |
| D6 perf/RT | 2 | 2 | 4 | 3 | 0 | 0 | 3 | 3 | 1 |
| D7 UX/docs | 3 | 2 | 4 | 3 | 1 | 1 | 3 | 4 | 2 |
| D8 commercial | 2 | 2 | 2 | 2 | 0 | 2 | 3 | 3 | 0 |
| D9 maintainability | 3 | 3 | 4 | 3 | 0 | 0 | 3 | 3 | 2 |
| D10 strategic | 5 | 5 | 4 | 4 | 1 | 3 | 4 | 4 | 3 |
| **Total/50** | **28** | **27** | **38** | **30** | **8** | **10** | **29** | **30** | **20** |

Bands: 0-14 not product · 15-24 prototype · 25-34 alpha · 35-42 beta-ready · 43-47 RC · 48+ shipped.

## 6. Roadmap (RICE lite; Effort = person-weeks)

Now (0-30d): (1) Canonical-repo decision + delete/track skeletons [R10/F-01,F-06,F-08,F-09]; (2) Secrets audit + rotate if needed [F-02]; (3) Backend venv fix (`nacl`) + `pytest -q` receipt [F-05]; (4) SLO pin ONNX/TagLib + `cmake --preset ssm-qualification` receipt [F-03,F-04]; (5) Archive NITE Files artifact from sale surface [F-07]; (6) Pin KENN/DiskSweep to loopback-Ollama fail-closed [F-11].
Next (31-90d): wire CTest + run SLO/KENN/Submit suites; per-product CI (lint+build+test+smoke); licence table + testing-assets rights pass; Submit `swift build/test` + notarisation + parity gate; platform canonical deploy + webhook live-fire in sandbox.
Later (91-180d): paraphrase engine build-or-kill; Windows port decision (currently 0 files — explicit no); Thursday consolidation; shared safety/licensing/update components.

## 7. Owner-decision register
1. Canonical repo per product — options keep nested vs consolidate to monorepo — consequence fixes land wrong otherwise — recommend nested-repos-as-truth + monorepo thin pointers — deadline 7d.
2. Sell individually/bundled/subscription? — blocks licensing merge — 14d.
3. Fund Windows port? — currently empty — recommend macOS-only until revenue — 30d.
4. Keep generative/Thursday alive or freeze? — cost sink — 30d.
5. Release gate (parity + notarisation + real-file validation) — 14d.
6. Is Audio_Too product or private tooling? — recommend private — 14d.
7. Brand promise "local-first privacy-first"? — KENN OpenAI fallback + Submit Sparkle must be disclosed — 7d.

## 8. Appendices
A. Commands: see §0. B. Files inspected: ~200+ source/config via subagents + ~40 git/rg commands; explicitly NOT read: any `*.md` for conclusions, `*.onnx/.wav/.dmg/.zip`, >100k-line JSONs. C. Claim-grade index: §3 per product (A=ran, B=code-complete, C=partial, D=claimed-only, E=contradicted, F=unknown). D. Glossary: canonical = built/deployed checkout; readiness bands §5. E. Limitations: no builds/tests run beyond collect-only; no DAW/network live-fire; nested-repo remotes partially enumerated; licences/models unopened.

*End — new baseline from code only. Next step is build+test receipts to lift B-grades to A.*
