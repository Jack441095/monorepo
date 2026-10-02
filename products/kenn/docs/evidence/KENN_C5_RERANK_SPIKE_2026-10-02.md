# Cross-encoder rerank spike for the held-out wrapper rows — 2 October 2026

Follows [the ranking probe](KENN_C5_RANKING_PROBE_2026-10-02.md), which found no general heuristic fix and proposed
experiment 2 of the [research note](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md). No repo code was
changed. The hook lived in a scratch copy on the GPU box and is not committed.

## Setup

- Index: the same fresh box build as the probe (3,907 chunks, CPU, local manuals included).
- Model: `cross-encoder/ms-marco-MiniLM-L-6-v2`, fetched from hf-mirror.com because huggingface.co times out from the
  box. It is a third-party mirror, so there is no official hash to check against. `model.safetensors` is 90,870,598
  bytes, sha256 `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae`. Its `config.json` says
  `_name_or_path: cross-encoder/ms-marco-MiniLM-L-12-v2` even though the repo path we fetched was the L-6 one, so the
  provenance is not clean.
- Hook: wrap `search()`, take the top 20 hybrid results, score query against each chunk, turn the scores into z-scores
  clipped at ±2 and multiply the original score by `1 + alpha * z`. Two modes: `reorder` keeps the old score values
  and only changes the order (grounding thresholds see the same numbers), `blend` keeps the new scores.
- The cross-encoder ran as a small local server in the box's torch env, called over loopback from KENN's venv. That
  was only to avoid touching the shared conda env; it is not a proposed design.

## How the config was chosen

Alpha and mode were picked on hit@3 over the unsealed device (125), technique (50), internet (19) and knowledge (32)
fixtures. None of those contain the six held-out rows, and the sealed holdouts were not touched.

| Config | device | technique | internet | knowledge |
| --- | --- | --- | --- | --- |
| baseline | 74 | 37 | 19 | 32 |
| reorder 0.15 | 77 | 36 | 19 | 32 |
| reorder 0.3 | 79 | 37 | 19 | 32 |
| reorder 0.6 | 80 | 37 | 19 | 32 |
| reorder 1.0 | 81 | 37 | 19 | 32 |
| blend 0.3 | 78 | 38 | 19 | 32 |
| **blend 0.6** | **81** | **38** | 19 | 32 |

Blend 0.6 has the best total (+8 over 175 scored cases) and was declared as the config before anything was run on the
held-out rows. An earlier pass had already shown the six rows' failure counts for several alphas, so they are no
longer a clean holdout. What follows is one run at the pre-declared config, not a tuning result.

## Result at blend 0.6, K=20

- Coverage: 128 / 128 (84 applicable, 44 abstention), same as baseline.
- Wrapper eval: three of the six rows now pass (`upgrade-room-null`, `upgrade-kick-tail`,
  `internet-itu-target-boundary`). `harsh-after-mastering`, `eval-followup-snare-layer-mono` and
  `upgrade-buffer-recording` still fail. Nothing that passed before fails now.
- Guards unchanged from baseline: abstention 26 / 26, public-corpus boundary 13 / 13, negative-advice guard 29 / 30
  (the one miss is the same as before).
- Cost: search time over the 226 hit@3 queries went from 24 s to 116 s, so about 0.4 s more per query on a shared box
  with the model running in PyTorch. LLM turns are seconds, so it is small, but we have not set a latency budget for
  retrieval and this is not a measurement of an ONNX path.

## What we're taking from it

The model helps, but not by much: +7 device and +1 technique on the tuning sets, and half the held-out rows. The three
rows it does not close (harshness, snare layering, buffer) look like content or chunking problems, not ranking ones.
We haven't confirmed that.

I would not ship it yet. Shipping needs a new model file and the ONNX Runtime wheel, the only source we could reach
was a mirror with mismatched config metadata, and the gain is modest next to the added moving parts. If we want it
later, the sensible version is an ONNX export of the L-6 model fetched from huggingface.co with a recorded hash, scored
on the same four fixtures plus the coverage rows, behind a default-off flag. That needs Jack's OK first.

## Limits

One index, one machine, single runs. Latency was measured through a loopback HTTP hop on a busy shared CPU, so treat it
as an upper bound. The hit@3 sets are the unsealed fixtures, which other work has also looked at.
