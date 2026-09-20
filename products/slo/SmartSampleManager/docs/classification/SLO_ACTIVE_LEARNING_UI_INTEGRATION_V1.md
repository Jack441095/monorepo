# SLO Active Learning — UI Integration V1

## Flow

1. **User accepts a suggestion** → `record(original_action="suggest", corrected_label=<same>)`.
   Agreement is evidence too: it confirms a class at a confidence level.
2. **User corrects a label** → `record(..., corrected_label=<new>)`.
3. **User adds a note** → stored in `user_note`, **parsed**, not decoration.
4. Row lands `status='pending'`.
5. Owner reviews (`--export`) and **explicitly** promotes.
6. Promoted rows merge by **path** into the label CSVs, preserving
   `original_label`; the dataset is rebuilt and re-checksummed.

Nothing skips step 5.

## Why notes are first-class

The percussion sprint: 11 of 47 files were marked `Unknown` **with a written
note naming the sound** (7 Tom, 2 Hi Hat, 1 Rimshot, 1 SFX) — because a
percussion-subtype option list had no key for a plain Hi-Hat, Rimshot or SFX.
Parsing those notes resolved all 11. An option list without an escape hatch
manufactures fake Unknowns.

Every correction UI must therefore offer **"not in this list"** plus free text.

## Guarantees (each tested)

| guarantee | test |
|---|---|
| no audio stored | asserts no audio/blob column exists |
| append-only | two corrections for one file, both survive |
| pending by default | a mis-click cannot rewrite ground truth |
| version-stamped | taxonomy, policy and model version on every row |
| exportable | CSV export round-trips |

## API surface for the UI

```
record(file_path, original_action, original_label, original_conf,
       corrected_label, corrected_subtype, user_note, ...) -> id
promote(ids)        # explicit, owner-only
export_csv(out)     # review
stats()             # pending / promoted counts
```

**Status: wired into the JUCE inspector and compiled; interactive runtime
smoke remains.** The inspector's optional "Correction note" field is passed to
`updateTaxonomyAsync`, which records it in the append-only pending correction
log alongside the original model evidence. Save/Reset remain explicit user
actions; no correction is promoted automatically.
