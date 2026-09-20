# SLO Vocal Loop Cross-Vendor Verification V1

**Generated for:** SLO Master Plan V2, Phase 7 (B-008)
**Purpose:** the existing Vocal Loop/Phrase disambiguation fix (commit `e85feec`, `AbletonTaxonomy::classify()`) was validated on exactly one vendor (KSHMR: 1.9%→7.5% full-corpus recall). Its own report flagged this explicitly: "real-world effectiveness against other vendors' naming conventions is unverified." This report closes that gap.

## Headline result

**Historical pre-remediation baseline: 0.0% Vocal Loop recall cross-vendor (0/22), 100% Vocal Phrase recall (14/14).**

36 real, cross-vendor (Loaded Samples, Bright Lights, Minimal Audio — none KSHMR), independently-labeled samples. Ground truth methodology: files with an adjacent BPM+musical-key filename suffix (the same signal the fix looks for, matching the original report's own ground-truth methodology so results are comparable) or an explicit "loop" word = Vocal Loop; files under 2.0s duration (independently verified via `afinfo`, not a filename-derived signal) or from a vendor-asserted "Oneshots" folder = Vocal Phrase. 13 additional Lo-Fi Memphis files were genuinely ambiguous under this methodology and excluded rather than force-labeled.

**The existing fix does not generalize.** Cross-vendor recall (0%) is dramatically worse than even the modest single-vendor number (7.5% full-corpus / 11.5% holdout).

## Two distinct, well-evidenced root causes

1. **The fix's signal is narrower than the naming conventions it needs to cover.** `hasAdjacentTempoKeyPair()` requires BOTH a plausible BPM token AND an adjacent musical-key token. 21 of 22 Loaded Samples "VOCALS" files carry a BPM tag (`[72 BPM]`) but no key — a very common convention (tempo-only tagging) that the fix's narrow signal simply doesn't recognize. These fall through to the DSP-only `detectLoopVsOneShot()` heuristic (duration>1.5s AND decay-ratio>0.6), which also gets every one of them wrong — plausibly because rap/hip-hop vocal hooks have percussive, staccato delivery rather than the sustained/decaying envelope the DSP heuristic's decay-ratio threshold was tuned against (an assumption likely inherited from melodic/sung loop content, not represented in this vendor's catalog).
2. **A separate, more basic gap**: the Bright Lights sample uses the industry-standard abbreviation "BVs" (Backing Vocals) in its filename (`BL_C#m_120_BVs_loop_GirlGroup_HighHarm.wav`) — explicit "loop" word AND full BPM+key adjacency present. But "bv"/"bvs" isn't in the coarse category-detection keyword list (`SampleManagerEngine.cpp`'s `matchType` lambda, Vocal bucket), so the file never gets category-tagged "Vocal" in the first place — it falls through to the generic "Loop" bucket and gets classified `Music Loop` instead of anything Vocal-related at all. This is upstream of the Vocal Loop/Phrase fix entirely; the fix never gets a chance to run.

## Decision: suppress the claim, don't rush a fix

Per this plan's own operating discipline (don't invent a new heuristic under time pressure just to move a number), and because the root causes above need real design work (broadening the signal, and separately deciding whether/how to expand the DSP fallback's assumptions for percussive vocal content) rather than a one-line patch:

**Recommendation: treat "Vocal Loop" classification as unreliable in any user-facing accuracy claim until a dedicated remediation phase addresses the signal-narrowness and DSP-fallback issues above.** Checked: no current marketing/website copy makes a Vocal-Loop-specific accuracy claim, so there is nothing live to retract — this is guidance for future copy, not an active walk-back.

**Separately flagged, not fixed here** (adjacent, not this blocker's scope): the "BVs" abbreviation gap is a narrow, well-understood, low-risk addition to an existing keyword list (unlike the Vocal Loop signal itself, which needs real design work) — a good candidate for a small, dedicated future fix, but making it now would be scope creep beyond what this measurement task set out to do.

## Update — 2026-08-28 (SLO Master Plan V3): the "BVs" gap is now fixed

The narrow, low-risk fix flagged above as a future candidate was implemented: `"bv"`/`"bvs"` added to the coarse category-detection Vocal keyword bucket (`SampleManagerEngine.cpp`'s `matchType` lambda). Re-ran the same cross-vendor scan:

**Vocal Loop recall: 0% → 4.5% (1/22).** The Bright Lights file (`BL_C#m_120_BVs_loop_GirlGroup_HighHarm.wav`) now correctly resolves to `Vocals / Vocal Loop` via FILENAME evidence (previously misrouted to `Music Loop` before the Vocal-specific fix could even run). Vocal Phrase recall unaffected (100%, no regression) — verified via a full `ssm_qual_full` rebuild before merge.

**This does not change the overall conclusion.** The dominant cause (21 of 22 real-world misses — Loaded Samples' tempo-only, no-key filename convention never triggering `hasAdjacentTempoKeyPair()`) is untouched, and remains a genuine design-effort item, not something fixed here. The claim-suppression recommendation above stands: Vocal Loop classification is still unreliable enough that no user-facing accuracy claim should be made about it.

## Update — 2026-09-14 (tempo-marker review signal)

The tempo-only convention identified above is now represented as a separate,
Vocal-scoped `hasTempoMarker` signal: a plausible BPM token adjacent to the
literal `bpm` marker (for example `Vocal_72_BPM`) is treated as loop evidence
without being mistaken for a musical key. It cannot affect Bass, Synth, Drum
or other subcategory decisions, and it remains subject to the existing
review/policy gate. Taxonomy version 4 invalidates cached taxonomy rows so the
rule is applied consistently after rescan. Cross-vendor precision and recall
still require a fresh owner-reviewed evaluation; this change is not an
automatic-promotion claim.

## Update — 2026-09-14 (measured Loaded Samples slice)

After rebuilding the native benchmark with the punctuation-normalized parser,
the two independently labeled Loaded Samples `VOCALS` rows carrying tempo-only
suffixes (`Rollin Deep - With the Click [72 BPM]` and `Wer Don't Just Rap [72 BPM]`)
both resolve to `Vocals / Vocal Loop` (2/2). The first also exercises the
folder-over-generic-"click" precedence fix. The acoustic head still predicts
`Vocal Phrase` for both, so the explicit filename/folder evidence is retained
as the final heuristic label and the ML result remains diagnostic-only.

This is a descriptive two-row slice, not a universal-accuracy claim or a new
automatic-rename tier; owner-reviewed calibration is still required before any
promotion decision.

## Scope limitations

- 36 samples, 3 vendors — real but small. 13 additional Lo-Fi Memphis samples were excluded as genuinely ambiguous rather than force-labeled; a larger, more deliberately-curated cross-vendor set (including vendors with sung/melodic vocal loops, not just rap vocal hooks) would strengthen this further.
- Ground truth for the 22 "Loop" samples reuses the same BPM+key-suffix signal the fix itself tests for (matching the original report's methodology for comparability) — this is a fair test of whether the *convention* generalizes, not an independent verification that every individual file's audio content is actually loop-like.
