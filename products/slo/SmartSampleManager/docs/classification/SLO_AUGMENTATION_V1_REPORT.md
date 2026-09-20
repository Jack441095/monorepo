# SLO Pack-Mastering Augmentation — V1

_Phase 3. Collection-held-out, nearest-centroid incumbent, 3-seed pilot._

## Hypothesis

Collection identity is linearly decodable from the frozen Perch+CLAP embedding
at ~59% against a ~25% baseline, and collection-held-out accuracy sits ~9.7pp
below random CV. The suspicion was that the embedding encodes **how a pack was
mastered** — EQ balance, loudness, compression, saturation, bandwidth, ambience,
format — and that the classifier exploits it as a shortcut.

If so, training-fold augmentation varying those production characteristics
should reduce the shortcut and improve unseen-collection accuracy.

The earlier augmentation experiment tested pitch shift, time stretch and gain.
Those vary the **performance**, not the **production**, so it never tested this.

## Result — the hypothesis is falsified

| policy | accuracy | macro-F1 | cov@95 | Other/none FA | delta |
|---|---|---|---|---|---|
| **none (incumbent)** | **65.52%** ± 0.86 | 56.1 | 28.2% | 37.0% | — |
| spectral | 65.08% ± 1.08 | 55.4 | 27.7% | 38.2% | −0.44 |
| dynamics | 65.59% ± 0.77 | 56.2 | 27.7% | 39.4% | +0.07 |
| space (ambience) | 65.20% ± 1.06 | 55.5 | 27.7% | 38.2% | −0.32 |
| format | 64.76% ± 1.26 | 54.6 | 25.9% | 39.4% | −0.76 |
| combined | 65.78% ± 0.86 | 56.2 | 26.0% | 41.2% | +0.26 |

**No family reaches the +1.5pp pilot threshold, let alone the +2.0pp gate.** Per
the pre-declared ladder, none advances to 8-seed confirmation. Route closed.

Augmentation also makes rejection **worse**: `Other/none` false acceptance rises
from 37.0% to 38–41% under every policy. For a confidence-gated renamer that is
the wrong direction on the metric that matters most.

## Why it failed — the mechanism test

The diagnostic is more informative than the accuracy numbers. If the hypothesis
were right, augmentation should make collection identity **harder** to decode.

| policy | collection decodable at | change |
|---|---|---|
| none | 59.3% | — |
| spectral | 60.0% | +0.7 |
| dynamics | 60.3% | +1.0 |
| space | 59.9% | +0.6 |
| format | 57.3% | **−2.0** |
| combined | 57.6% | −1.7 |

**Varying production style barely moves collection decodability at all.** The
one family that reduces it most (format, −2.0pp) is also the worst performer on
accuracy (−0.76pp) — it is destroying signal, not removing a shortcut.

The augmentations are not weak: the self-check confirms every variant changes
the waveform materially. The audio changed; what the encoder knows about the
collection did not.

**So the vendor shortcut is probably not a mastering shortcut.** More likely
candidates for what makes a collection identifiable:

- **content selection** — which drums a pack actually contains, its sonic palette
- **sample-family structure** — packs render many near-variants of one source
- **instrument and synthesis choices** — the actual devices used

None of those can be removed by re-EQing or re-compressing the audio, because
none of them is a production-style artefact.

## Honest limitations

- Three variants per file with conservative ranges. A more aggressive policy
  might shift more — but the probe says the mechanism is absent, so aggression
  would most likely destroy signal (which is exactly what `format` shows).
- **Stereo operations were excluded by construction, not tested.** Perch and CLAP
  both consume mono and the pipeline downmixes before the encoder, so width,
  narrowing and polarity are guaranteed no-ops. Testing them needs a
  stereo-aware encoder.
- A diagnostic bug was found and fixed mid-experiment: the first collection
  probe scored 99.2% because augmented copies of a file landed in train while
  the original was in test. Grouping the probe by source file removed it. The
  99.2% was leakage in the diagnostic, never a finding.

## Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 pack_augment.py --self-check
python3 aug_experiment.py --extract --family all --workers 6
python3 aug_experiment.py --eval --family all --seeds 3
```
