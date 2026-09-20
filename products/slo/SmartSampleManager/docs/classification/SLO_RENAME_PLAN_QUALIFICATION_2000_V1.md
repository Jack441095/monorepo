# SLO rename-plan qualification: 2,000 real samples

Date: 2026-09-12

This is a read-only qualification over the first 2,000 deterministic paths in
the testing library:

```text
/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing
```

Command:

```text
python3 tools/classification_benchmark/build_rename_plan.py \
  /Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing \
  --limit 2000 --workers 4 \
  --out /tmp/slo_current_rename_plan_2000_v1.jsonl
```

## Result

| action | rows |
| --- | ---: |
| never_act | 58 |
| review | 1,665 |
| suggest | 277 |
| auto_rename | 0 |

The planner remains fail-closed because no owner-qualified automatic-action
policy exists. The normal validator selected zero rows.

The independent duplicate guard found 51 acoustic near-duplicate flags. The
approval audit found 277 suggestion rows, six of which were additionally
blocked by near-duplicate evidence, and **zero rows ready for approval**.

The review export contains no join errors and remains read-only. Its blind
label manifest contains 1,942 suggestion/review items at:

```text
tools/classification_benchmark/label_manifest_review_2000_v1.json
```

Predicted classes are hidden in that manifest to reduce confirmation bias.
No source audio, metadata, or filesystem path was modified.
