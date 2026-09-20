# SLO Classification — Active Learning / User Correction Design (Phase K)
# and Classification Confidence UX Contract (Phase L)

**Status: DESIGN ONLY. Nothing in this document is implemented in this
phase.** No retraining pipeline, no EMBER UI, no data-collection code is
built here. This defines a data model, states, and a UX contract for a
future, separately authorized phase to implement.

---

# Part 1 — Active Learning / User Correction (Phase K)

## 1.1 Why this matters (tie-in to this phase's own findings)

This closeout's Vocal Loop forensics (`SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md`)
found a real, previously-invisible classification defect using nothing more
than a per-sample table cross-referencing ground truth against the
system's own evidence trail. A user-correction pipeline is, structurally,
the same idea running continuously and at scale: every time a user
overrides SLO's classification, that correction *is* a ground-truth-vs-
prediction disagreement, for free, on real usage data spanning whatever
vendors/naming-conventions/content a real studio actually has — directly
addressing the single-vendor dataset gap identified as the top V5 priority
(`SLO_CLASSIFICATION_V5_RESEARCH_BASELINE.md` §1.2, §6.5). This is why V5's
research baseline ranks it as potentially the highest long-run value item,
even though it has the longest time-to-value.

## 1.2 Where user corrections already exist today (not new — reused, not rebuilt)

`SampleManagerEngine` already has a `tagUserOverridden` flag and a
`user_tag_overrides` SQLite table (`applyUserTagOverride`,
`writeUserTagOverride`, seen in `SampleManagerEngine.cpp`) that persists a
user's manual category/subcategory/tag correction locally and protects it
from being silently clobbered by a later re-scan (`prepareFile`'s taxonomy
block explicitly skips re-classification when `tagUserOverridden` is set).
**This is the correct foundation to build on** — it already captures "user
decision = authoritative" at the single-machine level. What does not exist
today is any mechanism for that correction to leave the user's machine, be
aggregated, or feed back into evaluation/training data. This section
designs that missing, opt-in half only.

## 1.3 Data model

A structured correction record, captured locally at the moment of
correction (reusing the existing `user_tag_overrides` write path as the
trigger, not a new UI flow):

```
CorrectionRecord {
  sample_fingerprint: string   // content hash already computed today
                                // (SampleItem::contentHash) -- NOT the file
                                // path, which is private/local and must
                                // never leave the machine (see §1.5)
  original_prediction: {
    category: string
    subcategory: string
    secondary_tags: string[]
    confidence: float
    winning_evidence: string   // "EMBEDDED_METADATA"|"FILENAME"|"FOLDER"|"DSP"
    ml_evaluated: bool
    ml_was_ood: bool
  }
  corrected_label: {
    category: string
    subcategory: string
    secondary_tags: string[]
  }
  model_version: string        // matches the frozen head's version marker
                                 // (there is currently no explicit runtime
                                 // version constant for
                                 // AcousticClassifierWeights.h/Centroids.h --
                                 // a prerequisite for this design, noted as
                                 // an open item in §1.7)
  taxonomy_version: int        // AbletonTaxonomy::kTaxonomyVersion at
                                 // correction time (already exists, bumped
                                 // 1->2 by this phase's Vocal Loop fix)
  corrected_at: timestamp
  correction_source: "manual_tag_edit" | "drag_to_different_bucket" | ...
}
```

Design choices, and why:
- **Fingerprint, not file path or filename.** The whole point is
  cross-vendor generalization data; filenames/paths are exactly the kind of
  local, potentially personally-identifying information (a user's project
  names, client names, internal folder structure) that must never leave a
  local machine under any circumstances. `contentHash` already exists and
  is vendor/path-independent.
- **Both the original prediction AND its evidence trail are captured, not
  just old-label/new-label.** A correction on a `winning_evidence:
  "FILENAME"` sample teaches something different from a correction on a
  `winning_evidence: "DSP"` sample (the former is exactly this phase's bug
  class: heuristic-precedence-wrong; the latter is more likely a genuine
  embedding/DSP-signal gap). Losing this distinction would make the
  resulting dataset far less useful for root-causing the *next* Vocal-
  Loop-shaped defect.
- **model_version / taxonomy_version are mandatory fields**, not optional
  metadata — a correction made against a stale taxonomy or an old model
  version could otherwise silently poison training against the *current*
  system's actual failure modes.

## 1.4 What this explicitly does NOT do

- **Never trains on the user's own machine.** No gradient step, no
  centroid recomputation, no local model mutation happens as a side effect
  of a correction. `MlOverrideGate`/`AcousticClassifierWeights.h`/
  `AcousticClassifierCentroids.h` remain exactly what shipped, on every
  machine, until a deliberate, versioned, centrally-produced model update.
  This preserves V4-H's frozen-architecture guarantee at the fleet level,
  not just within this repository.
- **Never uploads audio.** Only the fingerprint + structured labels above.
  No raw audio, no embedding vector (the 512-D embedding dump seen in
  `ClassificationBenchmark`'s local/gitignored diagnostic output is a
  benchmarking-only artifact and is explicitly NOT part of this design's
  data model).
- **Never uploads anything without explicit opt-in**, and opt-in is a
  product/legal decision for the owner to make separately, not assumed by
  this design. Default state is opt-out.

## 1.5 Opt-in / privacy-respecting path (design sketch)

1. Local accumulation: every correction (§1.3) is appended to a local,
   user-visible, user-clearable log (e.g. a `correction_log` table
   alongside the existing `user_tag_overrides` table) regardless of
   opt-in state — this makes the feature auditable and inspectable before
   a user ever decides whether to share it, and is useful locally on its
   own (a user could review "what have I corrected and why" as a debugging
   tool for their own library).
2. Explicit, separate opt-in setting (distinct from any other telemetry/
   analytics opt-in the product may have) specifically for "share
   anonymized classification corrections to improve future versions,"
   defaulting OFF, with the data model above shown to the user (or at
   minimum a plain-language description of exactly these fields) before
   they can turn it on.
3. If enabled: periodic, batched, user-visible sync (not silent
   background upload) of the local correction log to a NITE DSP-owned
   collection endpoint — batching and visibility both matter for trust,
   not just efficiency.
4. Server-side: corrections accumulate into a versioned, append-only
   corpus, separate from the existing single-vendor qualification corpus
   (`dataset_manifest.json`) — never silently merged into it. A future,
   human-reviewed promotion step (NOT automatic) decides whether/when
   accumulated corrections graduate into an actual eval/training set
   addition, exactly mirroring how `LABELING_PROTOCOL.md`/
   `GOLDEN_SET_V1_METHODOLOGY.md` already require human-authored ground
   truth today — user corrections are a *candidate signal*, not
   auto-trusted ground truth (a user can be wrong too).
5. No automatic retraining trigger at any volume threshold. Any future
   retrain remains a deliberate, versioned, qualified phase — exactly like
   V4-F through V4-H and this closeout were.

## 1.6 Correction quality / trust considerations

Not every user correction is a reliable label (a user might miscategorize
too, or "correct" something for their own personal-workflow reasons that
don't reflect the sample's actual content — e.g. deliberately re-tagging a
Vocal Loop as Music Loop because that's where they want it to sort in
their own browser). Recommended (design-only) mitigations for a future
implementation phase to evaluate:
- Weight/flag corrections by agreement across multiple users on the same
  `sample_fingerprint` (only possible for content that recurs across
  users' libraries — e.g. commercial packs, not personal recordings) —
  requires no per-user identity, just fingerprint-level aggregation.
- Track correction "reversals" (a user corrects, then corrects back) as a
  signal the original correction may have been a mistake or workflow
  preference rather than a real label fix.
- Never let a single correction outweigh a `TRUSTED_PACK_LABEL`/
  `OWNER_VERIFIED` ground-truth entry in the existing qualification corpus
  without human review.

## 1.7 Open items for a future implementation phase

- No explicit runtime version constant currently exists for the frozen ML
  head/centroids (`AcousticClassifierWeights.h`/`AcousticClassifierCentroids.h`
  have no `kModelVersion`-equivalent to `AbletonTaxonomy::kTaxonomyVersion`).
  Adding one is a prerequisite for `CorrectionRecord.model_version` to be
  meaningful, and is a small, low-risk addition worth doing early in any
  future phase that builds on this design (does not require reopening the
  frozen architecture's *behavior*, only adding a version label to it).
- Legal/privacy review of the opt-in flow (§1.5) by the product owner is
  required before implementation — this document is an engineering design,
  not a privacy-policy or ToS.

---

# Part 2 — Classification Confidence UX Contract (Phase L)

## 2.1 Grammar

Per NITE DSP's established AI-surface grammar: **machine proposal =
provisional, user decision = authoritative.** Every state below is a
description of how confident/certain the *machine's proposal* is — never a
claim of correctness, and never presented in a way that outranks a user's
own subsequent correction (which, per Part 1, is captured with
`correction_source` precisely because it always wins).

## 2.2 States

| State | Definition (from existing system signals) | What it should communicate |
|---|---|---|
| **HIGH-CONFIDENCE KNOWN** | Known class, evidence tier `EMBEDDED_METADATA`/`FILENAME`, OR `winningEvidence` other with `tagConfidence` above a high band, AND (if ML was consulted) `diagMlIsOod == false` with a comfortable centroid-distance margin | This looks right; no action needed, but it is still a proposal, not a verified fact |
| **LOW-CONFIDENCE KNOWN** | Known class, but reached via `winningEvidence: "DSP"` alone, or `tagConfidence` below the high band (e.g. the honest low-confidence "Other"/ambiguous-Loop-bucket paths `AbletonTaxonomy::classify()` already produces today), or ML evaluated but near its per-class OOD threshold without crossing it | Worth a glance; the system is genuinely less sure here than in the HIGH-CONFIDENCE case, and should not visually look identical to it |
| **AMBIGUOUS** | Multiple evidence sources disagree in a way the current hard-precedence chain cannot resolve (the exact shape of state this phase's Vocal Loop fix's fall-through case represents: `loopEvidence == oneShotEvidence`, i.e. both or neither present) — a new, honest state this phase's fix makes newly representable, since previously that case silently produced a confident-looking wrong answer | This one is a genuine toss-up between two specific candidates; surfacing the candidates (not just "unsure") is more useful than a bare low-confidence score |
| **UNKNOWN/OOD** | `diagMlIsOod == true` (per-class-thresholded), or heuristic classification produced no match at all (`AbletonTaxonomy::classify()`'s `category=""`/`confidence=0.0f` "Other" path) | This does not match anything the system currently recognizes — invites a correction rather than presenting a guess |
| **USER-CORRECTED** | `tagUserOverridden == true` (already exists today) | This is authoritative; the machine's original proposal is historical context only (useful for the active-learning pipeline in Part 1, not for re-litigating the user's decision in the UI) |

## 2.3 What NOT to expose

- **No bare percentage confidence scores in the primary UI.** The
  underlying `tagConfidence`/`diagMlConfidence` values are, by
  `AbletonTaxonomy.h`'s own doc comment, "an honest, if approximate,
  signal — not a calibrated probability." Presenting `0.63` or `63%` next
  to a classification implies a statistical precision the system does not
  actually have (this is true today and would remain true even after any
  V5 model improvement, unless a future phase specifically adds
  calibration — e.g. conformal prediction, §V5 doc §5 — with a validated
  guarantee). The five states above are the right level of granularity;
  a raw number is not.
- **No exposing internal evidence-tier names** (`"FILENAME"`, `"DSP"`,
  etc.) as primary UI copy — these are implementation details useful for
  Part 1's correction records and for engineering debugging, not
  user-facing vocabulary. A tooltip/"why" disclosure surface may
  reasonably translate them into plain language ("guessed from the
  filename," "guessed from the audio itself") if a future phase wants an
  explainability affordance, but that is a separate design decision from
  this contract.
- **No AMBIGUOUS state that silently resolves to a guess without saying
  so.** This is precisely the class of bug this phase fixed for Vocal
  Loop/Phrase — before this phase, an ambiguous case produced a
  confident-looking wrong label. The UX contract's AMBIGUOUS state exists
  specifically so a future ambiguous case (in any class, not just Vocal)
  has somewhere honest to go instead of repeating that failure mode
  invisibly.

## 2.4 Interaction with Part 1 (active learning)

Any user action that changes a sample's state to USER-CORRECTED is exactly
the trigger point for a `CorrectionRecord` (§1.3) to be written locally.
The UX contract and the data model are two views of the same event: the
UX contract governs what the user sees and does; Part 1 governs what
(optionally, with consent) happens to that decision afterward. Neither
should be implemented without the other being at least designed (this
document does both, together, for exactly that reason).

## 2.5 Explicitly out of scope for this document

- Visual design (color, iconography, placement, animation) — a future
  EMBER implementation phase's job, not this engineering design's.
- Any specific UI component API or React/JUCE-component code.
- Retraining triggers, dashboards, or aggregate correction-rate metrics
  for the product owner — a separate, future, business-facing tool, not
  designed here.
