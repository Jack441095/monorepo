# PRODUCT REVIEW — NITE FILES / NITE PARAPHRASE / NITE-SUBMIT-WINDOWS — 2026-09-17

## NITE Files · Verdict: ARCHIVE or CONSOLIDATE INTO Submit · 6/50 (Dead/Orphaned)
OBSERVED: `products/nite-files/` = `.build/` + `artifacts/Files-0.1.0-macOS.{dmg,zip}` only; no Sources/README/Package.swift (verified `ls`). Only evidence of code: `.build` object names (OrganizationRulesEngine, FolderScanner, FileOperations, DropZoneView). Cannot rebuild/sign/support. All claims **F**. Action: find canonical repo or ARCHIVE + redirect to Submit (F-07).

## NITE Paraphrase · Verdict: CONTINUE RESEARCH (server-side) · 8/50 (Spike)
OBSERVED: `products/nite-paraphrase/{engine,evals,tests}` all 0 entries (verified). Real logic: `monorepo/backend/app/paraphrase.py:31-101` (httpx proxy w/ MockTransport) + `paraphrase_orders.py`. Product scaffold **F**; server capability **B**. Action: delete scaffold, document server API (F-08).

## nite-submit-windows · Verdict: ARCHIVE (placeholder) · 3/50
OBSERVED: 0 entries. Action: delete until R-09 funds it.
