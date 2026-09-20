# SLO Multi-Window Extraction Report V1

## Design

Handcrafted DSP features have failed twice in this project (+0.0pp both times),
because they were whole-file descriptors of properties the encoders already
capture. This layer is a different bet: the remaining errors are concentrated in
**temporal/form** confusions, and a whole-file average cannot express form.
"Loud at the start and silent after" is a one-shot; "equally busy in every
third" is a loop. That contrast is the signal global pooling destroys.

**55 features** = 5 windows × 9 descriptors + 10 cross-window contrasts.

| window | span | purpose |
|---|---|---|
| full | whole file (≤12s) | reference |
| attack | 0–120 ms | transient identity |
| early | 0–1 s | hit plus early decay |
| mid | middle third | steady state |
| tail | last 25% | decay character |

Per window: transient strength, decay length, low-end energy (<200 Hz),
HF density (>6 kHz), spectral centroid, spectral flux, onset rate, sustained
tonal energy, noise-vs-tonal (flatness).

**Cross-window contrasts** — the actual point of the layer: early-vs-tail energy
ratio (≈0 one-shot, ≈1 loop), onset-rate coefficient of variation across thirds
(low = steady = loop), rhythmic autocorrelation peak and lag, a combined
repetition score, **stereo width and correlation measured before downmix**
(the encoders are mono, so this is the only place width is observable at all),
duration, crest factor and silence fraction.

## Result

| metric | audio-only | multi-window | delta |
|---|---|---|---|
| accuracy | 69.69% | 69.57% | −0.12 |
| macro-F1 | 65.14 | 64.92 | −0.22 |
| **coverage @90%** | **31.4%** | **32.5%** | **+1.1pp** |
| coverage @85% | 67.6% (fusion) | 68.8% (mw-fusion) | +1.2pp |
| junk false-accept | 20.2% | 19.3% | −0.9pp |

**Accuracy is flat; coverage improves.** That is the correct shape for this
work — the features do not identify sounds better, they make the *confidence*
better ordered, which is what a gated renamer needs.

## What did not work

`mw-form + audio-family` (multi-window supplying temporal form, encoder
supplying family) scored 68.60% / F1 62.48 — **worse than either component**.
Form is already 88.8% accurate from the encoder alone, so there was little for a
dedicated form model to add, and the hard routing added failure modes.

## Encoder multi-window (crops through Perch/CLAP)

Extraction was still in progress at time of writing (~150 of 762 files). The DSP
layer is complete and is what these numbers measure. The encoder-crop arm
remains **untested** and is the open half of this route.
