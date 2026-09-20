# LAYER ALIGNMENT V2 BACKLOG
### Items discovered during Real-Audio Validation V1 — engine FROZEN, none patched

## B1. NaN-confidence propagation (engine, low severity)
On fully degenerate input (NaN samples) the action is safely NO_ACTION but
`confidence` is NaN and would leak into the product JSON. Fix in V2: coerce
non-finite feature aggregates to abstain-with-zero-confidence at the
classify boundary. Product-layer sanitisation is acceptable as an interim
guard.

## B2. Controlled-case coverage policy (product research, medium)
Small-offset self-perturbed transients gate to NO_ACTION because identity
already sums near-optimally (<0.25 dB predicted gain). Estimation remains
exact. If a "micro-nudge" tier of suggestions is wanted, it needs:
its own listening evidence, a separate suggestion class in the output
contract, and UI treatment distinct from meaningful alignments. Not a
threshold change.

## B3. Uncontested benchmark (ops)
All current timings are contaminated (host load 85–212 observed). Run
`eval/bench.py` in a load<4 window on licensed-audio-sized pairs before any
performance claim. The bench refuses to certify otherwise by design.

## B4. Reviewer panel (process)
Single-reviewer validation is acceptable but must be labelled; if more
engineers are available at review time, add inter-rater agreement reporting
(already supported by the vote schema).

## B5. Format coverage (harness)
Loader supports WAV PCM16/24/float32 only. FLAC/AIFF import requires either
owner-side conversion or adding `soundfile` — decision deferred to keep the
qualification environment dependency-frozen.

## B6. Domain-specific reporting polish (product)
If the domain-limited outcome materialises (transient drum/bass PASS,
tonal NOT QUALIFIED), surface per-domain verdicts in the product UI rather
than one global score.

## B7. Bin-level spectral overlap under-measures musical overlap (engine, from real run)
63/109 natural pairs abstained via the spectral-overlap guard because
sparse-harmonic sources (kick partials vs dense bass harmonics) barely
intersect bin-by-bin. V2: band-level overlap metric (energy per musical
band, not per bin) and/or onset-gated transient-window analysis for
rhythmic pairs. Highest-value fix: directly drives actionable coverage.

## B8. Long-window musical ambiguity (engine, expected but now quantified)
25 natural abstentions are genuine periodic ambiguity at 10 s windows.
V2 candidate: adaptive windowing (transient-anchored short windows for
drum-domain pairs), reported as a distinct analysis mode with its own
validation.

## B9. Distorted one-shot refusal (engine)
Real-material tanh-distorted copies push correlation into refusal more
often than synthetic fixtures predicted (safe, coverage-costly). V2:
distortion-tolerant weighting; requires its own listening evidence.

## B12. Multi-objective gate hardening (engine, from real run)
LR4-recombined healthy pairs received ALIGN suggestions because weighted
low-band gain improved while other bands degraded. V2: add per-band
non-degradation conditions (e.g., no active band may lose more than X dB)
to fast_search acceptance and to recommend() gating.

## B10. Uncontested benchmark still outstanding (ops)
Host load never dropped below ~46 during the sprint. Run eval/bench.py in
a quiet window, or better, measure the native C++ path once integrated.

## B11. Review pack scaling
If natural ALIGN coverage rises post-B7/B8, regenerate the stratified pack
to reach the original ~60-primary-judgement target.
