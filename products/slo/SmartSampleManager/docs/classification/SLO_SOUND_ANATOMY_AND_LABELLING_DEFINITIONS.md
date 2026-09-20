# SLO Sound Anatomy — physical definitions for labelling

_Derived from clustering inside the incoherent classes on encoder embeddings,
then describing each cluster with interpretable physics. Corpus v2, 821 rows._

## Why this exists, and what it is not

Four classes have **negative silhouette** — the average file sits closer to
another class than its own. They name several unrelated sounds:

| class | silhouette |
|---|---|
| Percussion | −0.154 |
| Percussion Loop | −0.114 |
| Foley | −0.102 |
| Synth One-Shot | −0.005 |

**This is not another physics-feature attempt.** Inharmonicity, pitch
trajectory, modulation and provenance were each built as features and each
added **+0.0pp** — the encoders already capture the physics. This uses physics
to *define* classes, not to predict them. The output is a labelling guide.

---

## Percussion → three real subtypes

Best split: **3 clusters, silhouette 0.159** (vs −0.154 for the class as a
whole). The clusters map almost exactly onto the proposed subtypes, and they
are separated by measurements a human can hear.

| | **Shaker / Tambourine** | **Tom** | **Short Percussive Hit** |
|---|---|---|---|
| n | 22 | 15 | 13 |
| attack | 36 ms | 16 ms | **0 ms** |
| decay | 0.13 s | **0.26 s** | **0.06 s** |
| duration | 1.17 s | 1.35 s | **0.38 s** |
| spectral centroid | **3859 Hz** | **1217 Hz** | 2815 Hz |
| energy below 200 Hz | **0.00** | **0.40** | 0.08 |
| harmonicity | 0.39 | **0.49** | **0.22** |
| ZCR | **0.145** | **0.020** | 0.083 |
| examples | Shaker, Mazhar Tambourine | Tom_G, Tom_D | Rimshot, Rim, Perc |

**Discriminating physics:** centroid (d′ 1.70), harmonicity (1.65), decay
(1.60), ZCR (1.55), low-frequency energy (1.19). All strong.

**How to tell them apart by ear:**

- **Tom** — the only one with real low end (40% of energy below 200 Hz) and a
  *pitch*. Longest decay. If you can hum it, it's a Tom.
- **Shaker/Tambourine** — bright and noisy, essentially no low end, high
  zero-crossing rate. Rattles rather than rings.
- **Short Percussive Hit** — instant attack, gone in 60 ms, lowest harmonicity.
  A click or crack rather than a tone.

**Hand Drum did not emerge as a separate cluster** — probably too few examples
in the corpus. Keep the label; revisit when there are enough.

---

## Synth One-Shot → it is three different things, and only one is a "one-shot"

Best split: **3 clusters, silhouette 0.139**. Duration separates them at
**d′ 2.47**, the strongest separation found anywhere in this analysis.

| | **Sustained Tone** | **Slow-Attack Pad** | **Pluck / Stab** |
|---|---|---|---|
| n | 7 | 6 | 6 |
| attack | 128 ms | **432 ms** | **24 ms** |
| decay | 3.57 s | 3.45 s | **0.48 s** |
| sustain | **0.67** | 0.47 | **0.19** |
| duration | 9.26 s | 10.0 s | **1.20 s** |
| harmonicity | **0.98** | 0.82 | 0.81 |
| examples | Saw C3, Square Wave C3 | Supermassive Sine, Organ | Cassette Pluck, NADRISK_SYNTH |

**Only the third cluster is actually a one-shot.** The other two are sustained
tones and pads roughly ten seconds long that happen to have been filed as
one-shots. That is why the class has a silhouette of −0.005.

**Recommended split:** `Synth Pluck` (short, fast attack, low sustain) versus
`Synth Tone/Pad` (sustained, long, high harmonicity). The boundary is
essentially duration and sustain, which is the same envelope axis that made
`Bass Reese` the most coherent class in the corpus (silhouette 0.471).

---

## Percussion Loop and Foley — weak splits, different reasons

**Percussion Loop** (2 clusters, silhouette 0.108): bright/noisy loops
(centroid 4138 Hz, flatness 0.088 — shakers, hats, snare tops) versus
low/tonal loops (centroid 1881 Hz, 22% energy below 200 Hz — congas, kongoma,
mbour). A real distinction but weakly separated; splitting is not yet
justified.

**Foley** (2 clusters, silhouette 0.103): instant-attack short hits (snaps,
reverse rimshots) versus slower 136 ms-attack material. The separation is weak
**and that is the expected result** — Foley is a *provenance* label, not an
acoustic one. Its members have nothing acoustic in common by construction. This
belongs in `source_attributes`, not in a class split.

---

## What this changes

1. **Percussion should be split into Tom / Shaker-Tambourine / Short Percussive
   Hit.** The clusters are clean, the physics is interpretable, and the subtype
   field already exists in the schema.
2. **Synth One-Shot should be split by envelope**, not by instrument. Two of its
   three clusters are not one-shots at all.
3. **Foley should not be split.** Weak clusters are the correct outcome for a
   provenance label; forcing an acoustic split would manufacture structure.
4. **Percussion Loop: leave for now.** Real but weak; revisit with more labels.

## Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 class_anatomy.py --k 3 --workers 6
```
