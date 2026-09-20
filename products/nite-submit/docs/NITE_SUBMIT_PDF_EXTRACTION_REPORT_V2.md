# NITE SUBMIT — PDF EXTRACTION REPORT V2

Comparison of the V1 synthetic baseline, the V1.1 synthetic regression
(NITE_SUBMIT_PDF_CORPUS_V1 extended to 239 cases / 233 extractable PDFs), and
real-document validation status.

## 1. V1 baseline (recorded before changes)

203 extracted PDFs · wrong-HIGH 0.49% (1/203) · name 100% / ID 100% /
university 99.5% / module 100% / project title 98.4%.

## 2. Changes made in V1.1 (all deterministic, evidence-driven)

| Change | Trigger |
|---|---|
| Word-boundary anchor on module-code regex (`\\b`) | V2 regression caught leftmost-match bug: `MANGTBL-20-2` → `ANGTBL-20-2` |
| Generic academic heading penalty in title ranking | Real-world convention: banners like "FINAL REPORT"/"ASSIGNMENT" are not project titles |
| Page-1 first-line priority + partnership-word exclusion for university | Known 1/203 multi-institution error (partner university preferred over primary) |
| Group-name ambiguity handling | Multiple labelled student names now cap at MEDIUM with candidates surfaced |

## 3. V1.1 synthetic regression results (233 extracted PDFs)

| Field | Precision | Recall | HIGH-confidence precision | Wrong-HIGH |
|---|---|---|---|---|
| Student name | 100% (213/213) | 91.4%* | **100%** | 0 |
| Student number | 100% (219/219) | 98.2%* | **100%** | 0 |
| University | 100% (233/233) | 100% | **100%** | 0 |
| Module code | 100% (206/206) | 95.4%* | **100%** | 0 |
| Project title | 98.7% (220/223) | 100% | **100%** | 0 |

\* Recall deltas are ground-truth bookkeeping of the extended corpus
(image-only/malformed/absent-field cases count as expected-missing), not
extraction regressions versus V1.

**Wrong HIGH-confidence rate: 0/233 = 0.00% on truth-present fields.**

The previous known university error (multi_institution_00, Cardiff partner
line chosen over UWE Bristol) is fixed by partnership-line exclusion.

## 4. Release performance (measured)

Latency over the full corpus, single process:

| p50 | p95 | p99 | max |
|---|---|---|---|
| 1.3 ms | 2.2 ms | 3.9 ms | ~215 ms |

Peak resident memory for an entire 233-document batch: **~38 MB**
(no growth across the batch; text-only extraction with page caps).

## 5. Real-document validation

See NITE_SUBMIT_REAL_DOCUMENT_VALIDATION_V1.md — **BLOCKED: authorised corpus
required.** The validation harness, anonymised reporting and review UI are
ready; no real-world precision claims are made.

## 6. Failure-mode taxonomy observed (synthetic forensics)

| Mode | Class | Status |
|---|---|---|
| Leftmost regex match truncating module codes | REAL DEFECT | FIXED (word boundary) |
| Generic banner headings winning title ranking | REAL DEFECT RISK | MITIGATED (penalty) |
| Partner institutions on cover pages | AMBIGUITY | MITIGATED (exclusion list) |
| Group submissions with multiple names | BY DESIGN | MEDIUM confidence + candidates |
| Image-only documents | OUT OF SCOPE | graceful manual-entry path |
