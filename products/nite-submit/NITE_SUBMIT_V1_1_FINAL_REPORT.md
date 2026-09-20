# NITE SUBMIT V1.1 FINAL REPORT

> Historical snapshot of the 0.2.0 beta before the current corpus and OCR
> validation work. See `NITE_SUBMIT_RELEASE_REPORT.md` for current evidence.

## Verdict

**NITE SUBMIT V1.1: PASS WITH LIMITATIONS**
**PRODUCT STAGE: PRIVATE BETA RC1 (0.2.0)**
**REAL-DOCUMENT VALIDATION: BLOCKED — AUTHORISED CORPUS REQUIRED**

No real-world precision claims are made; the validation harness is complete
and awaiting the owner's authorised corpus (see
docs/NITE_SUBMIT_REAL_DOCUMENT_VALIDATION_V1.md for exact supply instructions).

## Key facts

| Item | Value |
|---|---|
| BRANCH | engineering/nite-submit-v1.1-beta |
| STARTING SHA | 0485d6d6a8e75e1a7cd89aae857795676a7aac01 |
| ENDING SHA | see `git rev-parse HEAD` |
| COMMITS | narrow conventional commits on this branch |
| PUSH | private GitHub remote configured; current branch is being pushed via the safe handoff |
| SWIFT | Apple Swift 6.3.3, tools-version 5.9, macOS 13+ |

## Synthetic regression (NITE_SUBMIT_PDF_CORPUS_V1 extended)

233 extracted PDFs (239 cases incl. image-only/malformed simulations):

| Field | Precision | HIGH-conf precision | Wrong-HIGH |
|---|---|---|---|
| Student name | 100% | 100% | 0 |
| Student number | 100% | 100% | 0 |
| University | 100% | 100% | 0 |
| Module code | 100% | 100% | 0 |
| Project title | 98.7% | 100% | 0 |

**Wrong HIGH-confidence rate: 0/233 = 0.00%** (V1: 0.49%) — improved.

## Hardening delivered

1. Module-code word-boundary fix (leftmost-match truncation defect found by
   the new V2 regressions).
2. Generic academic heading penalty in project-title candidate ranking.
3. University detection: page-1 first-line priority + partnership-line
   exclusion (fixes V1's only wrong-HIGH case).
4. Group-submission ambiguity: multiple labelled names cap at MEDIUM with
   candidates surfaced.

All fixes are deterministic. No OCR. No AI. No network.

## Real-document infrastructure delivered

- Manifest-driven `validate` command (anonymous IDs, ABSENT handling,
  per-field precision/recall/HIGH-precision, latency percentiles).
- Keyboard-driven resumable `review` interface for ground-truth confirmation.
- Privacy-safe results JSON (status codes only; values withheld).

## Safety regression re-verified

Create-copy default ✅ · rename confirmation ✅ · undo ✅ · byte preservation
(SHA-256 hard regression) ✅ · zero unsafe overwrites ✅ · zero known critical
data-loss defects ✅.

## Performance & memory (Release)

p50 1.3 ms · p95 2.2 ms · p99 3.9 ms · max ~215 ms · peak RSS ~38 MB across a
233-document batch with no growth.

## Artifact

`artifacts/NITESubmit-0.2.0-macOS.app` (1.0 MB; compressed zip ~302 KB),
ad-hoc signed, SHA-256 recorded in NITE_SUBMIT_RELEASE_REPORT.md lineage.

## Owner decisions required

1. Supply authorised real corpus → run validation harness.
2. Developer-ID signing / notarisation policy for wider beta.
3. Whether batch drop should enter V1.2.
