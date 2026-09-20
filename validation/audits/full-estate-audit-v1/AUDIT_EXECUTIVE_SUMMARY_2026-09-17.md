# AUDIT EXECUTIVE SUMMARY — NITE DSP Full Estate V1 — 2026-09-17

Owner: NITE DSP (Jack). Mode: read-only on product source. Output: `Nite-DSP-Operations/monorepo/validation/audits/full-estate-audit-v1/`. Zero product files modified (receipt §12 + AUDIT_RECEIPT JSON).

## Estate in one paragraph

OBSERVED: workspace root `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP` is **not a git repo**; it contains **13 independent git repos** (verified `git -C <d> remote -v`): `monorepo` (Nite-DSP/monorepo), `products/slo` (Nite-DSP/slo), `Audio_Too` (dual remote: origin Nite-DSP/slo + nitedsp_prod Jack441095/Nite_DSP_01), `platform` (Nite-DSP/monorepo), `kenn-evaluation`, `nite-submit`, `design-system`, `layer-alignment`, `thursday`, `platform-support`, `Shenrendao/KENN` (Jack441095/kenn-standalone), 2 client repos. INFERRED (HIGH): the estate is a **federated monorepo + satellite repos**, not a single repo — cross-repo duplication is the #1 structural risk.

## Product verdict table

| Product | Assessed stage | Verdict | Score/50 | One-line reason |
|---|---|---|---|---|
| SLO (products/slo) | Alpha (internal) | HARDEN | 30 | Engine real, WAV-only, beta blocked on signing/licensing; docs contradict readiness |
| KENN standalone (Shenrendao/KENN) | Alpha (internal) | SHIP AFTER FIXES (supervised pilot only) | 28 | Chat+KB+mix-review real; AutoMix disabled by design; mix-review tests failing 5/58; plugin never DAW-loaded |
| NITE Submit (products/nite-submit) | Release Candidate | SHIP AFTER FIXES (parity gate + sign/notarise) | 41 | Swift app+CLI+tests real, v1.0.0 RC declared; only network is update feed (declared) |
| NITE Files | Dead/Orphaned | ARCHIVE or CONSOLIDATE INTO Submit | 6 | No source in tree, only `.build` cache + 2 artifacts; no README |
| NITE Paraphrase | Research/Spike (scaffold) | CONTINUE RESEARCH (server-side) | 8 | `engine/evals/tests` all empty; real logic lives in `backend/app/paraphrase*.py` |
| DiskSweep | Prototype→Alpha | HARDEN | 27 | Scanner+sidecar+contracts real; **31/31 pytest pass (verified this audit)**; no DMG built; privileged-helper unreviewed |
| AudioGen (in Audio_Too) | Prototype | CONTINUE RESEARCH | 18 | Code present, no quality metric; Apple-Silicon-only gate |
| AutoMix / Mix Review | Prototype (mix-review) / Disabled (automix) | HARDEN mix-review; KEEP automix disabled | 20 | local_engine real but BS.1770/true-peak failing; automix returns failed without external renderer |
| Thursday (autonomous-systems/thursday) | Prototype | CONTINUE RESEARCH | 22 | 106 modules, 44 test files; extraction coupling documented; no commercial path |
| Platform backend (monorepo/backend) | Alpha | HARDEN | 29 | FastAPI+Paddle+Alembic real; ruff clean (verified); pytest blocked by missing NaCl in this env; commerce/licensing diverge from platform/ copy |
| Platform website (monorepo/website) | Alpha | HARDEN | 28 | Next 16.3/React 19 real; CI manual-only; diverges from platform/website (Next 16.3.5 + extra routes) |
| Audio_Too workspace | Alpha (internal tooling) | CONSOLIDATE (decide product vs private) | 24 | 145 test entries claimed ~1,330 tests; live DB gitignored; dual remote is a push-mistake risk |
| Client-Work | N/A (separate stream) | No verdict (hygiene only) | — | Branch-per-client; no secrets found in spot check |

## Top 10 risks (P0/P1 first)

1. P1 | Estate | Canonical-source ambiguity x4 (KENN, platform, SLO-archive, Thursday) — editing wrong checkout ships wrong product. Evidence: `diff -rq backend/app platform/backend/app` → 4 files differ; website diff → 15+ routes differ; Next 16.3.0 vs 16.3.5.
2. P1 | SLO | Beta-blocked but docs imply progress; `slo_beta_readiness_v1.json: external_private_beta_ready:false, decision E_BLOCKED_BY_EXTERNAL_CREDENTIAL_DISTRIBUTION_DEPENDENCY`.
3. P1 | KENN | Mix-review calibrated loudness/true-peak + 24/32-bit support **failing 5/58** (verified `.venv/bin/python -m pytest mix-review/tests` → `5 failed, 53 passed`); README itself says "not yet a qualified public Mix Review product" (`mix-review/README.md:29-32`).
4. P1 | KENN/SLO plugin | Neither plugin verified loaded in a real DAW (KENN `docs/beta/ABLETON_INTERNAL_BETA_0.1.md:25-27`; SLO `SLO_V1_WORKING_PRODUCT_DEFINITION.md` CANNOT-VERIFY drag-to-Ableton).
5. P1 | Commercial | No product can charge today: SLO licensing endpoint gap (B-001/B-003), Submit unsigned/unnotarised (`README.md:122-128`), DiskSweep no DMG, KENN no entitlement path.
6. P1 | Privacy (watch) | No contradiction found in Submit/DiskSweep/KENN-mix-review local paths (all network enumerated §4), but KENN `llm_rewrite.py:182` can reach `api.openai.com` with user key — must stay opt-in + disclosed.
7. P2 | CI | Product repos have NO CI here: `.github/workflows/` only `backend.yml`/`website.yml` (both manual `workflow_dispatch` only) + `mirror-to-personal.yml` force-push mirror. SLO/KENN/Submit/DiskSweep ungated.
8. P2 | Audio_Too | Dual remote (`origin` Nite-DSP/slo + `nitedsp_prod` personal) + `.git` nested inside monorepo — push-mirror mistake risk; `data/audio_too.db` untracked-but-critical (clean checkout behaves without DB — unverified).
9. P2 | NITE Files | Orphaned artifacts (`Files-0.1.0-macOS.{dmg,zip}`) with no source — cannot rebuild, cannot sign, cannot support.
10. P2 | Monorepo hygiene | Dirty worktrees in 6 repos (SLO 10 modified, monorepo 10, platform 10, KENN renames); committed `.wavs`, `.onnx` (SLO), `.DS_Store`s; `workspace/` 55M scratch + 46G monorepo + 57G testing-assets (disk/time cost).

P0: none confirmed (no tracked private key found; only `backend/staging_keys/licensing_signing_key.public` tracked — public key is safe).

## Top 10 opportunities (RICE in brackets)

1. Submit: sign + notarise + pass parity gate → first revenue-capable product [RICE 96].
2. SLO: WAV→AIFF/FLAC/MP3 discovery expansion (gated by research R-01) [48].
3. DiskSweep: rules-only mode + 5k-parity fuzz in CI → sellable safety story [60].
4. KENN: fix 5 mix-review failures → qualified supervised pilot for Ableton users [54].
5. Platform: unify backend/frontend canonical copy (delete or re-export platform/) [72].
6. Shared licensing client (SLO+Submit+DiskSweep+KENN) from `backend/app/licensing.py` [44].
7. Submit site-licence / university channel (batch CLI already exists) [58].
8. SLO find-similar as a service for KENN/Audio_Too (HNSW 512-D reuse) [30].
9. Telemetry-free diagnostics bundle (Submit manifest pattern → all products) [40].
10. Sunset/archive NITE Files + nite-submit-windows + paraphrase scaffold → cut confusion [80].

## The single most important decision this month

**Declare canonical checkouts (KENN = Shenrendao/KENN; platform = monorepo root; Thursday = autonomous-systems/thursday; SLO = products/slo/SmartSampleManager) and delete or re-export the duplicates** — every week of ambiguity risks fixing/shipping the wrong copy. See OWNER_DECISIONS_2026-09-17.md Q1.
