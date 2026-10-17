# KENN V2-A Evaluation Workspace

Synthetic qualification harnesses and their frozen results. The V2-A golden
benchmark and the V2-D product-qualification runner drove the Python Mix Review
engine inside `Audio_Too`; both were removed with it on 18 Oct 2026 (last state
under the tag `archive/audio-too-final`). Their reports and results stay here as
evidence. The V2-B/V2-C recommendation-gate scripts in `benchmark/` are
self-contained and still run.

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
