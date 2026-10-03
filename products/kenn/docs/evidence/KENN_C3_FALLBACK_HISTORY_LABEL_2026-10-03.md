# Fallback history-label repair, 3 October 2026

Implementation commit: `97501811491b038e0ee2e7d3e9825e7d123d08ac`, pushed to `fix/review-critical-2026-10-02`.

The [reverb replay](KENN_C3_REVERB_FOLLOWUP_EVIDENCE_2026-10-03.md) delivered the internal `[Previous User Question]` label and repeated question when model validation rejected the rewrite. A clean retrieval fixture reproduced this on both surfaces, so neither source text nor streaming introduced it. The fallback renderer appended prompt context verbatim.

## Exact files and behavior

- `apps/backend/src/kenn/core/chat_answer.py`: `build_intent_answer` omits the previous-question prompt-context line from delivered fallback prose. Retrieval and generation still receive history; other context types keep their existing rendering.
- `apps/backend/src/kenn/tests/test_history_boundaries.py`: `test_reverb_followup_fallback_does_not_expose_internal_history_labels` covers payload and stream with isolated state, a clean reverb note and generation disabled. It checks useful fallback evidence, history-aware search and the unchanged generation-context helper as well as absence of the internal label and repeated question.

## Verification

Commands ran sequentially from `products/kenn`, on Fake Live with fresh caches.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py -k fallback_does_not_expose_internal_history_labels -o cache_dir=/private/tmp/kenn-history-label-red-20261003b
```

Before repair: **2 failed, 35 deselected**, 0.17 s, exit 1. Both fallback surfaces leaked the label.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py apps/backend/src/kenn/tests/test_correction_followups.py apps/backend/src/kenn/tests/test_note_affinity.py apps/backend/src/kenn/tests/test_answer_upgrade_context.py apps/backend/src/kenn/tests/test_knowledge_request_context.py -o cache_dir=/private/tmp/kenn-history-label-scoped-final-20261003
```

Final scoped checks: **94 passed**, 6.15 s, exit 0.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-history-label-full-20261003 > /private/tmp/kenn-history-label-full-20261003.log 2>&1
```

Full backend: **3668 passed, 12 skipped, 1 failed, 7 warnings**, 103.56 s, exit 1. The sole pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, still reporting the unchanged handoff path. `git diff --check` passed. Two earlier command setup mistakes used a wrong edit path and a nonexistent test filename; they changed no implementation and are superseded by the commands above.

## Research decisions and limits

Re-read the [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) and [product research section 12](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings). Decode remains the principal measured cost; external MLX and speculative-decoding speed factors are hypotheses for different hardware/model packages. Thinking is already off. The isolated cap and brief-style trials did not recover both surfaces with useful accepted output, so production answer style remains for Jack's decision. Keep-alive still trades about 5.4 GB of residency against avoiding reloads; Live memory pressure and audio dropouts remain unmeasured. The exact Qwen3 8B / approximately 1,100-token runtime comparison is written in the [brief-style receipt](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md), awaiting approval.

This is a fallback presentation repair, not an inference optimization or model-acceptance improvement. No new model replay was required to validate the deterministic rendering boundary. Generic dense-drum advice and editorial source rationale remain separate quality limits. No grounding, style, output ceiling, keep-alive, dependency, CI, permission, runtime, model file or index change. No private audio or model prose committed. No sealed-row tuning, UI or Live-open qualification. **C1, C2 and C3 remain unticked**; the accepted-answer 15-second gate still fails.
