# Precedence-effect passage retrieval — 3 October 2026

Code commit: `0a1e59f9` (`Match precedence effect questions to existing Haas evidence`).

The existing index contains Haas passages, but “Explain the precedence effect.” displayed generic effect notes. Retrieval now uses “Haas effect” for this exact phrase during candidate search, reranking and displayed-source selection. The bare word “precedence” does not become a stereo-width topic. This changes passage selection without changing grounding policy, answer style, model settings or the corpus.

## Changed files

- `apps/backend/src/kenn/retrieval/retrieval.py`: phrase alias and consistent query normalization for expansion and reranking.
- `apps/backend/src/kenn/core/chat_retrieval.py`: apply the same normalization at search and displayed-source selection.
- `apps/backend/src/kenn/tests/test_precedence_effect_retrieval.py`: named regression covering both precedence phrasings, Haas and non-audio precedence.

## Diagnosis and verification

The first synthetic regression run failed both precedence phrasings while the Haas and non-audio cases passed: 2 failed, 2 passed in 0.13 s. Adding only a topic synonym did not repair displayed selection; candidate and displayed-source ranking needed the same phrase.

The unchanged 4,642-chunk index already contains 17 Haas/precedence matches across nine sources. After the repair, the precedence question displays the existing stereo-width/mono-compatibility and stereo-imaging-width passages. A three-question metadata-only probe completed in 0.399 s. Phantom-power and balanced-cabling questions still missed the relevant displayed passages; these remain separate unresolved retrieval issues. The probe read existing index data and did not rebuild it or call a model.

Scoped command, run from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_precedence_effect_retrieval.py apps/backend/src/kenn/tests/test_retrieval_evidence_classes.py apps/backend/src/kenn/tests/test_note_affinity.py apps/backend/src/kenn/tests/test_retrieval_mode_evaluation.py apps/backend/src/kenn/tests/test_chat_evidence_availability.py apps/backend/src/kenn/tests/test_evidence_window_alignment.py apps/backend/src/kenn/tests/test_llm_grounding_pair.py -o cache_dir=/private/tmp/kenn-precedence-scope-pass-20261003
```

Result: **74 passed in 0.92 s**.

Full command, run from `products/kenn` because retrieval is shared:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_CACHE=0 PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-precedence-full-20261003
```

Result: **4,010 passed, 12 skipped, 5 warnings, 1 pre-existing failure in 85.42 s**. The failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, also present before this change. Its diagnostic output remains private. `git diff --check` passed for the changed files. One CPU-heavy job ran at a time.

## Research decision and limits

The speed shortlist remains test proposals from other hardware. At about 13 tok/s, 220–280 tokens already require 17–21 s of decoding. This retrieval repair supplies more relevant evidence; it does not demonstrate faster decoding, an accepted useful model answer or a latency-gate gain. No new real-model run, Live-open soak, memory-pressure measurement or audio-dropout observation was performed.

Jack authorized physical GPU indices **0 and 1** for KENN work on 3 October. GPUs 2–7 remain off limits. This records the expanded GPU permission; server restarts, dependency installation, model downloads and switching to MLX still require Jack's approval. No remote connection details are recorded here. This slice did not load a model or run inference on either GPU.

The production output cap, keep-alive and thinking settings are unchanged. Cap/brief-style trials remain disabled pending Jack's decision. C1, C2 and C3 remain unticked; the required useful-answer gate on both surfaces with Live open is still failed. No plan item is ticked by this receipt.
