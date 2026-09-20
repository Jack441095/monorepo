# SLO Granularity Label Sprint — Plan V1

_Export: `tools/classification_benchmark/SLO_GRANULARITY_LABEL_SPRINT_EXPORT_V1.csv`
— 400 files, 55 collections._

## Why this sprint

The last sprint's lesson was that **deleting two harmful tokens beat adding
complexity**: removing `sd`→Snare and `snap`→Clap took the defensible 90%
operating point from 32.5% to **52.3%** coverage.

The remaining risky tokens cannot be fixed the same way, because they are
**granularity errors, not identity errors**. `perc` genuinely indicates
percussion — it just usually means Percussion *Loop*. `loop` genuinely indicates
a loop — just not which kind. Deleting them would discard real evidence. Only
labels settle a boundary.

## Allocation

| bucket | n | why |
|---|---|---|
| Top / Hi-Hat Loop | 60 | Top Loop has **6** labels; the overlap is entirely unevidenced |
| Bass family | 60 | Sub Bass has **2** labels; `sub` measures 11%, `bass` 0% |
| Percussion family | 60 | `perc` measures 29%, `shaker` 43% — both mean *Loop* |
| Foley / SFX / Impact / Texture | 60 | `texture` measures 0%; Atmosphere has 3 labels |
| Rejection boundary | 80 | ~27% of all errors; junk given confident classes |
| Low confidence or name/audio disagreement | 80 | is the review queue right? where fusion must choose |

**240 never labelled · 124 carry a high-risk token · 55 collections.**

## Selection is by difficulty, not by class

Picking files the model already handles teaches nothing. Every bucket is drawn
from evidence of difficulty: high-risk token hits, name/audio disagreement,
classifier abstention, known false accepts, thin classes, and files with **no
filename evidence at all** — the population the model must judge alone.

## Options and escape hatches

Each row carries its own option list plus five escape hatches:

`Unknown (write a note)` · `Not in this list (write it)` ·
`Not enough information` · `Corrupt / unusable` · `Taxonomy gap`

**This is the most important design decision in the sprint.** The percussion
sprint produced 11 `Unknown` answers that each carried a written note naming the
sound exactly, because the option list had no key for it. The reviewer was not
unsure — the list was incomplete. Notes are parsed as label evidence.

## Rules

* **Do not force a label.** `Taxonomy gap` is a valid, useful answer.
* **Mark form explicitly** where one-shot vs loop is the actual question — that
  is what most of these buckets are really testing.
* A written note beats a forced key press.

## Expected impact, stated before the sprint

From the measured curve (+3.29pp accuracy and −17.9pp false-accept per 500
breadth labels), 400 targeted labels should:

* give `Top Loop` and `Sub Bass` enough examples to be scored at all
* let `perc`, `shaker`, `top`, `sub` be re-measured and re-risked
* test the four thin low-risk tokens (`bd` 4, `clp` 6, `crash` 7, `impact` 7)
* reduce rejection-boundary false accepts

It is **not** expected to move headline accuracy much. The last 500 labels moved
it +3.29pp; the value here is in the *boundaries*, which is where the product
actually fails.
