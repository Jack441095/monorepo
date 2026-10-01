# SLO C++ Remediation — Phase 4 Proposals (owner sign-off required)

**Companion to:** `SLO_CXX_REVIEW_REMEDIATION_RECEIPT_V1.md`
**Branch:** `consolidate-20261001` · **Date:** 2026-10-01

Nothing in this document has been executed. Each item is gated by R8 in
`SLO_CXX_REVIEW_REMEDIATION_PROMPT_V1.md`, either because it crosses a data-format
boundary, changes a threshold, changes real-time ownership, or deletes more than 100
lines in one commit. Recommendations are given so the decisions are easy to make.

---

## 1. Sort journal: CSV → JSONL

**Why.** The CSV journal is defended now by rejecting control characters on write and
validating row shape on read (`SampleManagerEngine.cpp:195-216`, `7392-7408`), and the
injection is closed — Test 8 proves a filename can no longer forge a row. But the format
is still a line-oriented one that a filename can influence, and the defence depends on
getting the validation exactly right rather than on the format making it impossible.

`CorrectionLog.h` already writes JSONL correctly, including `jsonEscape` for `"`, `\`,
control characters and everything below 0x20. The sort journal should be the same shape.

**Blast radius.** Every `.slo_sort_journal_*.csv` already on a user's disk becomes
unreadable to the new parser. Journals are transient — one per sort, and renamed to
`.undone` after use — so the practical loss is the ability to undo the sort that
produced a still-open journal. That is small, but it is not zero, and it is the user's
audio.

**Recommendation.** Do it, and read both: try the `.jsonl` name first, fall back to
`.csv` with the current strict validator. That removes the downside entirely at the cost
of keeping ~40 lines of the old parser, which can then be deleted once the fallback has
shipped for a release.

**Effort.** ~2 h including the round-trip test. Needs a test that a journal written by
the new writer parses back through the new reader and that a legacy `.csv` still undoes.

---

## 2. Move `transportSource` ownership off the audio thread

**Why.** `startPreparedPlayback` (`PluginProcessor.cpp:250-273`) runs inside
`processBlock` and, per the review, performs roughly five allocations and two lock
acquisitions per audition start: `setSource` with a resampling rate constructs a
`ResamplingAudioSource`, then JUCE's `prepareToPlay` does `buffer.setSize` plus three
`calloc`s and `flushBuffers` (a `CriticalSection`), then `ScopedLock callbackLock` is
taken on the way out. The comment at `:253` claims realtime safety. It is not.

**What P0-3 already removed.** The deterministic 1.4 s stall is gone — `stop()` is no
longer called from the audio thread at all. What remains is measured, not hypothetical:
`test_rt_deadline_stress` reports 38 of 2000 callbacks carrying allocations, worst case
4 in one callback, and an intermittent 2–86 ms outlier in roughly 1 callback in 1000.
The outlier population predates this work — it was present at `df37fe21` before P1-8.

**Why it is gated.** The audio thread's only job right now is deciding *whether* a beat
boundary was crossed; the actual transport calls happen because of that decision. Moving
them means moving the beat decision to the message thread, which needs either a lock
(the thing being avoided) or a second thread. JUCE's own `callbackLock` already
serialises `setSource` against `getNextAudioBlock`, and the retire ring from P1-8
already removed the `readerSource` lifetime race that made an earlier version of this
unsafe — so the two obstacles the original design cited are gone. It still needs a real
host soak, not the stress binary: the stress binary has no host transport, so it cannot
exercise the beat-quantisation path this would touch.

**Recommendation.** Attempt it, but only with a host soak scheduled, and keep the current
allocation instrumentation in `test_rt_deadline_stress` as the before/after measure. If
the soak cannot be scheduled, leave it — the deterministic failure is already fixed and
this is a latency-quality improvement, not a correctness one.

**Effort.** ~4 h plus a soak window.

---

## 3. Bass timbre and hi-hat: present the confidence, do not gate on it

**This proposal replaces a threshold gate, because the threshold was already measured
and rejected.**

The review asks for a confidence floor on the bass/hi-hat secondary tag — something like
`if (bassTimbre.label != "" && bassTimbre.confidence >= 0.55f)`. The separation that
gate would need does not exist, and the project's own calibration says so.
`BASS_TIMBRE_TAG_V1_REPORT.md:15`:

> per-sample confidence margin (top1 vs top2 centroid similarity) does **not** cleanly
> separate correct from wrong predictions at this sample size — the lowest-margin wrong
> prediction (0.0019) and a correct prediction with similarly low margin (0.0024) overlap

`HIHAT_TYPE_TAG_V1_REPORT.md:11` gives the hi-hat version as a number: mean intra-class
similarity **0.939** against inter-class **0.930**, a gap of 0.009. Any floor placed near
that band throws away correct predictions at the same rate as wrong ones. A 0.55 floor
would be worse than useless — it would sit far below the whole distribution and tag
everything, which is the current behaviour, while looking like a gate.

**What is actually wrong.** `SampleManagerEngine.cpp:409` and `:415` commit the label
silently. The classifiers were designed to "expose a score and let downstream callers/UI
decide how to present it" — the same posture as `tagConfidence` — and the downstream
decided nothing. So a `"808"` tag the model is nearly indifferent about reaches the user's
library indistinguishable from a confident one.

**Options, in the order I would try them.**

1. **Present it, change nothing about tagging.** Show the margin in the inspector or as
   part of the badge, so a user who cares can see it is a weak call. This is what the
   classifier contract asks for, costs no accuracy, and is reversible.
2. **Tag, but record the score on the sample** so a later pass can revisit low-confidence
   tags without re-running inference. A schema addition, so it needs R8.
3. **Widen the corpus.** The Reese class is 24 samples and the report already flags it as
   thin; the hi-hat gap of 0.009 is the same problem. More examples from more vendors
   would sharpen the centroids and might make a gate viable — but that is a data task, and
   until it is done no threshold is defensible.
4. **Drop the tag entirely.** Honest, and costs a feature that is right 92% of the time.

**Recommendation.** Option 1 now, option 3 as ongoing work, and explicitly *not* a
threshold. Whichever is chosen, the number belongs in the header next to the accuracy
figure so the next reader can see which is which — that confusion is what produced this
proposal in the first place.

**Effort.** Option 1 is a UI change, ~3 h. Option 3 is unbounded and is a data-collection
project.

## 4. `ctest` versus the six `ssm_qual_*` groups

**Where this stands.** R1 is resolved: `enable_testing()` and 56 `add_test()`
registrations exist, and `ctest` runs the suite in ~90 s. The `ssm_qual_*` targets
remain `add_custom_target(... DEPENDS <executables>)`, so they still only build.

**The decision.** Either they stay build-only, in which case their names are actively
misleading — `ssm_qual_classification` reads like a gate but proves nothing about
pass/fail, and that is the exact confusion this document's §7.1 baseline had to correct.
Or they become run gates over the matching `ctest` label, which requires labelling the
registrations and giving each group a real pass condition.

**Recommendation.** Convert them, but rename as you do: `ssm_build_classification` for
the current behaviour and `ssm_qual_classification` for a `ctest -L` run. The risk of
leaving them is that a future reader trusts a green build as a green suite — which is
what the review found in the audit docs.

**Effort.** ~1 h. One decision, no code risk.

---

## 5. `TestLicensing` needs a live server, so it is not registered

**Where this stands.** P1-30 is fixed and this is no longer a data-safety question: the
test now redirects the licence file to a `juce::Uuid()` temp directory and *asserts the
real file is byte-identical afterwards*, so running it cannot cost a user their licence.
`LicenseManager::setAppDataDirOverrideForTesting` is the hook.

It is still not in `ctest`, because it needs `uvicorn` on port 8420 and a real key from
`POST /v1/admin/licenses`, and `runURLPolicyTests` is the only mode that runs standalone.

**The decision.** Either stand up the server in CI and register it, or mark the binary
as an explicit manual soak. The status quo — build-only, enrolled in `ssm_qual_ui`, and
therefore looking like a gate — is the worst of the three.

**Recommendation.** Mark it manual first, since that is honest and takes ten minutes.
Stand it up in CI only if licensing becomes a release blocker, because it adds a network
dependency to the suite that nothing else needs.

**Effort.** 10 minutes to label it; ~2 h to wire a server into CI.

---

## 6. `getTailLengthSeconds()` returns 0.0

**Why it matters.** `PluginProcessor.h:26` returns 0 while `processBlock` is actively
writing audio. If a host consults it, audition playback could be truncated to nothing when
the transport is stopped.

**Status: unverified.** I could not confirm or refute it without a host. The fix, if it
is needed, is to report the remaining length of the prepared reader — which is available
on the message thread but not safely readable from the host's query, so the honest answer
may be "return the source file's duration".

**Recommendation.** Soak it: audition a long sample in Ableton with the host transport
stopped and listen for truncation. If it truncates, fix it; if not, add a comment saying it
was checked and is harmless, so the next reader does not repeat the investigation. Do not
change it speculatively — a wrong non-zero tail length makes hosts hold plugin instances
open longer, which is its own problem.

**Effort.** 30 min to soak, 15 min to fix.

---

## Also awaiting sign-off: 764 lines of confirmed-dead code

R8 caps a single deletion at 100 lines, and every one of these is over it, so they are
proposals rather than commits. Grep evidence and line counts are in the receipt's §7.6a.

| Item | Lines | Evidence |
|---|---|---|
| `Source/PhaseCorrelationMeter.h` | 171 | **zero** references anywhere in `Source/` |
| `Source/PhysicalSynthesizer.h` | 268 | only `test_physical_acoustics_main.cpp` |
| `Source/AudioSimilarity.h` | 165 | only its test and `AudioEvidence.h` |
| `Source/AudioEvidence.h` | 160 | only its test and `AudioSimilarity.h` |
| `ResultsPanel` aspect-weight strip | ~120 | `setAspectWeightsChangedCallback` is never called; no production code writes `row.aspects`, so both render branches are unreachable |
| `PhysicalAcoustics::evaluateMixCollision` | 71 | only `test_physical_acoustics_main.cpp` |

**Recommendation.** Delete them one commit each so no single diff crosses the 100-line
line, and delete `test_audio_similarity_main` / `test_audio_evidence_main` with their
headers. That removes ~760 shipped lines that no product path reaches and that the next
reviewer would otherwise have to re-derive. `PhaseCorrelationMeter.h` is the clearest
case: it has never been constructed by anything.

**One caveat, deliberately not deleted.** The fusion-v2 and loop-v2 feature flags
(`MlOverrideGate.h:37`, `AbletonTaxonomy.h:27`) look identical — setters called only by
their own test binaries, so permanently `false` in production. But the surrounding comment
states the gates are values "the owner must pass before V2 ships", and
`test_fusion_v2_main` / `test_loop_v2_main` are real coverage of that parked path.
Deleting them destroys staged work, not dead code. The related hazard is worth recording
though: `kTaxonomyVersion` does not change when a flag is toggled, so the day someone
wires a UI toggle, cached rows classified under the old setting will silently disagree
with freshly classified ones. Either bump the version when behaviour can change, or make
the flags `constexpr` and delete the toggles.

---

## Summary

| # | Proposal | Gate | Effort | My recommendation |
|---|---|---|---|---|
| 1 | CSV → JSONL journal | R8 (format) | 2 h | Do, with a read-both fallback |
| 2 | `transportSource` off the audio thread | R8 (RT ownership) | 4 h + soak | Attempt only with a soak scheduled |
| 3 | Bass/hi-hat confidence | R8 (threshold) | 3 h for option 1 | Present the score; the gate was measured and rejected |
| 4 | `ctest` vs `ssm_qual_*` | none | 1 h | Convert and rename |
| 5 | `TestLicensing` registration | none | 10 min | Mark manual now |
| 6 | `getTailLengthSeconds()` | needs a host | 30 min | Soak, then fix or document |
| — | 764 lines of dead code | R8 (>100 lines) | 1 h | Delete, one commit each |
