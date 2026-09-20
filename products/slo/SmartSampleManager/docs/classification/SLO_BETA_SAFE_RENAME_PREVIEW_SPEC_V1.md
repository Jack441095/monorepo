# SLO Beta Safe Rename Preview — UI Spec V1

## Principle

**SLO shows its intent before it acts.** The user sees exactly which files would
change, and approves or cancels.

## Four sections

### 1. Safe rename preview
Files where `action == auto_rename_eligible` — Kick, Clap, Drum Loop above the
gate. Shows old name → new name, the class, and confidence.

> **SLO will not change your files unless you approve.**

Buttons: *Approve all* · *Approve selected* · *Cancel*. Copy is the default;
Move keeps its existing second, explicit not-reversible confirmation.

### 2. Suggestions
`action == suggest` — Snare, Hi-Hat, Crash, Percussion Loop, Foley, plus
anything with a misleading filename token. One-click accept per file, nothing
applied in bulk.

### 3. Review queue
`action == review` — below the gate, or the model believes it is not a supported
sound. **No label is asserted.**

> **Some sounds are left for review when confidence is low.**

### 4. Not auto-renamed
`action == never_act` — Percussion and impulse responses.

> **Percussion and impulse responses are not auto-renamed in this beta.**
> Percussion covers several different sounds (shakers, toms, rimshots, metallic
> hits), so SLO cannot tell them apart reliably enough to rename them.
> Impulse responses are recordings of a space rather than instruments.

## Expected shape on a real library

| section | share |
|---|---|
| safe rename preview | ~15% |
| suggestions | ~9% |
| review | ~72% |
| not auto-renamed | ~3% |

**Do not present this as a failure.** Framing: *"SLO is confident about 15% of
your library, has ideas about another 9%, and is honest about the rest."*

## Non-negotiables

* Every automatic rename individually undoable.
* Every decision exposes its `reason` — a user who cannot see why cannot trust it.
* Never assert a label for `review` or `never_act` files.
* The preview never writes to disk.
