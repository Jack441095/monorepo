# SLO rename-plan qualification: complete testing library

Date: 2026-09-12

This is a read-only qualification over all 28,330 supported files in:

```text
/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing
```

Command:

```text
python3 tools/classification_benchmark/build_rename_plan.py \
  /Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing \
  --workers 4 \
  --out /tmp/slo_current_rename_plan_full_v1.jsonl
```

## Product-safe result

| action | rows |
| --- | ---: |
| never_act | 4,310 |
| review | 19,949 |
| suggest | 4,071 |
| auto_rename | 0 |

The planner is fail-closed because no owner-qualified automatic-action policy
exists. The normal validator selected zero rows.

## Identity and approval gates

The complete SHA-256 identity inventory found 1,020 exact duplicate groups,
with 1,564 aliases. The duplicate guard marked all 1,020 canonical paths and
all 1,564 aliases in the plan; among suggestion rows, 112 canonical and 158
alias flags were present.

The available acoustic near-duplicate inventory covers the previously embedded
7,315-file research subset, not every file in this 28,330-file scan. It added
510 known near-duplicate flags overall and 201 suggestion-row flags. These are
review cues only, never proof of duplication.

The approval audit found 4,071 suggestion rows and **zero rows ready for
approval**. The complete blind label manifest contains 24,020 review/suggestion
items at:

```text
tools/classification_benchmark/label_manifest_review_full_v1.json
```

Predicted classes are hidden by default. No source audio, metadata, or path was
modified, and no automatic rename permission was granted.
