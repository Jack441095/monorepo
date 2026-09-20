# NITE Submit field policy v1

Status: implemented in the 0.2.0 beta artifact.

This policy keeps the detector useful across US and UK cover-sheet layouts
without turning ambiguous text into a filename automatically.

## Student numbers

- A number following an explicit student-number label is high confidence when
  it matches a supported institutional format, including five-to-twelve digit
  numbers and common letter-number forms.
- The accepted labels include student number/ID/no, registration number,
  matriculation number, enrolment/enrollment number, university ID, and student
  reference.
- An unlabelled number-shaped token remains a lower-confidence fallback and is
  never treated as a personal student number merely because it appears on an
  early page.
- A saved student number is a local user-provided fallback. It is shown as
  such in the evidence and can be cleared from the app.

## Module codes

- A code after an explicit module/unit/course-code label is high confidence.
- An unlabelled code-shaped token, including short forms such as `CS101`, is
  surfaced as low confidence for review. This improves recall without making
  guidance-page version tokens or unrelated identifiers automatic filename
  components.
- Module codes remain optional unless the selected naming template requires
  `{module_code}`.

## Multiple authors and group work

- The detector retains alternatives when it sees more than one plausible
  student/author name.
- If a filename template contains a personal name, approval is blocked until
  the user edits the Student name field to make an explicit choice.
- ID-only and anonymous-candidate templates do not require a group-name choice;
  they can be used when the assessment requires anonymity.
- The original PDF is never changed until the user approves the complete
  filename preview.

## Evidence boundary

The public corpus currently proves name/title/university behavior on the
reviewed cases. Student-ID and module-code accuracy claims remain intentionally
limited until additional documents with explicit, reviewable ground truth are
added. The synthetic corpus covers format and false-positive regressions; it is
not a substitute for institution-specific accuracy evidence.
