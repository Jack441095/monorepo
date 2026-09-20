# SLO loop/form definition research — V1

Date: 2026-09-12

## The useful definition

A **loop** is a finite piece of audio intended to repeat as a musical unit.
The defining property is not file duration; it is repeatable temporal
organisation. A loop may be one bar, four bars, or longer, and it may contain
one or many sound sources.

A **drum loop** is therefore:

> A repeatable rhythmic pattern containing multiple percussive drum events or
> parts over a time span, normally with a discernible pulse or meter.

“Multiple drums playing at once over a period of time” is close, but “at once”
is too strict: kick, snare, and hat events can occur at different times. The
important combination is **multiple percussive events + rhythmic organisation
+ intended repetition**.

## Proposed SLO operational definitions

These are review rules, not yet production gates.

| label | operational meaning |
|---|---|
| Drum One-Shot | One principal percussive event with no repeated rhythmic pattern. |
| Drum Loop | A repeating or repeatable pattern with at least two distinct drum/percussion event types or parts, multiple onsets, and evidence of pulse/periodicity. |
| Percussion Loop | A repeating multi-event percussion pattern whose content is mainly hand, metallic, shaker, Foley-percussion, or other non-kit percussion; do not use this merely because the filename contains `perc`. |
| Top Loop / Hi-Hat Loop | A repeating pattern dominated by upper-frequency hats/cymbals/shakers and lacking a substantial kick/bass role. |
| Drum Fill | A short multi-hit transition or variation; it may be rhythmic but is not intended to repeat as the main groove. |
| Sustained / Pad / Atmosphere | Tonal or noisy material whose identity is continuous sustain or ambience rather than discrete repeated events. |

## Measurable evidence for a future classifier

Use several weak signals rather than one hard threshold:

1. **Onsets:** count distinct attacks and their density.
2. **Rhythmic periodicity:** autocorrelation or beat-tracking confidence.
3. **Pulse stability:** whether onset intervals cluster around a tempo grid.
4. **Event diversity:** spectral/envelope clusters suggesting more than one
   percussive role; this is not the same as merely having many transients.
5. **Duration:** supportive only. A long file can be a sustained tone, and a
   short file can still contain a fill.
6. **Boundary/repeat evidence:** similarity between the start and end of the
   candidate period, when a period can be estimated.
7. **Human intent evidence:** filename words such as `loop` are useful search
   evidence but must not override the audio definition.

## What is not enough on its own

- duration longer than a one-shot;
- more than one onset;
- a filename containing `loop`, `perc`, or a BPM number;
- a single spectral feature;
- a model's high confidence without collection-held-out validation.

## Why the distinction matters

The current SLO labels mix **family** (kick, hat, percussion) and **form**
(one-shot, loop, fill). Separating those axes makes the definitions clearer:
`family=drum kit`, `form=loop`, and optional attributes such as `tempo`,
`meter`, `swing`, and `event_roles`. It also avoids treating a loop as a
particular instrument class.

## Research basis

Ableton describes loops as repeated sections and specifically treats drum loops
as rhythm-dominant material; Apple describes loops as prerecorded musical
phrases or riffs intended to repeat. Freesound's broad taxonomy places drum
loops under solo percussion examples such as rhythmic patterns and drum
passages. These sources support the proposed definition, but they do not
provide a universal numeric threshold; SLO should calibrate thresholds from
the collection-held-out human labels.

## Next experiment

After the 600 labels are complete, compare the proposed rules against the
human `Drum Loop`, `Percussion Loop`, `Top Loop`, `Hi-Hat Loop`, and `Drum Fill`
labels. Report precision/recall by collection and retain the rules as
explanation evidence unless a pre-registered classifier clears the existing
promotion gate.
