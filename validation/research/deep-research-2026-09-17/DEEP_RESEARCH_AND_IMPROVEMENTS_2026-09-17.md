# DEEP RESEARCH + IMPROVEMENTS — 2026-09-17

> Inputs are LEADS, re-verified from source. A = `validation/audits/baseline-v2-2026-09-17/FULL_BASELINE_2026-09-17.md` (code-only). B = `validation/audits/full-estate-audit-v1/` (18 files). Every premise below traces to A/B section + own file:line/command check. Read-only on product source; output only here. No secrets printed.

## 0. Method + conflict table + commands run

Commands run this session: `ls` KENN mix-review/tests (7 test files confirmed), `ls` SLO classification_benchmark (ablation_suite.py, acoustic_evidence.py, centroids/weights v5+v6 headers confirmed), `rg` commerce.py HMAC (lines 100-130 confirmed), `sed` llm_rewrite.py:165-200 (default provider `openai`, fallback base openai-vs-ollama confirmed), `wc -l backend/app/paraphrase.py` (172 lines confirmed).

| Topic | A says (§) | B says (file) | Source check | Winner + conf |
|---|---|---|---|---|
| Readiness scores | SLO 28 KENN 27 Submit 38 DS 30 BE 29 (§5) | SLO 30 KENN 28 Submit 41 DS 27 BE 29 (READINESS_MATRIX) | Score methods differ (A zero-trust, B ran tests); delta ≤3 | AGREE (HIGH) — use B where it ran tests, A where B relied on docs |
| KENN mix-review tests | ~700 tests unrun, approval partial (§3.2) | 5/58 failing: 24/32-bit + BS.1770 + true-peak (FINDINGS F-03) | 7 test files exist (ls) | B WINS on detail (HIGH) — carry R-03 + fix list |
| SLO benchmark | Custom harness, no CTest, unrun (§3.1) | Strict-blind gate `_artifacts/slo_strict_blind_class_gate_v2/` 72 wavs + R-01 ≥70% top-1 (RESEARCH_AGENDA) | benchmark/ tools exist (ls) | B WINS on method (MED) — adopt R-01, verify gate path exists before running |
| Paddle webhook | HMAC correct by code, sandbox-gated, unrun (§3.6) | HMAC + replay window, needs idempotency deep review F-18 + R-07 | commerce.py:100-130 HMAC + compare_digest confirmed | AGREE (HIGH) — research = idempotency + live-fire, not signature |
| LLM default | Default openai unless ollama (`llm_rewrite.py:170,182`), P1-if-local-only (§4 F-11) | Same code cite, P3 trust + pin ollama (F-15) | sed confirms default `openai` / model `gpt-4o-mini` | AGREE on fact (HIGH); severity MED — research pins default + disclosure |
| Paraphrase | engine/ 0 files, backend 172-line proxy (§3.5) | Same: scaffold empty, logic server-side F-08 | paraphrase.py 172 lines confirmed | AGREE (HIGH) — build-or-kill stands |
| Files/Windows | Orphaned / empty (§3.5) | Same F-07 (448K dmg) | Prior evidence | AGREE (HIGH) — archive, no research |
| Canonical chaos | 215 tracked files, skeletons untracked (F-01) | diff backend/platform, kenn no-source, dual remotes (F-01,F-09,F-10) | Prior git evidence | AGREE (HIGH) — Tier 1 consolidation first |
| CI | workflow_dispatch only, no product gates (F-10) | Same F-06 | Prior evidence | AGREE (HIGH) |
| Licences | NOTICES only Submit/SLO/KENN; models/assets unverified (F-12) | JUCE pre-distribution F-17 + 57G assets F-12 + R-track 10 | THIRD_PARTY paths known | AGREE (HIGH) — research = clearance table |
| Submit ship path | Parity+sign+notarise (verdict) | Same + appcast signing F-16, site-licence FT2-03 | Prior evidence | AGREE (HIGH) |
| DiskSweep | Trash-first verified, accuracy UNVERIFIED | 31/31 pass claimed + R-05 ≥99% BLOCKED precision | helper/cli cites agree | B WINS on test count (MED) — re-run before trusting |

Killed premises: none fully killed; B's test-count claims (KENN 5 failures, DS 31/31) are adopted as hypotheses to reproduce, not facts, until re-run in Phase 2.

## 1. Executive summary

Top 5 research bets: (1) R-01 SLO strict-blind classification gate — decides flagship beta; (2) R-03 KENN mix-review validity + 5-test fix — decides pilot claim; (3) R-07 Paddle idempotency + sandbox live-fire — unblocks ALL revenue; (4) R-05 DiskSweep BLOCKED precision + Trash fuzz — unblocks 2nd revenue; (5) R-09 Windows spike (5d cap) — kills or prices the port question permanently.
Top 5 improvements: (1) I-T1-01 canonical-repo consolidation; (2) I-T1-03 backend venv + SLO CTest wiring (testability); (3) I-T1-05 loopback fail-closed + disclosure; (4) I-T1-06 archive Files/Paraphrase-scaffold/Windows; (5) I-T2-01 Submit sign+notarise+parity (first revenue).
The one decision: declare canonical repo per product within 7 days — every research result rots if fixes land in the wrong checkout.

## 2. Research tasks

```
R-01 · SLO strict-blind classification gate · SLO · 10d · corpus real-authorised packs + `_artifacts/slo_strict_blind_class_gate_v2/` (72 wavs per B; verify path first) + tools/classification_benchmark/{ablation_suite.py,acoustic_evidence.py}
Q/H: top-1 ≥70% on 16-class taxonomy with UNKNOWN ≤15% at frozen OOD threshold; PANNs-CNN10 vs CLAP AB.
Why now: unblocks SLO beta (B F-02, A F-04/F-05).
Method: freeze engine; run benchmark; confusion + OOD curves; fusion-weight sweep; record threshold to BetaDecisionPolicy.
Success: winner + threshold shipped. Fail: neither hits 70% → hold beta, rescope taxonomy.
Deliverable: report + confusion.csv + repro command. Unlocks: ship/hold beta + FT2-01.
```

```
R-02 · SLO format expansion cost · SLO · 5d · TagLib/dr_libs decode path
Q/H: AIFF/FLAC/MP3 scan throughput within 20% of WAV, zero journal regressions.
Why now: gates FT2-01 multi-format flag.
Method: same corpus transcoded; throughput + journal-diff; quarantine/undo fuzz.
Success: flag on. Fail: >20% slowdown or any journal regression → stay WAV-only. Unlocks: FT2-01.
```

```
R-03 · KENN mix-review validity + 5-test fix · KENN · 10d · mix-review/tests/ (7 files confirmed) + human listening ref
Q/H: fault agreement κ≥0.6; LUFS ±1 vs BS.1770 ref after fixing 24/32-bit + true-peak failures (B F-03).
Why now: pilot claim currently unqualified.
Method: fix numpy decode fast path + calibrated loudness; full suite re-run; blind human protocol for clip/headroom/silence/imbalance/phase/DC.
Success: qualified-pilot label. Fail: κ<0.4 → keep "not qualified". Unlocks: FT2-02.
```

```
R-04 · Plugin host compatibility · SLO+KENN · 7d · pluginval + Ableton/Logic/Reaper smoke, VST3/AU parity, ThreadSanitizer
Q/H: 0 crashes, RT-thread clean (no alloc/lock on audio thread).
Why now: both plugins never loaded in DAW (A §3, B F-04).
Method: existing test mains + pluginval; capture RT audit log.
Success: SHIP for plugins. Fail: any crash/RT violation → HARDEN list. Unlocks: KENN VST3 beta (FT3-03).
```

```
R-05 · DiskSweep accuracy + Trash guarantee · DiskSweep · 7d · labelled corpus (build if absent) + scanner/sidecar/privileged-helper/helper.cpp:1,20,51 + cli.py:8,204
Q/H: BLOCKED precision ≥99%; Trash-only fuzz 5000/5000 pass; rules-vs-Ollama latency/cost table.
Why now: 2nd revenue candidate, safety-critical.
Method: labelled SAFE/REVIEW/BLOCKED run; fault-injection on BLOCKED paths; Ollama reachable vs rules-only AB.
Success: beta + pricing. Fail: precision <99% or any non-Trash write → hold. Unlocks: FT2-04.
```

```
R-06 · Submit generalisation + update integrity · Submit · 7d · private authorised corpora per university profile + Sources/NiteSubmitCore/UpdateEngine.swift:69 + main.swift:114
Q/H: ≥98% correct renames, zero overwrites; tampered appcast rejected; cert pin holds.
Why now: site-licence pricing (FT2-03) + supply-chain (B F-16).
Method: per-profile acceptance sweep; feed-tamper tests; parity gate + notarisation rehearsal.
Success: site-licence pack. Fail: overwrite >0 or feed-accept on tamper → hold. Unlocks: first + institutional revenue.
```

```
R-07 · Paddle/entitlement live-fire · Platform · 5d · backend/app/commerce.py:100-130 (HMAC confirmed) + config.py sandbox default
Q/H: duplicate-webhook safe (idempotent), offline grace defined, refund/fraud paths covered.
Why now: unblocks charging everywhere.
Method: sandbox duplicate/replay/out-of-order webhooks; offline-verify matrix; idempotency-key tests.
Success: charge-ready receipt. Fail: double-fulfil or replay-accept → hold. Unlocks: all paid launches.
```

```
R-08 · AudioGen/AutoMix metric or freeze · Audio_Too/KENN · 10d
Q/H: objective metric with inter-rater ≥0.6 + cost/render + provenance gate; else freeze sales, keep research.
Why now: no metric = no shippable claim (B R-08).
Method: define metric + human protocol; measure cost/latency; copyright/provenance review.
Success: continue. Fail: no metric → freeze generative sales. Unlocks: continue/freeze.
```

```
R-09 · Windows portability spike · SLO/Submit · 5d cap · scanner+plugin + Swift core
Q/H: scanner+plugin build on Windows with parity fuzz pass.
Why now: windows dir is 0 files; question open (A F, B R-09).
Method: timeboxed spike only; no full port.
Success: priced plan. Fail: >4wk forecast → stay macOS-only. Unlocks: OWNER Windows decision.
```

```
R-10 · Testability triage · Estate · 5d · SLO CMakeLists custom targets (:1180-1264, no CTest) + KENN 700-file suite + backend conftest.py:19 nacl
Q/H: backend collects (venv fix), SLO wires CTest without breaking custom groups, KENN suite triaged to runnable subset with pass/fail/skip counts.
Why now: everything else depends on green suites (A F-05).
Method: fix venv; add CTest shims; --collect-only then -x with receipts.
Success: three receipts. Fail: suite unrunnable → rewrite test plan. Unlocks: all CI gates.
```

```
R-11 · Licence + cost clearance · Estate · 5d · THIRD_PARTY_NOTICES (SLO/SUBMIT/KENN) + PANNs/CLAP/onnx + testing-assets 57G + JUCE commercial + inference/API spend
Q/H: per-component licence table 100% filled; unlicensed assets quarantined; cost-per-seat modelled, no cliff <10x scale.
Why now: distribution blockers (B F-12/F-17, A F-12).
Method: inventory + obligation check + asset quarantine + cost model.
Success: shippable. Fail: GPL contamination or unlicensed bundle → hold bundle. Unlocks: paid launch + FT4-01 bundle.
```

## 3. Improvements backlog

Tier 1 — Hardening (do first):
```
I-T1-01 · Canonical-repo consolidation · estate · Problem F-01 · Change: declare truth per product (slo→Nite-DSP/slo, submit→private, KENN→standalone, platform→root), delete/submodule skeletons, drift-gate script (B FT1-05) · Reuse: existing remotes · S/M (1-2w) · Risk low, rollback re-clone · DoD: decision log + deletions + `git status` clean + drift CI green · RICE 120.
I-T1-02 · Secrets hygiene · estate · F-02 · Change: gitignore audit, rotate any ever-tracked secret, single secrets doc (paths only) · S (0.5w) · DoD: `ls-files | grep env|key` shows only .example+public · RICE 100.
I-T1-03 · Testability fixes · estate · A F-05/B F-06 · Change: backend venv (nacl), SLO CTest shims, KENN subset triage (R-10) · Files: backend/tests/conftest.py:19, SLO CMakeLists :1180-1264 · M (2w) · DoD: three receipts (collect+run counts) · RICE 110.
I-T1-04 · Dep pins · SLO/platform · A F-03 · Change: pin ONNX/TagLib (hash or vendor), align Python 3.11/3.12/3.13 matrix, Node 22 lock · M (1-2w) · DoD: clean-checkout build receipt · RICE 90.
I-T1-05 · Local-only fail-closed · KENN/DiskSweep · A F-11/B F-15 · Change: default provider ollama, refuse cloud without explicit key + UX disclosure; DiskSweep --no-llm flag (B FT1-02) · Files: llm_rewrite.py:170,182; ollama_client.py:7 · S (0.5-1w) · DoD: default-off test + privacy doc line · RICE 95. REJECT any cloud-by-default variant.
I-T1-06 · Archive scaffolds · Files/Paraphrase/Windows · F-07/F-08 · Change: archive artifacts, README-redirect, delete empty dirs (B FT1-06) · S (0.3w) · DoD: dirs gone/redirected, sale surface clean · RICE 80.
```
Tier 2 — Quality (gated on research):
```
I-T2-01 · Submit ship · Submit · R-06 · Change: verify_release_artifacts + Developer ID + notarise + appcast signing (B F-05/F-16) · S (1w) · DoD: signed+notarised + parity receipt · RICE 96.
I-T2-02 · Paddle harden · Platform · R-07 · Change: idempotency keys, replay/out-of-order tests, offline grace, staging rehearsal · M (2w) · DoD: live-fire receipt · RICE 100.
I-T2-03 · SLO beta readiness · SLO · R-01+R-04 · Change: licensing endpoint + signing, OOD threshold ship, DAW validation, multi-format flag (R-02) · L (6-8w) · DoD: beta gate receipt · RICE 70.
I-T2-04 · KENN pilot · KENN · R-03 · Change: 5-test fix, retrieval eval, supervised-pilot UX messaging (B FT1-04), VST3 packager · M (3-4w) · DoD: κ≥0.6 receipt + pilot label · RICE 65.
I-T2-05 · DiskSweep beta · DiskSweep · R-05 · Change: helper threat review, DMG CI smoke, BETA_KIT + undo-log UX (B FT2-04) · M (2-3w) · DoD: 5k fuzz receipt + DMG · RICE 75.
I-T2-06 · Per-product CI · estate · F-10 · Change: lint+build+test+smoke gates for SLO/KENN/Submit/DiskSweep; protect main; non-force mirror · M (2w) · DoD: 4 gates green · RICE 90.
```
Tier 3 — Differentiation (only after Tier 1):
```
I-T3-01 · Shared safety lib (undo/quarantine/Trash) · cross-product · Reuse SLO SampleManagerEngine.h:763-799 + DiskSweep helper · M (3w) · DoD: adopted in 2 products · RICE 60.
I-T3-02 · Shared licensing client (Swift) · Submit→DiskSweep · Reuse backend licensing.py · M (2w) · DoD: offline-verify <0.1% fail · RICE 64 (B FT2-06).
I-T3-03 · Update/diagnostics channel · all · Reuse Submit appcast pattern, telemetry-free · L (8w) · DoD: 2 products on channel · RICE 47 (B FT3-01).
I-T3-04 · Paraphrase build-or-kill · backend · R: demand proof first · Change: engine or kill + doc API · M · DoD: paid pilot or deletion · Kill: zero pilots 90d · RICE 40.
I-T3-05 · Library Health bundle · SLO+DS+Submit · Needs unified installer + bundle licence (B FT4-01) · L · Kill: WTP <£30 · RICE 38.
```

## 4. Sequenced 30/90/180 plan

Now (0-30d): I-T1-01 → I-T1-02 → I-T1-03 + R-10 → I-T1-05 → I-T1-06 → start R-07 + R-01 + R-05. Dependencies: canonicals before all code work; R-10 before CI.
Next (31-90d): finish R-01..R-07 + R-04 + R-11; I-T2-01 (first revenue) → I-T2-02 → I-T2-06 → I-T2-05 → I-T2-04 → I-T2-03; quick wins B FT1-01..FT1-04.
Later (91-180d): R-08/R-09 decisions; I-T3 tier; sunset executions; bundle decision (kill if WTP fails); Windows stay-or-go.

## 5. Owner-decision register

1. Canonical per product (7d) — options nested-truth vs mono-truth — recommend nested-truth + thin pointers.
2. Local-first brand promise (7d) — KENN default + Submit Sparkle must be disclosed either way.
3. Release gate: parity + notarisation + real-file validation mandatory? (14d) — recommend yes.
4. Windows: fund or macOS-only? (30d, pending R-09) — recommend macOS-only until revenue.
5. Generative/Thursday: freeze or fund? (30d, pending R-08) — recommend freeze sales, research-only.
6. Audio_Too: product vs private tooling? (14d) — recommend private.
7. Pricing: individual/bundle/subscription + site-licences? (14d) — Submit first, bundle after R-11.

## 6. Appendices

A. Commands: §0 list. B. Files inspected: A (1) + B subset (6 files: RESEARCH_AGENDA, FINDINGS_REGISTER, READINESS_MATRIX, FEATURE_BACKLOG, UPGRADE_ROADMAP + spot sources commerce.py, llm_rewrite.py, paraphrase.py, test dirs, benchmark dir); NOT re-read: all other B product reviews in full, any *.md for proof, large data/models. C. Scores reconciled: A vs B within 3 pts; B detail adopted where it executed tests. D. Unresolved: SLO gate path existence; KENN 5-failure reproduction; DS 31/31 reproduction; backend full-suite result; nested-remote enumeration; model/asset licences; DAW behaviour — all assigned to R-IDs above.
