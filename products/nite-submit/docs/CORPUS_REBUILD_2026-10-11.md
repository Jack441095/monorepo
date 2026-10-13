# Submit corpus rebuild — 2026-10-11

The local `real_validation_corpus` now contains 35 public PDFs, 12 controlled
field-policy PDFs and one generated image-only edge case. PDFs, source URLs,
review values and generated reports remain ignored by Git.

Of the 31 documents in the three tracked acquisition manifests, 22 were recovered
with the exact recorded SHA-256. Nine could not be restored: three UTAR downloads
timed out, three CORE downloads were unavailable, two institutional sources had
changed, and one recorded hash had 65 hexadecimal characters instead of 64.
Thirteen current institutional PDFs were acquired separately. They do not stand
in for historical files or inherit their old hashes or review results.

Nine public covers have independently reviewed title and institution truth;
seven also have reviewed author truth. The other 26 public PDFs exercise layout
extraction without claiming accuracy for example names or instructional prose.
The controlled suite tests 11 student IDs, ten module codes and one explicit
absence of a student ID. Unreviewed fields are omitted, not marked absent.

Cover review uses rendered first pages and independent text extraction, rather
than Submit's answers. Three covers print `The University of Sheffield`; their
truth preserves that article even though older acquisition metadata omitted it.

## Reproduce the checks

From the product directory, using Python 3.11 or later and the existing Swift
toolchain:

```sh
python3 -m unittest discover -s tools -p 'test_*corpus.py'
swift run nitesubmit-tests
swift build --product nitesubmit-cli
python3 tools/check_rebuilt_corpus.py --cli .build/debug/nitesubmit-cli
```

`check_rebuilt_corpus.py` verifies source hashes and fixed review coverage before
creating fresh manifests. It runs both the public and controlled suites, rejects
missing or unreadable inputs, and fails on any reviewed false positive or false
negative, including medium-confidence suggestions. Reports are written under
`real_validation_corpus/manifests`.

`restore_public_corpus.py --check` separately audits the original 31 provenance
records without network access. It exits unsuccessfully while the nine original
sources remain unavailable. Without `--check`, it attempts hash-matching public
downloads and preserves existing local files. `build_reviewed_corpus.py` turns a
local independent review record into a validation manifest; it does not invent
truth or run the detector to supply answers.

## Baseline before shipping implementation

The following results describe the initial rebuild, not the final release.
The completed shipping results and migration follow below.

- All 35 public inputs and all 12 controlled inputs were processed, with no
  missing or unreadable files and no wrong high-confidence values.
- Public author checks passed 7/7. Title and institution checks each passed 8/9.
  The remaining case is an image-based MIT capstone cover: OCR selects
  `Research Scientist` as the title and an author's previous university as the
  institution. This accuracy case remains scored and makes the check exit 1.
- All 12 controlled cases passed, including the explicit absent-ID case.
- The blank image-only PDF has no embedded text. A batch dry run held it as
  `image_only` and created no renamed PDF.
- The rebuilt corpus exposed a split-title failure caused by PDFKit reading a
  cover's title text box after its byline. `FieldDetector.swift` now joins a
  terminal heading block on the first page, retaining lowercase continuations
  and excluding dates. The result stays medium confidence. A regression also
  prevents joining title fragments across page boundaries.
- All 503 Swift checks and 22 Python tool checks passed. Disabling the recovery
  hash guard, review hash guard and result false-positive guard in temporary
  copies made their regression tests fail. The title regression failed before
  the detector fix. Existing linker search-path warnings and the CoreGraphics
  diagnostic remained visible during verification.

At that baseline, the six historical validation manifests had not been
fabricated and the release scripts still required unavailable inputs. That
rebuild alone did not clear the private-beta gate.

A local archive under `artifacts/corpus-backups/rebuilt-2026-10-11.tar.gz` contains
only the 48 selected PDFs and their review/provenance/report records. Its contents
were checked against the source bytes after creation. It is ignored by Git and
is on the same drive; an independent backup is still needed to survive drive loss.

## Files changed for this rebuild

- `Sources/NiteSubmitCore/FieldDetector.swift`: first-page split-title recovery.
- `Sources/NiteSubmitTests/DetectorTests.swift`: continuation, confidence and page-boundary regressions.
- `tools/restore_public_corpus.py` and `tools/test_restore_public_corpus.py`: public-byte recovery and rejection tests.
- `tools/build_reviewed_corpus.py` and `tools/test_build_reviewed_corpus.py`: independently reviewed manifest assembly and qualification tests.
- `tools/check_rebuilt_corpus.py` and `tools/test_check_rebuilt_corpus.py`: fixed-coverage validation and failing-report tests.
- `docs/CORPUS_REBUILD_2026-10-11.md`: this record.
- Repository-level `docs/OPERATIONS_AUDIT_2026-10-08.md`: current rebuild results and remaining blockers.

## Completed shipping migration — 2026-10-11

The final packaged CLI passes all 47 ordinary inputs. Public author/title/
institution truth passes 7/7, 9/9 and 9/9; controlled IDs/modules pass 11/11 and
10/10, plus the explicit absent-ID case. The MIT case remains independently
scored, with unchanged truth and accuracy classification. All 26 guidance PDFs
remain layout-only. Unknown fields stay omitted.

Visual cover review, PDFKit and Vision output exposed dense OCR row merging,
a staff role outranking the title and dated prior qualifications outranking
the awarding institution. Geometry now uses vertical glyph overlap instead of
an absolute page tolerance. Bounded title repetition above the abstract retains
both OCR readings for human review; it does not replace general spelling with
this document's expected answer. Staff-role and dated-qualification filtering
also covers a standalone wrapped year. No filename, author or institution was
hardcoded in production logic. The existing split-title regression is preserved.

The explicit replacement gate uses
`tools/Fixtures/rebuilt_qualification_v1.json`: exact ordered case paths, PDF
hashes, reviewed-field names, evaluation modes and canonical truth fingerprints.
It contains no truth values or source URLs. The local review identities are
`REBUILT_PUBLIC_2026_10_11_V1` and `REBUILT_FIELD_POLICY_2026_10_11_V1`.
`stage_release_corpus.py` selects 47 total, 9 submission or 26 guidance records;
it rejects corpus destinations and nonempty/symlink staging directories. A
private file or changed record cannot qualify merely by appearing in a folder.

The obsolete six-manifest release calls were removed explicitly. Missing UTAR
name/module matrix coverage uses the independently reviewed Sheffield Stacey
cover. Missing Berklee approved-copy coverage uses the independently rendered
Sheffield Long cover, whose independently derived approved filename is
`75589_Yang_Long_Zero-shot_Image_Classification.pdf`. Its uncertain fields
remain held until approval. Cambridge and Edge Hill retain required-field and
guidance holds. A deterministic candidate case protects the colonless label;
locked/malformed cases are generated in disposable folders. These replacements
preserve behaviors, not historical extraction equivalence or corpus identities.

Write checks use regular fixture copies because production refuses symlink
sources for writes. Read-only qualified staging may use symlinks. Originals,
collision targets, approval state, required-field holds, Unicode and containment
were checked. Stale validation reports are removed before subprocess execution;
a failed child cannot leave a passing result. A failed release rerun removes the
old pass manifest before rebuilding.

The complete gate passed with 534 Swift checks, 27 corpus tool tests and 5 feed
tool tests. Critical OCR, qualification, candidate and corpus/report mutations
were rejected. Source, extracted ZIP and mounted DMG each passed the complete
rebuilt check using their own packaged CLI. Both tracked synthetic copies remain
in parity, including the prior ambiguous-name expectation correction: the
explicit name-bearing write load holds all 233 ordinary synthetic inputs.

The refreshed same-drive archive contains exactly 48 selected PDFs and current
reviews/provenance/reports plus the qualification record (58 members). Every
member was compared byte-for-byte with its source. SHA-256:
`d3b8112993f1408a02068d7d70b132348d1eed3d32c033f684775db6f490322a`.
The checksum is also retained under ignored corpus manifests. Private intake,
generated outputs, obsolete report snapshots and the self-referential checksum
are excluded. An independent backup is still required.

See ../NITE_SUBMIT_RELEASE_REPORT.md for the exact final artifact hashes and
remaining public-release requirements. The baseline failure above is retained
as history; it no longer blocks the private-beta gate.
