# PRODUCT INVENTORY — 2026-09-17 (companion to CSV)

See `PRODUCT_INVENTORY_2026-09-17.csv` for machine-readable rows. Readiness bands: 0–14 not-a-product · 15–24 prototype · 25–34 alpha · 35–42 beta-ready · 43–47 RC · 48–50 shipped.

| Product | Stage | Score | Verdict | Build/Test (verified this audit) |
|---|---|---|---|---|
| SLO | Alpha | 30 | HARDEN | build dirs present; tests not run (toolchain) |
| KENN | Alpha | 28 | SHIP AFTER FIXES (pilot) | mix-review: 53 pass / 5 fail (VERIFIED) |
| NITE Submit | RC | 41 | SHIP AFTER FIXES | swift not run (TOOL_MISSING); artifacts 1.0.0 present |
| NITE Files | Dead | 6 | ARCHIVE/CONSOLIDATE | no source; orphaned dmg/zip |
| NITE Paraphrase | Spike | 8 | CONTINUE RESEARCH | scaffold empty; server code real |
| DiskSweep | Proto→Alpha | 27 | HARDEN | 31/31 pytest PASS (VERIFIED) |
| AudioGen | Prototype | 18 | CONTINUE RESEARCH | not run |
| AutoMix/MixReview | Proto/Disabled | 20 | HARDEN/disabled | 53/5 (same as KENN) |
| Thursday | Prototype | 22 | CONTINUE RESEARCH | not run |
| Platform backend | Alpha | 29 | HARDEN | ruff PASS (VERIFIED); pytest blocked (no nacl) |
| Platform website | Alpha | 28 | HARDEN | not run |
| Audio_Too | Internal Alpha | 24 | CONSOLIDATE | not run |
| Client-Work | N/A | — | no verdict | spot check only |

Scores D1–D10 detail live in each PRODUCT_REVIEW file; comparison matrix §6 of the master report.
