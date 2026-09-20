# SLO Operating Point Evaluation V1

_Collection-held-out. Gates fitted on training collections only and applied
unchanged to unseen ones. 762 files, 70 collections._

## Headline: the stated 90% / 41% operating point does not hold

The brief records "90% precision / 41% coverage (fusion)". Measured across three
seed counts, **fusion misses 90% at every one of them**:

| seeds | fusion coverage | fusion precision | meets 90%? |
|---|---|---|---|
| 4 | 43.2% | 89.8% | ✗ −0.2pp |
| 8 | 44.2% | 89.3% | ✗ −0.7pp |
| 12 | 43.7% | 89.6% | ✗ −0.4pp |

It fails consistently and by a small margin, which is the worst kind of failure:
it looks like success at low seed counts and is not. **41% coverage at 90%
precision was never real.**

## What actually holds at 90%

| arm | coverage | precision | stable? |
|---|---|---|---|
| **multi-window audio** | **32.5%** | **91.0%** | ✅ meets at 4/8/12 seeds |
| audio-only | 31.4% | 90.7% | ✅ meets at 4/8/12 seeds |
| family+form | 24.7% | 91.9% | ✅ |
| fusion | 44.2% | 89.3% | ✗ never meets |

**The honest 90% operating point is ~32% coverage, not 41%.**

## Full grid (8 seeds)

| target | arm | coverage | precision | meets |
|---|---|---|---|---|
| 85% | **mw-fusion** | **68.8%** | 87.6% | ✅ |
| 85% | fusion | 67.6% | 87.5% | ✅ |
| 85% | mw-audio | 52.5% | 86.1% | ✅ |
| 90% | **mw-audio** | **32.5%** | 91.0% | ✅ |
| 90% | audio-only | 31.4% | 90.7% | ✅ |
| 90% | fusion | 44.2% | 89.3% | ✗ |
| 95% | **audio-only** | **14.8%** | 95.1% | ⚠ marginal |
| 95% | family+form | 5.3% | 95.4% | ✅ |
| 95% | mw-audio | 16.5% | 94.8% | ✗ |

## Is 95% supported?

**Marginally, and not dependably.** `audio-only` delivers 95.1% against a 95.0%
requirement — a 0.1pp margin, which is inside seed noise. `family+form` clears
it more comfortably (95.4%) but covers only 5.3%.

**Recommendation: do not advertise 95%.** A 0.1pp margin on 70 collections will
not survive contact with a library we have not seen.

## Did multi-window improve the primary target?

**Yes, modestly and consistently.**

| target | before | after (multi-window) | delta |
|---|---|---|---|
| 85% | 67.6% | **68.8%** | +1.2pp |
| **90%** | **31.4%** | **32.5%** | **+1.1pp** |
| 95% | 14.8% | 16.5% ✗ | coverage up, target missed |

At 90% the improvement is real and stable across seed counts. It is **not** the
+9pp the brief hoped for.

## Honest product promise

> SLO safely identifies the sounds it understands at ~90% precision, covers
> roughly **a third** of a real library, and leaves the rest for review.

If a two-thirds-coverage promise is wanted, the honest precision is **85%**
(mw-fusion, 68.8%).
