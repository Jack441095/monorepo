# SLO 400-File Label Sprint Plan V1

_Export: `tools/classification_benchmark/SLO_400_FILE_LABEL_SPRINT_EXPORT_V1.csv`_

## Why these files

Rejection-boundary errors are **~27% of all remaining errors** and **19.3% of
genuine junk still receives a confident real-class label**. That is the largest
source of user-visible harm, and no method-side intervention has moved it — only
labels have.

## The 400

| bucket | n | why |
|---|---|---|
| confident `Other/none` | 80 | is the rejection right? measures reject precision |
| low confidence | 80 | the review queue — is abstaining correct? |
| known false accepts | 60 | junk given a confident class — the binding risk |
| Top Loop vs Hi-Hat Loop | 60 | overlap entirely unevidenced (6 and 13 labels) |
| bass family | 60 | **Sub Bass has ZERO labels**; Bass Hit has 11 |
| impulse responses | 30 | build a real IR class, not a path heuristic |
| Atmosphere / SFX / Impact | 30 | Atmosphere has 3 labels; SFX is incoherent |

**60 collections covered.** Three buckets were short when drawn only from the
labelled corpus — precisely because those classes are rare in what we have — so
they are topped up from the **unlabelled** library, breadth-first across packs.
That is the right source anyway: a sprint should ask new questions.

## Export columns

`bucket`, `path`, `filename`, `collection`, `pack`, `current_label`,
`current_subtype`, `prediction`, `confidence`, `action`, `reason_selected`,
`policy_reason`, `taxonomy_version`, `corrected_label`, `corrected_subtype`,
**`not_in_list_label`**, **`note`**.

## The escape hatch is mandatory

The percussion sprint produced 11 `Unknown` answers that each carried a **written
note naming the sound** — because the option list had no key for a plain Hi-Hat,
Rimshot or SFX. Parsing those notes resolved all 11.

**A missing option manufactures a fake Unknown.** Hence `not_in_list_label` and
`note`, both parsed as label evidence.

## Rules

* **Do not force a label.** Unknown is valid when the taxonomy genuinely lacks a
  class — that is a finding, not a failure.
* **Mark form explicitly** where loop/one-shot is ambiguous.
* Notes are parsed, so writing "it's a tom" is as useful as pressing a key.

## Expected impact, stated before the sprint

From the measured curve (+3.29pp accuracy, −17.9pp false-accept per 500 breadth
labels), 400 targeted labels should:

* cut junk false-accept from 19.3% toward ~14%
* give Sub Bass, Atmosphere, Top Loop and Impact enough examples to be scored
* settle whether Top Loop / Hi-Hat Loop is a real overlap or an artefact
* give impulse responses a real class instead of a path heuristic

It is **not** expected to fix Percussion — that needs ~50 more subtype labels.
