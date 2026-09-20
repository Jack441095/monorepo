# SLO Label Schema Review V1

## Gaps found and closed

| requirement | status before | action |
|---|---|---|
| primary family | present (`function_family`) | — |
| subtype | **percussion-only** | added generic `subtype` |
| form | present (`temporal_form`) | — |
| free-text notes | present (`note`) | — |
| reviewer confidence | present (`human_confidence`) | — |
| bad/corrupt/unusable | present (`rejection_reason`) | — |
| **missing-option escape hatch** | **MISSING** | added `not_in_list_label` |
| **not enough information** | **MISSING** | added `not_enough_info` |
| **taxonomy gap** | **MISSING** | added `taxonomy_gap` |

Schema is now 21 fields. `percussion_subtype` is retained unchanged for
backward compatibility — existing rows use it and must keep loading — while new
work writes the family-agnostic `subtype`.

## Why the escape hatches are not optional

The percussion sprint is the evidence. **11 of 47 files were marked `Unknown`
while carrying a written note that named the sound exactly** — 7 Tom, 2 Hi Hat,
1 Rimshot, 1 SFX — because a *percussion-subtype* option list had no key for a
plain Hi-Hat, a Rimshot or an SFX. The reviewer was not unsure; the list was
incomplete.

Parsing those notes turned 11 unusable rows into 11 resolved ones and produced
six primary-label corrections.

**A missing option manufactures a fake Unknown.** Three fields now separate what
were previously collapsed into one:

- `not_in_list_label` — *I know what this is, your list doesn't have it*
- `not_enough_info` — *the audio genuinely does not settle it*
- `taxonomy_gap` — *SLO's taxonomy has no right answer for this*

These are different facts with different consequences. The first is a labelling
tool defect, the second is a genuine ambiguity, the third is a taxonomy defect.
Collapsing them loses the signal that tells us which to fix.

## Backward compatibility

All existing CSVs load unchanged; new columns are written empty for rows that
predate them. Verified by the label-tool regression suite (24 tests), including
an explicit check that `verified_drums.csv` is not modified.
