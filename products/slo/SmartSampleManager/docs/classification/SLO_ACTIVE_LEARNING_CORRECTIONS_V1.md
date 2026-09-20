# SLO Active Learning — Corrections Store V1

_`tools/classification_benchmark/corrections_store.py`, SQLite, schema v1._

When a user rejects or edits a suggestion, that is the most valuable signal SLO
can receive: a by-ear label on a file the model got wrong, drawn from the real
deployment distribution rather than a curated sample. Measurement in this project
has been unambiguous that by-ear labels are the only intervention that reliably
improves SLO, so capturing user corrections is not a nice-to-have.

## Schema

`created_utc`, `file_path`, `content_sha256`, `original_action`,
`original_label`, `original_conf`, `corrected_label`, `corrected_subtype`,
`user_note`, `taxonomy_version`, `policy_version`, `model_version`, `arm`,
`status`, `promoted_utc`.

## Four safety properties, each tested

| property | why | test |
|---|---|---|
| **No audio stored** | the store can be inspected or shared without moving a licensed sample | asserts no audio/blob column exists |
| **Append-only** | a user changing their mind adds a row; history is evidence | writes two corrections for one file, asserts both survive |
| **Not automatically trusted** | a mis-click must never rewrite the dataset | new rows land `pending`; promotion is explicit and per-row |
| **Version-stamped** | a correction against an old model is not a correction of a new one | asserts taxonomy/policy/model version on every row |

`python3 corrections_store.py --self-test` — all six checks pass.

## Promotion path

1. User corrects a suggestion → row written as `pending`.
2. Owner reviews pending corrections (`--export`).
3. Explicit `promote()` marks chosen rows as ground-truth candidates.
4. Promoted corrections are merged by **path** into the label CSVs, preserving
   `original_label`, and the dataset is rebuilt.

Nothing skips step 3. The lesson from this programme is that ground truth is the
most valuable asset SLO has, and it must never be modified by a side effect.

## Notes are first-class

The percussion sprint proved it: 11 of 47 files were marked `Unknown` **with a
written note naming the sound**, because the option list had no key for a plain
Hi-Hat, Rimshot or SFX. Parsing those notes resolved all 11. `user_note` is
therefore a real field, not a comment box.
