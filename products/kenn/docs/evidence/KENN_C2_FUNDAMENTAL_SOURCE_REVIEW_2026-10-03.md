# Audio fundamental source review — 3 October 2026

Audit at commit `b13bf8ed`, after the precedence/Haas repair in `0a1e59f9`. This documentation commit is recorded in branch history. No plan item is ticked.

The remaining phantom-power and balanced-cabling failures involve source coverage and quality as well as passage selection. Promoting the existing exact matches would not establish useful grounded answers. This receipt records the review tasks without changing retrieval or grounding policy.

## Existing-index result

The metadata-only probe read the existing 4,642-chunk index and took **0.2613 s**. It did not rebuild the index or invoke a model.

| Question | Concept phrase in displayed evidence | `results_are_weak` |
| --- | --- | --- |
| Explain the precedence effect. | Yes, existing Haas passages | False |
| Explain phantom power. | No | False |
| Explain balanced cabling. | No | False |

Phrase matching is a diagnostic, not an answer-quality assessment. The latter two questions display unrelated mixing passages, yet the current weak-evidence heuristic does not flag them. A lexical match alone is insufficient for these concept questions. Any change to evidence sufficiency needs a separate grounding-policy review.

An exact-phrase scan across the loaded index found two phantom-power matches:

- `dan-worrall-0AxzJ-8n6qY-pt1-note-2`
- `dan-worrall-s8JGUzZCynU-pt1-note-2`

Both are generated “Try this” notes with suspect hardware/software category errors. Their original source and generation provenance need checking before use. No generated prose is copied into this receipt.

The only balanced-cabling phrase match is `mains-hum-removal-for-dialogue-note-2`, a brief hum-prevention tip rather than a definition. The scan does not establish that every possible synonym or source lacks an explanation.

As a hardware example, Shure's PGA27 guide describes phantom power supplied by a mixer or audio interface through a balanced microphone connection. This supports treating the suspect software-device instructions as a source-review issue. [Shure PGA27 guide](https://pubs.shure.com/view/guide/PGA27/en-US.pdf). Ableton's Push 3 guide also places phantom-power and input-gain configuration on the external interface or its companion application. [Ableton external-interface guide](https://help.ableton.com/hc/en-us/articles/23279895416220-How-to-Use-an-External-Audio-Interface-with-Push-3-standalone).

Next steps: review the identified notes against their original sources; identify approved concept explanations; then test passage selection and evidence sufficiency separately. No corpus import, deletion or ranking promotion was performed.

## Commands and verification

Private probe, run from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_CACHE=0 PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python /private/tmp/kenn-fundamentals-retrieval-loop-20261003.py > /private/tmp/kenn-fundamentals-retrieval-loop-followup-20261003.json
```

The probe calls `load_chunks`, `load_terms`, `search`, `display_results` and `results_are_weak` for the three questions above. It records source identifiers, scores and phrase-match flags only, and asserts that the repaired precedence question still selects Haas evidence. The separate source scan uses `bm25_search(..., limit=80, rerank=False)` followed by `rerank_results` and exact-phrase matching across the loaded chunks. Private source excerpts remain outside git.

Scoped command, run from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_precedence_effect_retrieval.py apps/backend/src/kenn/tests/test_route_query_model_free.py apps/backend/src/kenn/tests/test_retrieval_evidence_classes.py apps/backend/src/kenn/tests/test_retrieval_mode_evaluation.py -o cache_dir=/private/tmp/kenn-fundamentals-source-review-20261003
```

Result: **45 passed in 1.08 s**. These tests protect existing behavior; they do not qualify the source content. The most recent full backend run, recorded in the dispatch-token receipt, had 4,090 passes, 12 skips and the known pre-existing personal-path gate failure. This documentation slice did not rerun that suite. One CPU-heavy job ran at a time.

## Limits

Only this receipt and `KENN_PLAN.md` changed. No model run, Mac decode measurement, GPU inference, new corpus content or Live-open soak occurred. The other-hardware research figures remain hypotheses. Production answer style, output cap, keep-alive and thinking settings are unchanged; cap/brief-style trials remain disabled pending Jack's decision.

Jack authorized physical GPU indices 0 and 1 for KENN work; GPUs 2–7 remain off limits. No remote connection details are recorded here. No server restart, dependency installation, model download or MLX switch occurred.

C1, C2 and C3 remain unticked. The required useful-answer latency gate with Live open is still failed on both surfaces; memory pressure and audio dropouts remain unqualified until Jack schedules the soak.
