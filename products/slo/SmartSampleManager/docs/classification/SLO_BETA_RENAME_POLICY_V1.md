# SLO Beta Rename Policy V1

## The promise

> SLO renames the sounds it is confident about, suggests where it is unsure, and
> leaves the rest for you. It renames about **15%** of a library automatically at
> **around 90% precision**, suggests another **9%**, and sends the rest to review.

Not "SLO classifies your library". It does not.

## What SLO will and will not do

| | classes | behaviour |
|---|---|---|
| ✅ renames automatically | Kick, Clap, Drum Loop | above the gate, no misleading filename token |
| 🟡 suggests only | Snare, Hi-Hat, Crash, Percussion Loop, Foley | user applies |
| 🔍 review queue | Other/none, anything below the gate | no label asserted |
| ⛔ never acts | **Percussion**, impulse responses | not renamed, not asserted |

## Why Percussion is excluded

15.4% precision — five wrong renames for every right one. It is an incoherent
parent class naming shakers, toms, rimshots and metallic hits at once. Excluding
it prevents more user harm than any accuracy improvement in this programme.

## Why we do not claim 95%

Measured 95.1% against a 95.0% requirement — a **0.1pp margin, inside seed
noise**. It would not survive a library we have not seen.

## Undo and trust

Every automatic rename must be individually undoable, and the review queue must
show *why* (the policy returns a human-readable `reason` and an `evidence` dict
on every decision). A user who cannot see why SLO did something cannot trust it.
