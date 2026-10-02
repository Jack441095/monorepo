# Citation evaluation

The production gate's acceptance is a decision to measure, not a reference label.
Use independent reviews of the candidate and the exact evidence shown to it.
The metric definitions follow [ALCE](https://github.com/princeton-nlp/ALCE), with
explicit claim spans and reviewer labels instead of its default T5-XXL judge.

From the monorepo root, capture a fresh run with the current index and fixed model:

```sh
KENN_LLM_CACHE=0 KENN_LLM_MODEL=kenn-brain-qwen3-8b python3 products/kenn/tooling/scripts/measure_chat_latency.py \
  --cases products/kenn/tooling/data/citation_eval_queries_v1.json --limit 240 \
  --surface stream --capture-answers products/kenn/.runtime/eval/citation_v1.raw.jsonl \
  --receipt products/kenn/.runtime/eval/citation_v1.latency.json
python3 products/kenn/tooling/scripts/evaluate_citation_labels.py prepare \
  products/kenn/.runtime/eval/citation_v1.raw.jsonl \
  --output products/kenn/.runtime/eval/citation_v1.labels.jsonl
```

Use a new capture filename for each run: the latency tool appends. The label tool
refuses to overwrite files. Captures and labels contain source text and model prose;
keep them under the ignored `.runtime/eval` directory. Aggregate scores contain neither.
No index rebuild, model installation, or Live writes are needed.

Each prepared row freezes the capture and records a content hash. Changing a source
or answer invalidates the review. Source IDs come from the same function that prints
the prompt's excerpt IDs; source bodies retain cleaning and truncation. The separate
`additional_evidence_text` and `timeline_context` fields are also available to the
reviewer, but cannot validate an invented excerpt ID.

Old captures with only flattened evidence are unavailable for citation review.
Streaming prefix rejections that have lost the original candidate are also unavailable.
Do not label the returned fallback template as the rejected candidate. Compare the
capture count against the latency receipt's attempted count; missing attempts and
questions that never reached the model must be reported separately. Coverage in the
scoring receipt refers to its input captures, not all questions in the latency run.

## Review rubric

Read the question, answer, and frozen evidence before looking at `accepted`, warnings,
or the production gate's `claim_citations`. Those fields must not supply labels.

For every factual assertion, including numerical recommendations and procedural steps,
add a claim with zero-based Python string offsets `start` inclusive and `end` exclusive.
Split independently checkable assertions. Include attached `[#id]` mentions in the
span. Spans must be ordered and nonoverlapping; every citation must belong to a span.
Offsets count Unicode characters, not UTF-8 bytes. Pure headings, greetings, questions,
and honest statements that evidence is missing do not require factual claim labels.

Each claim has these required labels:

- `factual`: whether this span makes an assertion requiring evidence.
- `shown_support`: whether the full claim follows from any of the frozen context.
- `cited_support`: whether its attached excerpt citations jointly support the full claim.
- `citations`: a list in mention order, each with `id` and boolean `supports`.
  A citation is useful if it independently supports the full claim or contributes
  necessary evidence to jointly support it. An irrelevant or redundant citation is
  false. An ID absent from the source snapshot is always false.

Keep entity, direction, value, unit, and scope together. Evidence for a compressor's
attack of 150 ms does not support a release of 150 ms. A plausible recommendation from
general audio knowledge is unsupported when it does not follow from the shown evidence.
For a contradicted or partially supported claim, `shown_support` and `cited_support`
are false. If the cited sources fail to support the full claim jointly, every
per-citation `supports` label is false, matching ALCE's precision treatment.

Set `review.complete` only after checking that all factual assertions were labelled.
Record a named `review.reviewer`, `review.origin` as `human` or `model`, and an independent
boolean `review.answer_acceptable`. An acceptable answer must address the actual
question, remain supported, and provide appropriate citations. A refusal can be
acceptable when the evidence cannot answer; an empty or unnecessary refusal is not.
Model reviews are provisional and must never be described as human gold labels.

For example, given the captured answer `Use 150 ms [#a].` and source `a` explicitly
recommending that release, a reviewed claim is:

```json
{"start": 0, "end": 16, "factual": true, "shown_support": true,
 "cited_support": true, "citations": [{"id": "a", "supports": true}]}
```

## Scoring and limits

```sh
python3 products/kenn/tooling/scripts/evaluate_citation_labels.py score \
  products/kenn/.runtime/eval/citation_v1.labels.jsonl \
  --output products/kenn/.runtime/eval/citation_v1.scores.json
```

Citation precision is useful citation mentions divided by all mentions. Citation
recall is factual claims jointly supported by their citations divided by all factual
claims. Faithfulness uses support from all shown evidence instead. These are micro
averages across reviewed claims, not averages of per-answer percentages. A denominator
of zero yields `null`. The receipt also reports independent answer acceptability and
the fraction of gate-accepted, reviewed answers containing unsupported claims.

Pending reviews and unavailable candidates never enter score denominators. They remain
in coverage counts. The minimum sample flag requires 150 distinct reviewed questions;
it is not a certificate of 90% quality. Abstention-only rows add no factual claim
denominator, and repeated generations do not add unique questions. Question hashing
keeps repeated questions in one calibration/test partition. Freeze test labels before
tuning; this deterministic split alone does not establish exchangeability or prevent
paraphrase leakage.

Wilson intervals are calculated at the answer level, not the correlated claim level.
Repeated questions disable them. Report reviewer origin, split counts, coverage, and
sampling strata alongside scores. A curated stress set estimates performance on that
set; its rate is not automatically the production query rate. Threshold risk control
and additional verification models come after enough independent labels exist.
