# Threshold context and research triage, 3 October 2026

Implementation commit: `6a693aa9c0b83a347c3c95f201bd5a02224bfb0a`.

C1, C2 and C3 remain unticked. Parameter suggestions now retain the requested device and the corrected bus on both chat surfaces. The real-model replay shows that repairing history does not establish a useful answer: stream accepted a clipper answer to a limiter question; payload rejected its candidate and delivered unrelated AutoMix guidance. Neither met 15 seconds. No production style, output cap, grounding policy, device permission, asset or residency setting changed.

## Files and behavior

- `apps/backend/src/kenn/core/chat_routing.py`: recognises bounded parameter-suggestion questions, including “What threshold would you suggest there?”. When the preceding user turn is a correction, it carries the earlier device request alongside that correction. A new named subject does not inherit the limiter conversation.
- `apps/backend/src/kenn/tests/test_history_boundaries.py`: seven added cases cover the original threshold follow-up through stream and payload, parameter questions without history, and unrelated named subjects. They test history selection and the search boundary, not model-generated expectations.

## Verification

Commands ran sequentially from `products/kenn` with fresh pytest caches and Fake Live.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py -k "threshold_suggestion or parameter_suggestion or new_named_subject" -o cache_dir=/private/tmp/kenn-pcache-threshold-red-20261003
```

Before the fix: **2 failed, 5 passed, 26 deselected**, 0.49 s, exit 1. Both public surfaces dropped the limiter context.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py apps/backend/src/kenn/tests/test_correction_followups.py -o cache_dir=/private/tmp/kenn-pcache-threshold-green-20261003
```

After the fix: **45 passed**, 0.63 s, exit 0.

Mutation check, loaded in memory without editing the checkout:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python - <<'PYTEST'
from pathlib import Path
import pytest
from kenn.core import chat_routing
source = Path(chat_routing.__file__).read_text()
needle = '        return prior[-2:]\n    if query_topics(prior[-1])'
assert source.count(needle) == 1
exec(compile(source.replace(needle, '        return prior[-1:]\n    if query_topics(prior[-1])'), chat_routing.__file__, "exec"), chat_routing.__dict__)
raise SystemExit(pytest.main(["-q", "--tb=short", "-p", "no:randomly", "apps/backend/src/kenn/tests/test_history_boundaries.py", "-k", "threshold_suggestion", "-o", "cache_dir=/private/tmp/kenn-pcache-threshold-mutation-20261003"]))
PYTEST
```

Result: **2 failed, 31 deselected**, 0.54 s, exit 1. Both tests detect loss of the limiter anchor.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-pcache-threshold-full-20261003
```

Full backend: **3626 passed, 12 skipped, 1 failed, 7 warnings**, 104.93 s, exit 1. The sole pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`, detecting a machine-specific path in the unchanged handoff note. No suppression or unrelated edit. `git diff --check` passed.

## Original threshold replay

Private wrapper and model prose stay outside git. The replay used the recorded limiter request, drum-bus correction and original threshold question. It ran before the implementation commit; routing source SHA-256 `e4b6b05410d83cbd7fc49ee64a6bee1ff78d6d32f84206b2d93090903c74a908` matches that commit. Answer source SHA-256: `bf000707f27877d6001f684f6150a3bcfc4d49dcd5d28d0651cff8dbb8fb054c`.

```sh
KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_USE_MLX=0 KENN_CRITIQUE_LLM_ENABLED=0 KENN_CHATS_DIR=/private/tmp/kenn-c3-threshold-context-valid-20261003/chats KENN_DB_PATH=/private/tmp/kenn-c3-threshold-context-valid-20261003/kenn.db KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python /private/tmp/kenn-c3-threshold-context-valid-20261003/replay.py
```

Result: exit 0, both surfaces `used_history=true`; search retained limiter and drum bus. Both answers were read.

| Surface | Total | Delivered first token | Prompt/output tokens | Prefill | Decode | Decode rate | Cached prefix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stream | 20.755 s | 6.646 s | 1526 / 252 | 5.075 s | 14.150 s | 17.81 tok/s | 605 |
| Payload | 15.306 s | Not exposed | 1518 / 264 | 0.374 s | 14.819 s | 17.82 tok/s | 1481 |

Stream passed existing acceptance checks but used clipper guidance for a limiter question, including wrong device controls. Payload's candidate addressed limiting but introduced an unsupported threshold range; it was rejected, and the delivered fallback answered an AutoMix topic. Backend acceptance therefore remains separate from applicability and human quality. Provider calls completed with `stop`, application-cache misses, and warm load costs of 0.0043 / 0.0011 s. Native prefix caching was active. Sequential order, different output lengths and prefix reuse prevent a controlled stream/payload comparison.

Payload deterministic critique also referenced the prior stream trace despite different session IDs in the same scratch database. This may affect the acceptance comparison and needs isolation investigation. `KENN_CRITIQUE_LLM_ENABLED=0` disables optional model critique, not that deterministic trace comparison.

An initial replay accidentally selected the following cancellation row: it made no provider call and is excluded from these measurements. The corrected replay used a separate scratch directory.

Mac state, 01:49:34–01:50:10 UTC: Apple M3, 16 GiB, Ollama 0.34.4, Qwen3 8B Q4_K_M, digest `90a5eaf166fdda7e95441577e6ae96ebacf3248772a4366d1199b7b6ac0b0405`, reported 5.4 GB at 100% GPU with context 4096. Calendar, ChatGPT, Clock, FindMy, Flux, Home, Mail, Notes, Ollama, Siri AI, Stocks, Visual Studio Code and Weather appeared in the application inventory; Codex was active but omitted. Live was absent. Swap used 12450.12 → 12138.12 MiB, with 13312 MiB allocated. Background work and thermal state were uncontrolled. One heavy job at a time; no index rebuild. No cold-load or Live/audio result.

## Research triage against our measurements

The [speed research](KENN_SPEED_RESEARCH_2026-10-03.md) is a shortlist from other hardware. The [broader product research](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md) calls for stage accounting, applicable evidence and quality checks beyond backend acceptance. Our observations support these next checks; they do not validate another machine's speedup:

| Research idea | Local evidence and next boundary |
| --- | --- |
| Thinking off | Already sent as `think:false`; skip as a new optimisation. |
| Shorter answers | Isolated 128-token cap and soft brief-style trials are recorded in the C2 receipts. They had mixed timely acceptance and lost useful content. Neither adopted; Jack decides style. |
| Prefill / stable prefix | Native cached prefixes already reduce some prefills. The threshold payload still spent 14.819 s decoding. Useful to measure, insufficient to claim the gate recovered. Preserve grounding content. |
| keep_alive | Existing 30-minute setting plus 240-second ping can keep roughly 5.4 GB resident throughout an open app session. Warm loads here cost milliseconds; cold reload and real Live memory/audio effects remain unmeasured. No change without Jack. |
| Same-lineage MLX | Exact Qwen3 8B, approximately 1,100-token prompt, separate prefill/decode, warm/cold and native-cache controls, hardware and quality comparison already proposed in the brief-style receipt. Do not install, download or execute without Jack. |
| Speculative decoding | Requires draft assets and a supporting runtime. Draft acceptance and 16 GiB residency must be measured. Parked for approval; no extrapolated multiplier. |
| KV quantisation | External report found a small memory saving without decode gain. Lower priority; no setting changed. |
| Avoid wasted work / improve evidence applicability | Thirty-turn reading found wrong device guidance, action intent falling into knowledge, instruction echoes and rejected unsupported measurements. Fix deterministic conversation boundaries first, measure call counts and phase costs, and investigate trace isolation. Do not relax grounding to improve acceptance. |

[Cap measurements and residency trade-off](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md); [brief-style results and exact runtime proposal](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md).

No plan tick is earned. The thirty-turn suite has not been rerun after these fixes. UI delivery, two-track and project-switch cases, held-out human review and the owner-scheduled Live soak remain open. Instruction echoes and evidence applicability still fail; a speed measurement cannot count a wrong answer as useful.
