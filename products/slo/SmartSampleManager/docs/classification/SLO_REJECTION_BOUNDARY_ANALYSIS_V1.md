# SLO Rejection Boundary Analysis V1

_Where the renamer should abstain, and where fusion is actively unsafe._

## Current behaviour

| | audio-only | multi-window |
|---|---|---|
| junk confidently mislabelled (gate 0.5) | 20.2% | **19.3%** |
| junk correctly rejected | 60.5% | 60.5% |
| real sounds wrongly sent to review | 2.2% | 2.3% |

**One in five junk files still gets a confident real-class label.** Multi-window
improves this marginally. Rejection-boundary errors remain ~27% of all errors.

What the junk becomes: Drum Loop (18), Foley (7), Percussion Loop (6), Kick (5),
Snare (4), Clap (3). The absorbing classes are exactly the incoherent ones — a
class that means "several things" will happily accept a thing it has never seen.

## Per-class rename policy (evidence-based, not guessed)

Measured precision when the model acts at a 0.5 gate:

| class | n | acts on | precision | **policy** |
|---|---|---|---|---|
| Percussion | 50 | 52.0% | **15.4%** | **ABSTAIN ALWAYS** |
| Percussion Loop | 62 | 62.9% | 61.5% | suggest only |
| Foley | 55 | 45.5% | 68.0% | suggest only |
| Other/none | 119 | 73.1% | 72.4% | suggest only |
| Hi-Hat | 73 | 82.2% | 80.0% | suggest only |
| Crash | 26 | 80.8% | 81.0% | suggest only |
| Snare | 103 | 79.6% | 82.9% | suggest only |
| Drum Loop | 77 | 84.4% | 90.8% | **safe to rename** |
| Clap | 98 | 93.9% | 93.5% | **safe to rename** |
| Kick | 99 | 87.9% | 94.3% | **safe to rename** |

**`Percussion` must never auto-rename.** It acts on half its files at 15.4%
precision — five wrong renames for every right one. That single rule prevents
more user harm than any accuracy improvement in this programme.

Note this is a *policy* table, not a per-class confidence gate. Per-class gating
was tested and rejected: it undershoots its precision promise by 12pp on unseen
collections. Deciding *which classes may act at all* is safe; tuning a separate
*threshold* per class is not.

## Where fusion is unsafe

**28 files where the audio was right and the filename would have overridden it.**

| file | filename says | audio says | truth |
|---|---|---|---|
| `JVIEWS_antique_shop_snap.wav` | Clap | **Foley** | Foley |
| `JVIEWS_binaural_snap_in_tree_01.wav` | Clap | **Foley** | Foley |
| `Leek Snap.wav` | Clap | **Foley** | Foley |
| `Shaker Bodzin 3.wav` | Percussion | **Hi-Hat** | Hi-Hat |
| `MIDDLE EAST PERC.wav` | Percussion | **Percussion Loop** | Percussion Loop |
| `ECLIPSE Drum Loop 06 172BPM - Snare.wav` | Drum Loop | **Percussion Loop** | Percussion Loop |

Two clear patterns: the word "snap" reliably means a *recorded* sound (Foley),
not a clap; and a filename naming the family gets the *form* wrong. This is why
`audio-only` is the safer arm at 90% and why fusion cannot hold that promise.

## Impulse responses

9 flagged, excluded from all splits, **cannot be auto-renamed**. Labels retained
so the decision stays reversible.

## Recommended product behaviour

1. **Rename automatically**: Kick, Clap, Drum Loop above the gate.
2. **Suggest, do not apply**: Snare, Hi-Hat, Crash, Percussion Loop, Foley.
3. **Never act**: Percussion, impulse responses.
4. **Prefer audio over filename** where they disagree — measured 28 cases where
   the filename would have overwritten a correct audio call.
5. **Unknown is an acceptable outcome.** Forced wrong labels are not.
