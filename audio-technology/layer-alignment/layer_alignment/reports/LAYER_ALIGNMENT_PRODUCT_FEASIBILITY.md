# LAYER ALIGNMENT PRODUCT FEASIBILITY
### NITE DSP Intelligent Layer Alignment R&D — Candidate Product #2

## Verdict summary

The core hypothesis survives falsification testing on every measurable axis
except one (see Risks). Recommendation quality, abstention and no-action
intelligence all cleared their bars; differentiation is real and defensible.

---

## What the evidence supports

1. **Estimation core works.** Delay recovery essentially exact on broadband
   material (within-2 samples ≈ 94–100% by kind); fractional accuracy
   0.04-sample MAE; polarity 89–100% depending on processing severity;
   plugin-latency detection to 0.3-sample MAE where bulk delay exists.
2. **No-action intelligence works — the differentiator.** 230/230 healthy
   controls left alone (FPR 0.0%); intentional layering (disjoint kick
   stacks) 100% NO_ACTION across 112 configurations including deliberate
   offsets; snare composites routed to AMBIGUOUS abstention instead of
   guessed; octave-tone traps abstain.
3. **Benefit delivery is measurable.** Reinforcing-layer stacks:
   median 1.8-sample recommendation error, +11.4 dB summed low-band energy,
   +11.2 dB sub-band interaction improvement post-alignment.
4. **Explanation model is grounded.** Structured output (relationship /
   primary interaction / estimated offset in samples+ms / polarity / band
   offsets / confidence / suggestion / trade-off) generated directly from
   measurements — no LLM in the measurement path (§23 honoured).
5. **Frequency-dependent honesty.** Bandwise divergence detection triggers
   PARTIAL_SUGGESTION output (per-band offsets) instead of a single false
   number under dispersion — a behaviour none of the surveyed tool
   categories exhibit.

## Workflow prototype (§32)

Drag/route Layer A + B → Analyse (event-driven) → relationship +
band-interaction view → ranked suggestions with confidence and trade-offs →
audition (apply candidate non-destructively) → user decides.
Automatic correction explicitly NOT assumed; every suggestion carries its
predicted effect and an undo-safe audition path.

## Differentiation vs market categories (§31)

| category | gap NITE DSP fills |
|---|---|
| correlation meters | show a number; no cause, no bandwise truth, no abstention |
| auto-phase tools | typically silent global correction; measured here that global delay can *hurt* (min-phase/mic-TF/LR4 cases) |
| manual sample-delay utilities | no detection, no verification, no confidence |
| multi-track phase tools | per-pair binary flip/delay; no benefit quantification, no no-action intelligence |

NITE DSP combination that none provide together: explanation-first output,
bandwise interaction reporting, calibrated confidence + explicit abstention,
verified NO ACTION as a first-class outcome, benefit quantification before
the user commits an ear.

## Visualisation design (§24 — designed, deliberately not built)

Producer-first surfaces, in priority order:

1. **Layer overlay** — A and B waveforms on one lane with a ghost of B
   shifted by the suggested offset (before/after preview is the product).
2. **Transient markers** — onset ticks per layer; misalignment visible
   without reading numbers.
3. **Band interaction bar** — six vertical segments (sub…high), colour from
   measured interaction dB (cancellation red → neutral grey → reinforcement
   green). Replaces "correlation number" entirely.
4. **Suggestion card** — plain language: "Layer B is ~14 samples late.
   Audition advancing it 0.29 ms." + confidence + trade-off line.
5. On-demand expert view: phase-vs-frequency plot + per-band offsets
   (PARTIAL_SUGGESTION cases land here).

Explicitly rejected: real-time correlation meters, radar/goniometer plots,
multi-pane dashboards. The analysis is an event, not a screensaver.

## Multi-layer future (§33)

Pairwise engine generalises: N layers → reference selection + spanning-tree
of pairwise analyses; each edge reuses the proven two-layer core. Evidence
gate respected: nothing beyond pairwise was built until two-layer results
were compelling — they now are.

## Risks

1. **Synthetic→real transfer unproven** (biggest risk). Healthy-control FPR
   of 0.0% is on synthetic decorrelation; real-world unrelated material is
   messier. Mitigation: CONTINUE-R&D validation stage on licensed material
   before product commitment (owner/customer audio remains untouched by R&D).
2. Tonal/ringing layers remain information-limited (abstention is correct
   but users may perceive "it did nothing").
3. UI must resist science-dashboard clutter (§24): recommended surface is
   overlay + transient markers + band-interaction bar + one confidence
   element; phase-vs-frequency plot on demand only.
4. Performance numbers captured under extreme machine contention; healthy-
   hardware bench still required before alpha.

## Cost to build prototype

Small: kernels are validated, C++ portability proven by parity spike,
workflow is conventional plugin plumbing around ~20 FFT-class operations
per analysis event. Estimated scope for a JUCE utility prototype: focused
engineering effort, no research risk remaining at two-layer scope.
