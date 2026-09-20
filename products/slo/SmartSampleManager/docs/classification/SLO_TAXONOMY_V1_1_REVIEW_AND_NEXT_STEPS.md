# SLO Taxonomy v1.1.0 — Review and Next Steps

## What v1.1.0 changed, and the evidence

| change | evidence |
|---|---|
| Percussion subtypes populated | owner sprint: 25 Other Percussive Hit, 8 Shaker/Tambourine, 7 Tom, 1 Metallic |
| `Metallic` added | 1 observed example; recorded as supported-but-sparse |
| `Tom` confirmed as a subtype | detector rule was 90% correct at subtype level while scoring 0.0% as a class |
| `Hand Drum` marked NOT OBSERVED | sprint produced zero examples — retained, flagged, not silently kept |
| 6 primary labels corrected | 2 → Percussion Loop, 2 → Hi-Hat, 1 → Rimshot, 1 → Other/none |
| Foley Percussion → `source_attributes=foley` | provenance is an attribute, never a class |

Percussion coherence improved **−0.154 → −0.120**. Still negative, so it remains
`incoherent_parent`. 47 labels moved it a third of the way to zero; it is not
fixed, and claiming otherwise would be the kind of overreach this project has
been correcting.

## Confirmed genuine overlaps (not regex bugs)

**Top Loop vs Hi-Hat Loop.** The sprint produced no Top Loop and no Hi-Hat Loop
answers, so the overlap is unresolved by evidence rather than settled. The
detector fires `Top Loop` at ~36% precision with most errors being Hi-Hat Loop.
**Do not "fix" this in the detector** — there is no ground truth yet saying which
is right.

**Percussion vs Percussion Loop.** Confusion persists in both directions
(Percussion Loop → Drum Loop 10, Drum Loop → Percussion Loop 11). This is a form
problem inside a family, and multi-window features moved it only slightly.

## Escape hatches — a real finding from the sprint

11 of 47 files were marked `Unknown` **with a written note naming the sound**
(7 Tom, 2 Hi Hat, 1 Rimshot, 1 SFX). Those were not hedges: a *percussion
subtype* option list had no key for a plain Hi-Hat, a Rimshot, or an SFX, so the
only honest answer available was Unknown-plus-note.

**Two rules follow.** Any future option list must include an escape hatch, and
free-text notes must be parsed as label evidence, not discarded. Doing so turned
11 unusable rows into 11 resolved ones.

## Next steps, in evidence order

1. **Do not create Hand Drum** until examples exist.
2. **Do not split Top Loop / Hi-Hat Loop** until labelled by ear.
3. **Percussion needs ~50 more subtype labels** to test whether by-ear subtypes
   can take its silhouette positive. Derived subtypes already failed.
4. **Hi-Hat as primary vs subtype** is unresolved — 2 sprint files were Hi-Hat
   trapped inside Percussion.
5. **Metallic has 1 example.** It is recorded, not usable.
