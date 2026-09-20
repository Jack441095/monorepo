# TESTING — NITE Submit

Run everything with:

```sh
swift run nitesubmit-tests
```

For the packaged macOS UI, use the separate local smoke check after granting
Accessibility permission to the terminal running it:

```sh
./tools/run_app_ui_smoke_check.sh
```

It opens the real Berklee sample, exercises Approve details → Create Renamed
Copy through the AppKit controls, writes only to
`real_validation_corpus/test_results/app_ui_smoke_current/`, and verifies the
source hash is unchanged. It deliberately is not part of the headless release
gate because System Events control is machine-specific.

## Suites

| Suite | What it covers |
|---|---|
| FilenameSanitizer | forbidden/control chars, duplicates, dots/spaces, Unicode preservation, case styles, length caps, determinism |
| TemplateEngine | rendering, required-field gating, optional collapse, unknown-variable validation, date/original-name variables |
| FieldDetector | cover sheets, staff-name exclusion, reference-ID resistance, ID/module format variants, missing-field correctness, candidates, metadata distrust, Unicode |
| FileOperations | copy byte-preservation (hard regression), rename hash identity, undo, collision policies, failure cases, settings round-trip |
| PDF Corpus | NITE_SUBMIT_PDF_CORPUS_V1: 203 real generated PDFs, field-level precision gates, wrong-HIGH rate gate, latency |
| Failure handling | image-only simulation, malformed PDF, zero-byte file, missing file |

## Corpus

`tools/generate_corpus.py` deterministically generates **209 labelled cases**
(203 real PDFs) covering clear cover sheets, ID/label variants, module-code
formats, adversarial staff/reference content, implicit titles, missing fields,
image-only and malformed simulations, Unicode, path-like titles, very long
titles, multi-institution text, messy whitespace, metadata-only titles and a
50-page report. Ground truth lives in `manifest.json`.

## Quality gates enforced by tests

- student name / student ID / module code precision ≥ 98%
- project title precision ≥ 95%
- wrong HIGH-confidence critical extractions < 1% of documents
- original bytes bit-identical after CREATE COPY (SHA-256)
- content hash identical after RENAME ORIGINAL
