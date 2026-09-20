# NITE Submit real corpus wave 5

## Scope

Wave 5 adds six official university-hosted US title-page and thesis-format
samples from Missouri, Yale, Illinois, and Utah. The documents were collected
on 2026-08-25 from public university pages and are retained as local validation
inputs with source URLs and SHA-256 values in
`real_validation_corpus/manifests/provenance_wave5.json`.

These are layout and extraction smoke cases, not student-submission accuracy
truth. They contain public sample names, placeholder-style academic prose,
committee/adviser names, and no student numbers. They therefore use
`evaluation_mode: layout_only` and must not inflate recall or precision claims.

## Validation

The canonical release runner validates `wave5_manifest.json` and includes the
six PDFs in its qualified batch dry run. Expected safety properties are:

- all six PDFs open or extract without a missing-file failure;
- no document is treated as a high-confidence student submission truth case;
- titles and bylines remain reviewable when institutional degree or committee
  prose surrounds them;
- no output is written by the dry-run batch.

## Provenance and privacy

Only official university-hosted public documents were used. No login-protected,
private, or user-submitted PDFs were collected. Public sample author names are
retained inside the PDFs because they are part of the source examples; they are
not promoted into machine-readable accuracy truth. Private beta PDFs remain
confined to the ignored `beta_intake` workflow.
