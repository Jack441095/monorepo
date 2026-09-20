# SLO rename-plan qualification: 500 real samples

Date: 2026-09-12

This is a read-only qualification receipt over the first 500 deterministic
paths in:

```text
/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing
```

Command:

```text
python3 tools/classification_benchmark/build_rename_plan.py \
  /Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing \
  --limit 500 --workers 4 \
  --out /tmp/slo_current_rename_plan_500_v2.jsonl
```

## Product-safe result

| action | rows |
| --- | ---: |
| never_act | 41 |
| review | 338 |
| suggest | 121 |
| auto_rename | 0 |

The planner now fails closed: its classifier may recommend an internal
automatic action, but a row remains review-only unless `--enable-auto` and an
explicit owner-qualified class policy are both supplied. No such policy is
currently approved.

The default validator reported:

```text
validated plan: 500 rows, 0 selected
dry run only
```

The independent duplicate guard found two acoustic near-duplicate review
flags and no exact-duplicate flags in this 500-row slice. The approval-gate
audit found 121 suggestion rows, all correctly blocked pending explicit owner
approval; zero rows were ready for approval.

The immutable review-collection export contains the same 121 suggestions, 338
review rows, and 41 never-act rows, with zero join errors and no transferred
labels. It is suitable as the next labeling/review queue.

The local review workspace was exercised against this export on an ephemeral
localhost port: health, summary, suggestion items, and approval-gate items all
returned successfully, and the server shut down cleanly. Its runtime safety
report confirmed that it serves no source audio, performs no rename action,
and promotes no labels.

The complete classification-benchmark regression suite was also run from the
project root with the project module path configured: **124 tests passed in
23.15 seconds**.

For corpus-wide exact identity, all 28,330 supported files were hashed with
zero errors. The inventory contains 26,766 unique content IDs and 1,564 exact
duplicate aliases across 1,020 groups. The duplicate guard now accepts this
complete-hash receipt directly (not only the older slice inventory), and the
500-row approval audit remains at zero ready rows.

For the next human pass, the 121 suggestion and 338 review rows were exported
to a blind, deterministic label-tool manifest (459 items). Predicted classes
are hidden by default to avoid confirmation bias; the existing resumable
keyboard labeler can consume it directly. The durable manifest is
`tools/classification_benchmark/label_manifest_review_500_v1.json`; launch it
with:

```text
python3 tools/classification_benchmark/label_tool.py \
  --set drums \
  --manifest tools/classification_benchmark/label_manifest_review_500_v1.json \
  --csv /tmp/slo_verified_review_500_v1.csv
```

An attempted apply without the independent approval receipt was refused:

```text
REFUSED: --apply requires --approval-gate
```

No audio path, metadata, or source file was modified. This receipt is not a
model-promotion result and does not grant rename permission.
