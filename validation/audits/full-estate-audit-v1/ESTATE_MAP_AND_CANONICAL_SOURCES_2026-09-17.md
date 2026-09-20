# ESTATE MAP & CANONICAL SOURCES — 2026-09-17

## 1. Top-level layout (verified `ls` + `du -sh`)

| Path | Size | Kind | Verified |
|---|---|---|---|
| `Admin/` | 32K | Business ops docs | inventory only |
| `Client-Work/` | 35M | client-websites + crystal-carpentry (own git repos) | separate stream |
| `Nite-DSP-Operations/monorepo/` | 46G | main monorepo (git: Nite-DSP/monorepo) | product estate |
| `Nite-DSP-Operations/Shenrendao/KENN/` | 2.0G | standalone KENN (git: Jack441095/kenn-standalone) | canonical KENN |
| `Nite-DSP-Operations/products-archive/` | 56K | frozen SLO lineage | confirm nothing live references it (UNVERIFIED — grep pending) |
| `Nite-DSP-Operations/testing-assets/` | 57G | stems/packs/benchmark JSONs | licence check needed (P2) |
| `workspace/` | 55M | scratch: SLO scan JSONs, logs | NOT source |
| `fixtures/`, `.github/`, `.venv/` | small | support + audit venv | root fixtures vs monorepo/fixtures duplication UNVERIFIED |
| Workspace root | — | **not a git repo** | confirmed (`git rev-parse` fails / no .git) |

## 2. Repo boundaries (all re-confirmed `git -C <d> remote -v`, 2026-09-17)

| Repo root | Remote | Last commit (verified) |
|---|---|---|
| monorepo | Nite-DSP/monorepo | 55c1e5a 2026-09-17 |
| monorepo/products/slo (nested) | Nite-DSP/slo | dc855be 2026-09-17 |
| monorepo/products/kenn-evaluation | Nite-DSP/kenn-evaluation | 7f76f62 |
| monorepo/products/nite-submit | Nite-DSP/nite-submit (remote name nite-submit-private) | 1e086a6 2026-09-14 |
| monorepo/Audio_Too (nested) | origin Nite-DSP/slo + nitedsp_prod Jack441095/Nite_DSP_01 | 31e9388 2026-09-16 |
| monorepo/platform (nested) | Nite-DSP/monorepo | 8d4a6a5 2026-09-16 |
| monorepo/shared/design-system | Nite-DSP/design-system | 83d3966 |
| monorepo/audio-technology/layer-alignment | Nite-DSP/layer-alignment | 6e7b9f3 |
| monorepo/autonomous-systems/thursday | Nite-DSP/thursday | c88b3d7 |
| monorepo/autonomous-systems/platform-support | Nite-DSP/platform-support | 5287273 |
| Shenrendao/KENN | Jack441095/kenn-standalone | 3c82fe9 2026-09-16 |
| Client-Work/client-websites | Nite-DSP/client-websites | bc78dc1 |
| Client-Work/.../crystal-carpentry-salisbury | Nite-DSP/client-websites | d186980 |

Seed-table corrections: `Audio_Too` and `platform` ARE nested repos (confirmed). `products/slo/SmartSampleManager` is a dir inside the nested `products/slo` repo, not itself a repo root. No `.git` found for `products/nite-files`, `nite-paraphrase`, `disksweep` (dirs inside monorepo).

## 3. Canonical-source table

| Product | Canonical (recommended) | Duplicate(s) | Divergence (observed) | Blast radius |
|---|---|---|---|---|
| KENN | Shenrendao/KENN (full: source/, vst3, docs, 391 notes) | monorepo/products/kenn (only automix/chat/mix-review runtime+tests) | monorepo slice has no source/vst3/docs/requirements; not buildable alone | HIGH — fixing monorepo copy fixes nothing shippable |
| Platform backend | monorepo/backend | monorepo/platform/backend, Audio_Too/nitedsp (unverified), products/slo/nitedsp (unverified) | `diff -rq` monorepo vs platform: commerce.py, licensing.py, rate_limit.py, schemas.py differ | HIGH — deploy may follow stale copy |
| Platform website | monorepo/website (Next 16.3.0) | monorepo/platform/website (Next 16.3.5, extra about/api/learn-guides routes, 15+ page diffs) | version + route divergence | HIGH — which one is deployed is UNVERIFIED |
| SLO | products/slo/SmartSampleManager | products-archive/slo (frozen), archive/legacy-layout/slo-ux-v3 | archive contains old backend+docs; live code in nested repo | MEDIUM |
| Thursday | autonomous-systems/thursday (standalone, pyproject thursday@0.1.0) | Audio_Too/thursday (coupled, 819+ behavior tests in Audio_Too/tests/thursday) | standalone stdlib-only + `_compat.py`; Audio_Too copy has LLM/bridges | MEDIUM — extraction in progress per README |
| Fixtures | UNVERIFIED | root fixtures/ vs monorepo/fixtures/ | both small; content diff not run | LOW |

## 4. Hygiene findings

- Dirty trees: monorepo (10 M), platform (10 M), products/slo (10 M), nite-submit (D+M), KENN (M+R renames into docs/beta/), layer-alignment (M+untracked), platform-support (M+untracked). Nothing committed by this audit.
- Tracked binaries: SLO tracks `Models/panns_cnn10_embedding.onnx` (+24MB .data untracked or LFS — UNVERIFIED) + several `.wav` fixtures; monorepo root tracks no .dmg/.zip (artifacts live in product dirs, untracked or nested-repo-tracked — mixed).
- Tracked secrets: only `backend/staging_keys/licensing_signing_key.public` (public key — safe). KENN `.env` exists on disk but NOT tracked (`git ls-files` no hit) — good. Values never printed (R6).
- Oversized: `testing-assets/` 57G, monorepo 46G (includes build dirs `build_arm64*/build-test/`, `.venv`s, node_modules — full breakdown UNVERIFIED, spot-checked).
- CI: `backend.yml` + `website.yml` are `workflow_dispatch`-only (manual); `mirror-to-personal.yml` force-pushes `main` → `Jack441095/monorepo` on every push (sync direction outward; token-gated; review recommended).
