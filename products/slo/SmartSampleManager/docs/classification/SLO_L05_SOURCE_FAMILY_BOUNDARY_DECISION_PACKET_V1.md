# SLO L-05 Source-Family Boundary Decision Packet V1

**Status:** Awaiting an explicit owner decision; this packet is not an
approval or qualification receipt.

## Decision needed

Select the source-family identity to use when preparing the next corrected
17-class research manifest and its leakage-controlled train/test split.

## Evidence currently available

The metadata-only preflight at
`SLO_CLASSIFICATION_CORPUS_METADATA_PREFLIGHT_V4.json` inspected 5,157 files,
15 vendors, and all 17 taxonomy classes without decoding or modifying audio.
It recorded 49 duplicate-basename groups (98 rows), so path identity must be
preferred over basename matching.

The preflight is bound to source SHA `e731d1b52247` and is an inventory receipt,
not a current scorecard or owner-reviewed ground-truth receipt.

## Options

### Option A — Legacy first-three-token family

Do not use for qualification. The preflight found 20 mixed-label families and
only one family for Music Loop, so this boundary fails the minimum five-family
requirement and can leak or merge incompatible labels.

### Option B — Candidate metadata family

Use `vendor + mapped source folder + first five underscore-delimited filename
tokens` for an exploratory manifest only. The preflight found zero mixed
families and at least five families for every class. This remains derived from
vendor folder mappings and filename structure, not independent per-file
ground truth; it must not be used for a release claim without provenance and
review.

### Option C — Provenance-backed family IDs

Require a reviewed family identifier tied to vendor, pack/source lineage, and
the exact relative path before a row enters the qualification manifest. This
has the strongest leakage-control story, but requires provenance reconciliation
and explicit handling of ambiguous or disputed labels.

## Recommendation

Use Option B only to prepare and inspect an exploratory package. Use Option C
as the qualification boundary. Until that decision and the required review are
recorded, keep the current L-05 package blocked and do not export new runtime
weights or publish scorecard numbers as product evidence.

## Work that can continue safely

- Maintain runtime safety, evidence presentation, cache-version, and format
  handling tests.
- Improve the research harness and package validator without changing the
  frozen classifier weights.
- Prepare a path-identified manifest and reviewer queue outside the product
  source tree, marked exploratory and pending review.
- Execute native qualification only when the CPU environment and declared
  host/corpus scope are available.

## Risks and irreversible consequences

- Treating vendor folder labels as independent truth can inflate apparent
  generalisation and produce false confidence in OOD rejection.
- Changing the family definition after model fitting invalidates the split,
  metrics, OOD thresholds, and any exported weights.
- A basename-only join can assign a different vendor's label to a cached row;
  ambiguous basenames must be rejected.

## Rollback

Do not replace the current manifest or runtime header. Any exploratory output
must remain in the external research-artifact directory. If the selected
boundary is rejected, retain the preflight and current blocked receipt, discard
only the unqualified exploratory package, and regenerate from a new
owner-approved manifest with a new source/evidence receipt.

## References

- `tools/classification_benchmark/audit_corpus_metadata.py`
- `docs/classification/SLO_CLASSIFICATION_CORPUS_METADATA_PREFLIGHT_V4.json`
- `docs/classification/SLO_CLASSIFICATION_L05_EVIDENCE_GAP_V1.md`
- `tools/classification_benchmark/validate_l05_qualification_package.py`
