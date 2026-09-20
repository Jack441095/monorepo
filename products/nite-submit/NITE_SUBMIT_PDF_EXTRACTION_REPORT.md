# NITE_SUBMIT_PDF_EXTRACTION_REPORT

> Historical extraction snapshot. Version 0.2.0 adds bounded local OCR for
> image-only PDFs; see `docs/NITE_SUBMIT_PDF_EXTRACTION_REPORT_V2.md`.

## Method

Deterministic pipeline: PDFKit embedded-text extraction → line normalisation →
label/pattern heuristics → confidence ranking. No OCR, no AI, no network.
Precision is prioritised over recall (§87): missing values are preferred to
confident wrong ones.

## Corpus results (NITE_SUBMIT_PDF_CORPUS_V1, 203 extracted PDFs)

| Field | Hits | Correct | Precision | Wrong-HIGH |
|---|---|---|---|---|
| Student name | 183 | 183 | **100%** | 0 |
| Student number | 189 | 189 | **100%** | 0 |
| University | 203 | 202 | **99.5%** | 1 |
| Module code | 186 | 186 | **100%** | 0 |
| Project title | 193 | 190 | **98.4%** | 0 |

- Overall wrong-HIGH-confidence rate: **1/203 = 0.49%** (target < 1%) — a single
  multi-institution document where the engine picked the partner university
  mentioned on the cover page instead of the primary institution.
- Latency (debug build, external SSD): avg ~13 ms / max ~680 ms per document.

## Quality targets vs results (§86)

| Target | Required | Achieved |
|---|---|---|
| Student ID precision | ≥ 98% | 100% ✅ |
| Explicit student name precision | ≥ 98% | 100% ✅ |
| Explicit module code precision | ≥ 98% | 100% ✅ |
| Explicit project title precision | ≥ 95% | 98.4% ✅ |
| Wrong HIGH-confidence critical fields | < 1% | 0.49% ✅ |
| Sanitiser deterministic tests | 100% pass | 100% ✅ |
| Original content mutation | 0 | 0 (hash-verified) ✅ |

## Adversarial coverage

Lecturer/supervisor names above student names (excluded), IDs inside reference
lists (ignored), path-like and punctuation-heavy titles (sanitised), Unicode
names (preserved), very long titles (length-capped), messy whitespace,
multi-institution covers, repeated headings (ranked), untrustworthy metadata
(LOW confidence only).

## Known limitations

1. Implicit titles depend on heading quality; noisy first pages may yield
   MEDIUM-confidence candidates the user must confirm — by design.
2. No OCR; scanned documents return "image-only" and require manual entry.
3. Single-institution bias in label spellings is mitigated by configurable
   student-ID patterns and generic module-code regexes, but real-world
   institutional formats beyond the corpus need beta validation.
