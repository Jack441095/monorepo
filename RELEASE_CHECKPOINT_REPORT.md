# RELEASE CHECKPOINT REPORT

Date: 2026-08-25

## Repository

Branch: `design/website-v1-product-design-system` (new branch, first push this checkpoint)
SHA (before): `f2fe68fa77843bddce538f90d9bba708646d2635`
SHA (after): `97b4355f18050718c811d9138ee16e1885340e10`

## Changes

Summary: Two commits covering a site-wide design-system and copywriting pass. Commit 1 (`7f49154`) rewrites hero/capabilities/demo copy toward a more technical voice, replaces the pricing page's "Pricing TBC" placeholder with live Professional ($39) / Student ($19) licence tiers, adds two new marketing pages (`/products/submit`, `/technology`) and a shared `intelligence` component, adds two design-rationale docs, and removes a dead helper function (`scramble()`) surfaced by lint. Commit 2 (`97b4355`) updates four Playwright specs whose assertions targeted text removed by commit 1. Backend, SLO source, and submit-processing source were not touched — the only backend-adjacent activity was generated `__pycache__`/`.DS_Store` noise, left untracked.

## Validation

Lint: PASS, 0 warnings (1 pre-existing unused-var warning fixed by removing the dead `scramble()` function).
Typecheck: PASS (`tsc --noEmit`, 0 errors).
Build: PASS (`next build`, all 25 static routes generated, including the two new pages).
Tests: Playwright suite installed missing chromium binary, then ran full — **45/45 PASS** after updating the 4 specs whose assertions targeted old copy/pricing text (confirmed with the requester as an intentional rewrite before editing tests).
Secret scan: Clean across all new and modified files (key/token/password/PEM/AKIA patterns) — no credentials found.

## Commit

Hashes: `7f49154` (feat), `97b4355` (test)

## Push

Status: Success — first push of this branch (no prior upstream). `git push -u origin design/website-v1-product-design-system`. Post-push verification: local HEAD and `origin/design/website-v1-product-design-system` both at `97b4355f18050718c811d9138ee16e1885340e10`; `git status` reports branch up to date with no ahead/behind.

## Remaining Risks

- **Live pricing claim**: this branch now publishes real prices ($39 / $19) where the deployed site currently says "Pricing TBC." Confirm these figures are final with whoever owns commercial/pricing decisions before merging to `main`.
- Still no `.gitignore` in `platform/` — `.DS_Store` and `__pycache__` continue to surface as untracked noise on every checkpoint (unrelated to this change, flagged previously, still unresolved).
- Not merged, not deployed. This branch also sits on top of `design/website-nextgen-interaction-v1` at `dfacfe1`, which is itself unmerged — merge ordering/rebase should be considered before opening a PR.

## Recommended Next Action

Open a PR for `design/website-v1-product-design-system` against `main` (or against `design/website-nextgen-interaction-v1` if that lands first) once the pricing figures are confirmed final; GitHub already offered a compare URL on push (`https://github.com/Jack441095/NITE_DSP/pull/new/design/website-v1-product-design-system`).
