# NITE Submit corpus classification v1

The corpus is now divided into two purposes so guidance prose does not distort
student-submission accuracy metrics.

## Layout-only/adversarial fixtures

- 9 first-wave university templates, cover sheets, and formatting guides.
- 4 second-wave official documents from Essex, Exeter, Manchester, and
  Washington.
- 3 third-wave official US guidance documents from South Carolina, Colorado
  Anschutz, and Georgia.
- Used for PDF extraction, first-page layout, OCR, title-heading, guidance
  false-positive, and review-gate tests.
- Never counted as student-field truth unless a case is explicitly promoted
  after review.

## Accuracy candidates

- 11 public dissertations.
- 3 public project/capstone reports.
- 1 public final paper/portfolio.
- These 15 cases are the current candidates for reviewed student-name and
  project-title accuracy metrics.

## Scoring rule

Validation manifests may set `evaluation_mode` to `layout_only`. Such cases are
still extracted and included in processing/latency checks, but their detected
field values do not contribute true-positive, false-positive, false-negative,
or wrong-high-confidence accuracy counts.

This separation is deliberately conservative: a document that explains how to
format a thesis is useful for adversarial testing, but it is not evidence that a
student name or project title was correctly detected.

The rule is covered by
`real_validation_corpus/manifests/layout_only_smoke_manifest.json`: the Exeter
guidance PDF processes successfully, contributes zero accuracy counts, and
produces zero wrong-high-confidence cases in the layout-only smoke run.
