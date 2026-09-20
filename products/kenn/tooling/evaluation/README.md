# KENN V2-A Evaluation Workspace

This isolated repository holds a black-box, synthetic qualification harness for
the current KENN/Mix Review implementation. `Audio_Too` is read-only.

Run: `python benchmark/run_golden_benchmark.py`

Engine-level chat hard cases (grounding, answer quality, and self-check):

```bash
PYTHONPATH=apps/backend/src:packages/chat python3 tooling/scripts/evaluate_chat_hard_cases.py \
  --output /secure/evidence/kenn-chat-hard-cases.json
```

The receipt is bound to the question-corpus hash but stores no question text,
answer text, or retrieved source text. Public out-of-scope/abstention cases are
qualified by `tooling/scripts/eval_chat_coverage.py`; this runner only scores cases
that legitimately reach the internal answer engine.

Fixed retrieval-mode comparison:

```bash
PYTHONPATH=apps/backend/src:packages/chat python3 tooling/scripts/evaluate_retrieval_modes.py \
  --output /secure/evidence/kenn-retrieval-modes.json
```

This compares BM25 and hybrid retrieval on corpus cases with explicit expected
sources. It reports top-1, recall@4, MRR, and latency without storing questions
or source text. Personal feedback boosts are disabled for reproducibility.
