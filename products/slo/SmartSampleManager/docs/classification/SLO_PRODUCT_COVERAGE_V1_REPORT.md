# SLO Product Coverage — V1

_The end-to-end renamer, collection-held-out. Ground Truth V1, 764 files,
70 collections, 6 seeds × 5 folds._

## What this fixes

Every accuracy figure in this programme was **audio-only**. Production does not
work that way — it fuses evidence, trusting the filename where the filename is
trustworthy and consulting audio only where it is not. Reporting the audio
component as if it were the product both understated it and hid whether the
fusion loses precision where the two sources meet.

This measures the thing a user experiences: **given a file, does SLO rename it,
and is that rename correct?**

Both gates are fitted on **training collections only** — per-class filename
precision and the audio confidence threshold alike — and applied unchanged to
held-out collections. The audio gate is calibrated 3pp above target to absorb
the measured domain-shift shortfall.

## Result

| precision target | best arm that **meets** it | coverage (before → after detector fix) |
|---|---|---|
| 85% | fusion | 67.6% → **66.4%** |
| 90% | **fusion** (was audio-only) | 31.1% → **42.0%** |
| 95% | audio-only | **14.8%** |

**The detector fix moved the 90% operating point from 31.1% to 42.0% coverage**
by lifting fusion precision from 89.2% (missing the target) to 90.3% (meeting
it). Three token rules were removed: `hit`→Impact (38.5% precision, fires on any
percussive hit), bare `tops`→Top Loop (collided with Hi-Hat Loop), and bare
`chord(s)`→Chord Loop (0.0% precision, usually a synth sound).

A fifth arm, **family+form** — filename for the function family, audio for the
temporal form, since that is where each source is strong — is the most *precise*
fusion (92.0–96.0%) but not the highest coverage. It is the right shape for a
conservative mode: it is the only fusion arm that meets a 95% target at all.

Full grid:

| target | arm | coverage | precision | meets |
|---|---|---|---|---|
| 0.80 | filename-only | 48.2% | 90.1% | ✅ |
| 0.80 | audio-only | 65.5% | 82.9% | ✅ |
| 0.80 | **fusion** | **77.8%** | 86.0% | ✅ |
| 0.85 | **fusion** | **67.6%** | 88.4% | ✅ |
| 0.90 | filename-only | 18.7% | 90.0% | ✗ (−0.0) |
| 0.90 | **audio-only** | **31.1%** | 90.1% | ✅ |
| 0.90 | fusion | 42.8% | 89.2% | ✗ (−0.8) |
| 0.95 | filename-only | 3.6% | 94.6% | ✗ (−0.4) |
| 0.95 | **audio-only** | **14.8%** | 95.8% | ✅ |
| 0.95 | fusion | 17.7% | 94.0% | ✗ (−1.0) |

## Three findings

**1. Filename evidence is far less trustworthy than the architecture assumes.**
The evidence hierarchy (`EMBEDDED_METADATA > FILENAME > FOLDER > DSP`) treats
filenames as the reliable path. Measured against by-ear ground truth on unseen
collections, the filename detector fires on 64.3% of files at **65.3% overall
precision**, and even its best classes top out around 90% (Hi-Hat 92.7%,
Clap 91.3%, Snare 90.0%). Some fire and are almost always wrong — the generic
`Loop` token fires 62 times at **0.0% precision**.

At a 95% product target almost no class clears the trust bar, which is why
filename-only coverage collapses to 3.6%.

**2. Fusion buys coverage and costs precision.** At 90% and 95% targets fusion
has the highest coverage of any arm — and misses the target by 0.8–1.0pp,
because the filename component drags precision down. Requiring the two sources
to agree does not rescue it.

**3. The shippable operating point depends entirely on the promise.**
At 85% precision the product covers **two thirds of a library**. At 95% it
covers one seventh. That is a product decision, not a technical one.

## Recommendation

**Ship at 85% with fusion (67.6% coverage), not 95% with audio-only (14.8%).**

A renamer that correctly names two thirds of a library and abstains on the rest
is useful. One that names one file in seven is not, however precise it is. Users
correct mistakes; they cannot correct silence.

If a high-precision mode is wanted, offer it as a **mode**, not the default —
"conservative: names ~15% of files, ~1 error in 20".

## What would move it

- **More labels from unseen collections.** The only lever that has worked:
  +3.29pp accuracy and −17.9pp false acceptance per 500 labels, worth ~2× when
  drawn broadly.
- **Fixing the filename detector.** `Loop` at 0.0% precision and `Impact` at
  38.5% are removable defects, not modelling problems. Cheap.
- **Not** more method search. Nine routes have failed against this incumbent.

## Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 product_coverage.py --seeds 6 --target 0.95
python3 product_coverage.py --seeds 6 --target 0.85
```
