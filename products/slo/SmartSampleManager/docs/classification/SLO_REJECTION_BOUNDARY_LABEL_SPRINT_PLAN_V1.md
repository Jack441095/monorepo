# SLO Rejection-Boundary Label Sprint Plan V1

## Why this sprint

Rejection-boundary errors are **~27% of all remaining errors**, and **19.3% of
genuine junk still receives a confident real-class label**. That is the single
largest source of user-visible harm, and no method-side intervention has moved
it — only labels have.

The junk is absorbed by exactly the incoherent classes: Drum Loop (18), Foley
(7), Percussion Loop (6), Kick (5), Snare (4), Clap (3). A class that means
"several things" will accept a thing it has never seen.

## Current label counts and gaps

| class | have | need for a viable class (15) | gap |
|---|---|---|---|
| `Other/none` | 120 | 15 | 0 |
| `SFX` | 38 | 15 | 0 |
| `Foley` | 55 | 15 | 0 |
| `Percussion` | 50 | 15 | 0 |
| `Percussion Loop` | 62 | 15 | 0 |
| `Top Loop` | 6 | 15 | **9** |
| `Hi-Hat Loop` | 13 | 15 | **2** |
| `Rimshot` | 16 | 15 | 0 |
| `Bass Reese` | 27 | 15 | 0 |
| `Bass Hit` | 11 | 15 | **4** |
| `Sub Bass` | 0 | 15 | **15** |
| `Impact` | 13 | 15 | **2** |
| `Atmosphere` | 3 | 15 | **12** |
| `Synth One-Shot` | 44 | 15 | 0 |
| `Synth Loop` | 32 | 15 | 0 |

impulse responses labelled: 9
total labelled: 1069

## Sprint design — 400 files

| bucket | n | why |
|---|---|---|
| **Model says `Other/none`, high confidence** | 80 | is the reject class right? measures rejection precision directly |
| **Model says a real class, low confidence** | 80 | the review queue — is abstention correct? |
| **Files the model confidently got wrong** (known junk) | 60 | the false-accept population, the binding risk |
| **Impulse-response directories** | 30 | build a real IR class instead of a path heuristic |
| **Top Loop / Hi-Hat Loop candidates** | 60 | the overlap is entirely unevidenced — 6 and 13 examples |
| **Bass family**: Sub Bass, 808, Bass Hit, Reese | 60 | Sub Bass has **0** labels; Bass Hit has 11 |
| **Atmosphere / SFX / Impact boundary** | 30 | Atmosphere has 3 labels; SFX is incoherent (−0.024) |

Breadth rule applies throughout: **spread across collections**, max 4 per pack.
Measured worth ~2× per label versus depth.

## Option list — with escape hatches

The percussion sprint's key lesson: **an option list without an escape hatch
produces Unknowns that are really missing options.** This list must include:

* every target class above
* `Other/none` with a rejection reason
* **`Unknown` + free-text note**, parsed as label evidence
* a **"not in this list"** option that captures the intended label as text

## Rules

* **Do not force a label.** Unknown is a valid answer when the taxonomy lacks a
  class. Forced labels are what made Percussion incoherent.
* **Mark form explicitly** where loop/one-shot is ambiguous.
* **Notes are parsed**, so writing "it's a tom" is as useful as pressing a key.

## Expected impact, stated in advance

Based on the measured curve (+3.29pp accuracy and −17.9pp false-accept per 500
breadth labels), 400 targeted rejection-boundary labels should:

* reduce junk false-accept from 19.3% toward ~14%
* give `Sub Bass`, `Atmosphere`, `Top Loop` and `Impact` enough examples to be
  scored at all
* settle whether Top Loop / Hi-Hat Loop is a real overlap or a labelling artefact

It is **not** expected to fix Percussion — that needs ~50 more subtype labels.
