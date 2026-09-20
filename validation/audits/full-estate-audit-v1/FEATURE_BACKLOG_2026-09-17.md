# FEATURE BACKLOG — 2026-09-17 (RICE = Reach*Impact*Confidence/Effort; Effort in person-weeks)

## Tier 1 — Quick wins (<=1wk)

- FT1-01 · Submit: one-click "copy diagnostics bundle" (reuse release-manifest + CorpusTests fixtures). Reach 200/mo Impact 2 Conf 0.8 Effort 0.5 → **640**. Kill: <5% of support tickets use it in 60d.
- FT1-02 · DiskSweep: rules-only `--no-llm` mode (classifier.py already separable; sidecar stdlib-only). 300/1/0.8/0.5 → **480**. Kill: parity fuzz delta >2%.
- FT1-03 · SLO: expose CLI flags/batch + dry-run report export (engine already has journal CSV). 150/2/0.8/1 → **240**. Kill: no beta-tester usage.
- FT1-04 · KENN: surface "supervised pilot only" + AutoMix-disabled messaging in UX (docs already authoritative). 200/1/1.0/0.3 → **667**. Kill: user confusion tickets persist.
- FT1-05 · Estate: drift-gate script (diff backend/platform, website versions, kenn note count) in CI. 20 dev-runs/3/1.0/0.5 → **120** (internal). Kill: false-positive rate >10%.
- FT1-06 · NITE Files/Paraphrase/Windows: delete or README-redirect scaffolds (F-07/F-08). 50/1/1.0/0.3 → **167**. Kill: N/A (hygiene).

## Tier 2 — Differentiation (1–6 wks)

- FT2-01 · SLO multi-format discovery (AIFF/FLAC/MP3) behind feature flag; gated by R-01. 2000/3/0.5/6 → **500**. Kill: accuracy drops >3pts vs WAV baseline.
- FT2-02 · KENN qualified mix-review v1 (fix 5 failures, human listening ref from R-03). 500/3/0.5/4 → **187**. Kill: human agreement κ<0.4.
- FT2-03 · Submit university site-licence pack (batch CLI + acceptance sweep already exist). 50 institutions/3/0.8/3 → **40** (high value per seat). Kill: zero paid pilots in 90d.
- FT2-04 · DiskSweep BETA_KIT + undo-log UX (qa/BETA_KIT + sidecar undo log exist). 500/2/0.8/2 → **400**. Kill: false-positive Trash rate >1%.
- FT2-05 · SLO find-similar service reused by KENN/Audio_Too (HNSW 512-D). 300/2/0.5/3 → **100**. Kill: latency >2s on 50k libs.
- FT2-06 · Shared Swift licensing client (Submit→DiskSweep) from backend licensing.py. 400/2/0.8/2 → **320**. Kill: offline-verify fails >0.1%.

## Tier 3 — Ecosystem (1–2 quarters)

- FT3-01 · Single update/diagnostics channel (Submit appcast pattern → all products; telemetry-free). 3000/2/0.5/8 → **187**. Kill: notarisation cost > revenue.
- FT3-02 · Model/asset registry (PANNs ONNX, CLAP, notes index, fixtures) with hashes + licences. 100/3/0.8/6 → **40** internal. Kill: registry unused after 90d.
- FT3-03 · KENN VST3/AU beta program (after DAW validation R-04). 800/3/0.5/8 → **150**. Kill: crash rate >1/session.
- FT3-04 · Design-system adoption across website + Submit + DiskSweep UI. 2000/1/0.5/6 → **167**. Kill: no velocity gain.

## Tier 4 — New products (>=60% ingredients)

- FT4-01 · "NITE Library Health" (SLO scan + DiskSweep safety + Submit rename) — local-first media ops bundle. Missing 40%: unified installer + bundle licence. 1000/3/0.2/8 → **75**. Kill: bundle willingness-to-pay <£30.
- FT4-02 · "KENN Pilot for Education" (chat KB + mix-review + Submit) for course delivery. Missing: institution admin + offline pack. 100 institutions/3/0.2/8 → small. Kill: zero LOIs.
