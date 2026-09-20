# NITE Submit localisation foundation v1

NITE Submit remains English-only in the current release. This phase establishes
the boundaries needed for a later multilingual interface without changing the
simple local detect, review, approve, and rename workflow.

## Stable rules

- Interface labels use stable keys such as `student_id`, `module_title`, and
  `project_title`.
- Values detected from a document are never translated before they are shown or
  used in a filename.
- Student numbers, candidate numbers, assignment codes, module codes, and
  other identifiers are preserved exactly, including leading zeroes.
- Transliteration is an explicit future option, not an implicit filename change.
- OCR language selection will be separate from interface language selection.
- Missing translations fall back to reviewed English labels until a complete
  translation has been approved.

The first implementation is intentionally a foundation only: English labels
are still the visible default, and no machine translation or network service is
introduced.
