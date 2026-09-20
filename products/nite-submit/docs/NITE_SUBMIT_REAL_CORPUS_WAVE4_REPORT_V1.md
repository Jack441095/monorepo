# NITE SUBMIT — REAL CORPUS WAVE 4 REPORT

**Date:** 2026-08-25
**Status:** **COLLECTED — READY FOR VALIDATION**

## Purpose

Wave 4 adds official US university title-page and thesis-format samples to
balance the existing UK-heavy public corpus. The collection is deliberately
small and auditable: official university-hosted PDFs only, with no LMS,
portal, auth-gated, commercial essay-bank, or untrusted mirror sources.

## Collection

| Metric | Value |
|---|---:|
| PDFs added | 5 |
| Institutions represented | 4 |
| Countries | US |
| Official university-hosted sources | 5 / 5 |
| Student IDs intentionally collected | 0 |
| PDFs with named public sample authors | 3 |
| Duplicate SHA-256 values within wave | 0 |
| Image-only or malformed files | 0 |

Files are in `real_validation_corpus/university_templates/wave4/` and are
ignored as source artifacts. Provenance, source URLs, SHA-256 values, and
privacy flags are in
`real_validation_corpus/manifests/provenance_wave4.json`.

## Coverage added

- Colorado State University: separate master's and doctoral title-page
  samples, including title, student name, department, degree, institution,
  term, advisor, and committee fields.
- Northern Illinois University: a public named-author title-page sample.
- University of Nebraska: a multi-page thesis sample guide with a named
  author, major, institution, supervisor, and date.
- SUNY College of Environmental Science and Forestry: a formatting guide with
  a long institution name and named approval/committee fields.

## Research observations

The official University of Chicago Dissertation Office guidance describes a
title page as a layout convention rather than a Harvard/Chicago citation
choice: it specifies title-page typography, capitalization, margins, degree
name, and graduation date. The page also provides discipline-specific sample
templates. This supports keeping NITE Submit's university profile and naming
rule as independent controls; a citation style should not silently change the
filename fields.

Colorado State's official guidance similarly requires title, author, department,
degree, institution, date/term, and committee information, while explicitly
separating title-page layout from citation style. These documents are therefore
valuable for testing first-page field detection, but they are not evidence that
a filename should include every title-page field.

## Limitations

This wave is layout-focused. It does not provide real student-number recall,
because public university title-page examples generally omit student IDs or
use placeholders. Student-ID and module-code policy remain covered by the
controlled synthetic corpus and the existing Edge Hill/LSE examples. The next
privacy-safe source for those fields is an authorised beta intake, not broader
public scraping.

## Source pages

- Colorado State University, [thesis and dissertation organization guidance](https://graduateschool.colostate.edu/thesis-dissertation/organizing-and-formatting-your-thesis-and-dissertation/)
- Northern Illinois University, [templates and examples](https://www.niu.edu/grad/thesis/templates-examples.shtml)
- University of Nebraska, [thesis sample pages](https://graduate.unl.edu/sites/unl.edu.executive-vice-chancellor.graduate-studies/files/media/file/Thesis_SamplePages.pdf)
- SUNY ESF, [thesis formatting guidelines](https://www.esf.edu/graduate/documents/formatguidelines.pdf)
- University of Chicago, [sample title-page guidance](https://www.lib.uchicago.edu/research/scholar/phd/students/sample-title-pages/)
