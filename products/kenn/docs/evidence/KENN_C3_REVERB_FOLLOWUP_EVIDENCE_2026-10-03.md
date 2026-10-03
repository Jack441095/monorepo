# Reverb follow-up evidence and research follow-through, 3 October 2026

Implementation commit: `f9bd646ee619e954afc9e9eb09a8019ac741e49a`.

The [post-routing diagnostic](KENN_C3_POST_ROUTING_MODEL_DIAGNOSTIC_2026-10-03.md) lost reverb evidence when a dense-drums follow-up used history correctly. A static trace found the reverb workflow inside the existing 16-candidate pool, but generic drum titles displaced it from the three displayed sources. The fallback ranked notes separately and answered with parallel compression. Merely adding a reverb companion did not fix that fallback. After the lead repair, both surfaces still ranked their source cards from the bare current question.

## Exact files and behavior

- `apps/backend/src/kenn/core/chat_retrieval.py`: prefers an existing intent-bearing note source only when its score reaches the existing 0.55 close-score boundary. The original lead score still controls source diversity; weak or missing evidence stays weak. Retrieved input order is unchanged.
- `apps/backend/src/kenn/core/chat_formatting.py`: shares that intent lead with the deterministic fallback so a rejected rewrite cannot change subjects.
- `apps/backend/src/kenn/core/chat_answer.py`: both surfaces rank source cards with the same history-aware relevance query as the answer.
- `apps/backend/src/kenn/tests/test_note_affinity.py`: synthetic regressions cover displayed lead, fallback, one display slot, weak/missing evidence, the exact score boundary and input isolation.
- `apps/backend/src/kenn/tests/test_history_boundaries.py`: both chat entry points cite the reverb fallback after the dense-drums follow-up, with isolated state and no model or Live connection.

No index rebuild, grounding relaxation, runtime setting, model asset, dependency, CI or permission change.

## Verification

Commands ran sequentially from `products/kenn` with fresh pytest caches and Fake Live.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_note_affinity.py -o cache_dir=/private/tmp/kenn-intent-fallback-red-20261003
```

Fallback regression before the shared lead: **1 failed, 7 passed**, 0.22 s, exit 1. It selected parallel compression despite the displayed reverb companion.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py -k source_cards -o cache_dir=/private/tmp/kenn-intent-cards-red-20261003
```

Source-card regression before the call-site repair: **2 failed, 33 deselected**, 0.29 s, exit 1. Both surfaces delivered reverb advice with parallel compression first in their cards.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_note_affinity.py apps/backend/src/kenn/tests/test_note_section_boost.py apps/backend/src/kenn/tests/test_retrieval_evidence_classes.py apps/backend/src/kenn/tests/test_history_boundaries.py apps/backend/src/kenn/tests/test_correction_followups.py apps/backend/src/kenn/tests/test_retrieval_index_candidate.py -o cache_dir=/private/tmp/kenn-intent-cards-scoped-final-20261003
```

Final scoped checks: **80 passed**, 1.00 s, exit 0.

Mutation check replaces only the shared lead in memory:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python - <<'PYTEST'
from kenn.core import chat_retrieval, chat_formatting
import pytest
chat_retrieval.prefer_intent_note = lambda query, notes: notes
chat_formatting.prefer_intent_note = chat_retrieval.prefer_intent_note
raise SystemExit(pytest.main(['-q', '--tb=short', '-p', 'no:randomly', 'apps/backend/src/kenn/tests/test_note_affinity.py', '-o', 'cache_dir=/private/tmp/kenn-intent-fallback-mutation-20261003']))
PYTEST
```

**5 failed, 5 passed**, 0.33 s, exit 1, as expected. The display, fallback and score-boundary regressions detect removal. No checkout mutation.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-intent-cards-full-final-20261003
```

Full backend: **3666 passed, 12 skipped, 1 failed, 7 warnings**, 103.75 s, exit 1. The sole pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, reporting the unchanged machine-specific path in the handoff note. Scratch log: `/private/tmp/kenn-intent-cards-full-final-20261003.log`. `git diff --check` passed.

## Final-commit real-model replay

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_CHATS_DIR=/private/tmp/kenn-reverb-cards-replay-20261003/chats KENN_DB_PATH=/private/tmp/kenn-reverb-cards-replay-20261003/kenn.db KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python /private/tmp/kenn-reverb-cards-replay-20261003/run.py
```

Serial stream then payload, exit 0, 03:19:49.128–03:20:09.371 UTC. Wrapper SHA-256 `496ba758fd4ed07702e2277b18af2328928aa0f662d4f0054809dfcfe0b381ae`; answer SHA-256 `4ed4b9ed7577882d3a4a0ce4bbad2e28da8031de5924f9c2a7359b520139addb`. Retrieval and formatting match the implementation commit. Scratch `receipt.json` records all hashes, native attempts and before/after Mac state. `private-details.jsonl` holds history and model prose outside git.

| Surface | Final delivery | TTFT | Native prefill | Native decode | Decode rate | Accepted model answer |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Stream | 5.926 s | 1.198 s | unknown | unknown | unknown | no |
| Payload | 14.209 s | unknown | 0.360 s | 13.684 s | 17.757 tok/s | no |

Payload: 1473 prompt tokens, 1439 cached, 243 generated, 0.00108 s native load, completion reason `stop`. Stream interrupted on unsupported measurements; terminal native timings were not returned and remain unknown. Both delivered fallbacks use the reverb workflow and cite `reverb-send-workflow.md` first. Both complete answers were read. They still echo an internal history label, repeat generic return setup rather than explicitly adapting to dense drums, and include editorial source rationale. Those quality limits are not repaired here. Neither rejected generation counts toward accepted-model delivery: **0/2 accepted and 0/2 timely accepted**.

Mac: Apple M3 / 16 GB, Ollama 0.34.4, `kenn-brain-qwen3-8b` digest prefix `90a5eaf166fd`, 5.4 GB resident, 100% GPU, context 4096. Index `v-db8c6334cf63`, unchanged. Thinking off, ceiling 384 tokens, context-character budget 1200, keep-alive 30 minutes; production settings unchanged. Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather were reported open, alongside Codex and the existing caffeinate process. No Live process or concurrent heavy job. Swap used 12747.25 MiB of 14336 MiB before and after. Background load, thermal state, memory pressure and prompt-cache state were not controlled.

## Research decisions and limits

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) and [product research section 12](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md#12-accelerating-the-fixed-qwen-models-follow-up-findings) continue to guide the plan. External speed factors remain hypotheses, not M3 / 16 GB results. The previous lead-only replay spent 16.543 s decoding versus 0.360 s in prefill; the final replay varied to 13.684 s decoding without a runtime change. That variability does not establish an engine gain, and prefix tuning alone cannot remove the longer decode time.

The isolated [128-token cap](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and [brief-style trial](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md) lost accepted/useful answers on the local samples. Production style stays unchanged for Jack's decision. Thinking is already off. Keep-alive still trades about 5.4 GB of residency against avoiding reloads; memory pressure and audio dropouts need Jack's scheduled Live soak. The exact Qwen3 8B / approximately 1,100-token MLX comparison is written in the brief-style receipt, not executed. No new runtime, dependency, draft or model file was installed or downloaded.

This repair improves evidence continuity and honest fallback behavior. It does not qualify answer usefulness or decode acceleration. No independent held-out, UI, Live-open or memory/audio qualification; no tuning on sealed rows. **C1, C2 and C3 remain unticked** because the required 15-second eligible-request gate still fails.
