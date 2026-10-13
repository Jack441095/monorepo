# KENN offline SEAL experiment

Recorded 13 October 2026. The work queue remains C4 in `KENN_PLAN.md`. This runbook describes the executable contract and recorded build; it does not qualify an adapter for serving.

The current chat model is **Qwen3 4B Instruct 2507, Q4_K_M**, as Jack confirmed on 13 October. The main checkout's `.env` still names `kenn-brain-qwen3-8b`; it is stale relative to that owner decision. The experiment names the 4B explicitly and does not edit `.env`, load or select an Ollama model, restart a server, or contact Live. The optional MLX engine's smaller default is not the active answer baseline.

## Existing owners and the failed-tune evidence

`core/chat.py`, `chat_routing.py` and `chat_live_router.py` own conversation routing. `chat_answer.py` constructs grounded answers; `chat_retrieval.py` and `retrieval/retrieval.py` select evidence; `chat_grounding.py` checks generated answers. Session context, memory, proposal policy and action services remain their current owners. This experiment is conversational training, not a new command planner or execution path.

`llm/llm_rewrite.py` owns the native Ollama transport and usage capture, with Qwen thinking disabled. `llm/mlx_inference_engine.py` is an opt-in alternate. The corpus builder's own checker acceptance is insufficient semantic review. The CUDA worker reuses only `batches` and `target_loss` from the command LoRA trainer: it does its own nontruncating assistant masking and exact step loop. It imports no planner corpus and does not use the trainer's epoch-based eager GPU batches. Existing optional torch/Transformers/PEFT/safetensors packages are required for real trials; no dependencies were added.

The [25 September review](../reviews/KENN_BRAIN_ANSWERS_REVIEW_2026-09-25.md) records the 345-answer 8B style tune's worse use rate and slow tails. The plan's 8 October answer-tune receipt records 505 checker-kept teacher answers, 448 training / 57 validation, trained before owner grades arrived. `kenn-answer1` delivered 58/72 versus 44/72 at a 6.13 s versus 6.67 s median, but its additional deliveries were mostly partly correct or wrong. The secondary model review reported 26% right / 28% wrong versus 33% / 17%; this was not Jack's blind grading. Delivery acceptance never establishes correctness. Neither rejected tune supplies approved training targets here.

The [research note](../research/KENN_SEAL_RESEARCH_2026-10-13.md) pins the v2 paper and upstream revision. Appendix B.10 motivates a cheaper screen, but supplies no proxy/gain calibration for KENN. The screen here is an adaptation: human semantic approval plus example-kind diversity. It is not the paper's GPT-4.1 rubric, an adaptation reward, or evidence of learning.

## Recorded baseline and verification

Read-only local inspection produced `products/kenn/.runtime/seal-baseline-2026-10-13.json`, outside Git:

| Field | Recorded value |
| --- | --- |
| Git revision | `e278fc49422f074e6fe3554ef58a217ed088d214` plus a per-file hash map of the dirty Python build |
| Chat model | `qwen3:4b-instruct-2507-q4_K_M` |
| Model digest | `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0` |
| Quantization/runtime | GGUF Q4_K_M; Ollama-native 0.40.3 |
| Tokenizer | Bound to model digest; model metadata SHA-256 `bdaf865c1ae68f48661b50d841b029948e488a00a1031322f2ce347d084b71e4` |
| Code hash | `a298000122e1915a22ab7ae81a5601fb25374b1f9b39d4307ca012648bc4a3ac` |
| Retrieval index | `v-db8c6334cf63`, SHA-256 `140f97a96c0bfaf758a5bff70525b4e0b6eaaf04b5dd5a88e2d8902e0d2f4c01` |
| Ollama template hash | `40c21f34cf67d8c760ef72f8ad3ae5afad514299d4b06e91dd9a8d705af7b541` |
| Generation | Temperature 0.35; 128 output tokens; thinking off; response cache off |
| Hardware | Apple M3, arm64, 17,179,869,184 bytes unified memory (16 GiB) |

The manifest also stores the system-prompt hash. Exact rendered messages and captured retrieval results belong to each reviewed task, whose complete JSON is hashed. The tokenizer, template and model identities cannot be inferred from a tag alone. Snapshotting does not measure answers and does not claim to inspect the running app process's environment.

Verification from the monorepo root:

```sh
python3 -m pytest -q products/kenn/tooling/tests/test_seal_experiment.py
KENN_LIVE_BACKEND=fake python3 -m pytest -q products/kenn/apps/backend/src/kenn/tests/test_allowed_figures.py products/kenn/apps/backend/src/kenn/tests/test_answer_grounding_bypass.py products/kenn/apps/backend/src/kenn/tests/test_unasked_product_names.py
python3 -m compileall -q products/kenn/tooling/seal_experiment products/kenn/tooling/scripts/run_seal_experiment.py products/kenn/tooling/tests/test_seal_experiment.py
```

Results: **79 new offline tests and 28 existing grounding tests passed**. No scoped failures remain. The full backend suite was not run; no shared production implementation changed. Five isolated mutations were caught: numeric drift (four cases), wrong inner starting checkpoint (one), delivery credit without complete grounded answers (three), dropping missing timings (one), and ignoring abstentions (one). Workspace source remained unchanged; mutation logs are under ignored `.runtime/seal-verification/`.

The real CLI dry run completed in `.runtime/seal-verified-2026-10-13/`: A/B/C/D, two outer rounds, four measured-in-fixture D candidates, two simulated policy updates and seven simulated adaptation trials in total. Proxy correlation is null because the synthetic scores are constant. No model generation, GPU training, correctness improvement or timing result is implied by these fixtures.

## Reproducible commands and artifacts

Run from `monorepo`. Every output must be outside the Git checkout or under `products/kenn/.runtime/`, which is ignored. Weights, raw licensed text, review packets and receipts stay out of Git.

```sh
python3 products/kenn/tooling/scripts/run_seal_experiment.py snapshot --out products/kenn/.runtime/seal-baseline.json
python3 products/kenn/tooling/scripts/run_seal_experiment.py dry-run --out products/kenn/.runtime/seal-dry-run
```

The dry run writes a readable **synthetic** dataset and separate sealed file, which illustrate the JSON structure. They are contract fixtures, not a domain corpus. Real `run`/`final` commands reject `synthetic: true`; removing that flag does not turn a fixture into licensed, reviewed evidence.

Prepare `data.json` using reviewed public production notes and version-applicable technical documentation. Source records contain `text`, `sha256` of exact UTF-8 text, a pre-split broad source `family`, `split`, `license`, `privacy: public`, and `training_permission: true`. Preserve origin/version/license evidence alongside those fields for the reviewer. No session facts, conversations or personal preferences may be approved for shared weights.

The dataset has schema `kenn.seal.dataset.v1`, `sources`, `tasks`, `ordinary_examples`, `approvals`, `sealed_sha256`, and `sealed_questions`. Tasks carry IDs, question/task families, coverage category, source IDs, independently reviewed `accepted_answers`, and exact inference `messages`. Development tasks may only be `reward` or `retention`. Required reward and sealed coverage is technical explanations, numeric units, follow-ups, missing evidence, conflicting sources, hallucinated devices and proposal policy. Each partition allows at most 32 tasks. Broader domain families must be split before variants; `coverage` is not a substitute for source/task-family isolation.

`scope: knowledge_only` has no retrieved passage and measures incorporation/transfer separately. `scope: frozen_retrieval` needs KENN-captured `results` (`score` and `chunk`), `route`, `confidence`, `answer_mode`, optional timeline/additional evidence, and the exact grounded prompt in `messages`. The unchanged `generated_answer_validation` must accept an answer as well as the independent reference/owner grade before it earns reward. Frozen retrieval is a replay, not live product qualification.

Store final tasks separately as `kenn.seal.sealed.v1`. Freeze their canonical JSON digest and question word fingerprints in the development dataset before generation. Source content, source family, task family, duplicate questions and training/evaluation overlap are checked. Final sources can be recorded in the manifest, but only train-partition context is sent to the generator. Sealed prompts and labels are never loaded by `run`.

Every source, ordinary target and evaluation task needs a content-hash-keyed approval. Approval records require these exact semantics:

```json
{
  "verdict": "approved",
  "reviewer": "human reviewer identity",
  "reviewed_at": "ISO date/time",
  "supported": true,
  "numbers_units_correct": true,
  "no_contradictions": true,
  "shared_weights_allowed": true
}
```

These are attestations from an independent human review, not automatic scores. Hashes expire on any content/provenance change. Numeric checks reject changed numbers/units; exact excerpts, whitespace-normalized duplicate checks and a 0.6 question-word overlap guard add mechanical rejection. They cannot prove semantic support or catch every paraphrase. Human review must catch unsupported implications, contradictions and broader family leakage.

The generator emits only `{"examples": [...]}`. Each example has `kind`, `messages` and `support`; support contains exact `source_id`, `sha256`, and `excerpt`. Allowed kinds are restatement, implication, QA, explanation, follow-up and abstention. The saved `kenn.seal.self_edit.v1` envelope adds generator/model/package identity, policy checkpoint, prompt, seed, source family/hash and dataset hash. No generated command, script or training configuration is executed.

On the authorized GPU node, use an **already available** HF checkpoint and existing training environment. Hash its full directory with `seal_experiment.backends.tree_hash`. Fill the baseline's `hf_checkpoint_sha256` and `same_checkpoint_attestation` with reviewer/date, that hash and `served_model_digest`. The attestation binds the exact Qwen3-4B-Instruct-2507 lineage to the served GGUF. BF16 HF evaluation remains different from quantized Ollama serving, even with matching lineage. Copy the pinned source build, not merely its Git revision; real trials verify every source hash and package version. No downloads/installations are performed by the worker.

```sh
CUDA_VISIBLE_DEVICES=1 python3 products/kenn/tooling/scripts/run_seal_experiment.py run --data /path/to/reviewed/data.json --baseline /path/to/pinned/baseline.json --base-model /path/to/existing/Qwen3-4B-Instruct-2507 --out /path/to/offline/pilot
```

Exit code 2 means a required review is pending. Generated edits are saved before training and report their approval keys. Put their approvals in a **separate** `approvals.json`; do not mutate the frozen dataset's approval map. Unknown reward or retention prose also pauses selection and writes `blind-progress.json`. Independently review its evidence/reference and submit a card-ID-keyed `grades.json`:

```json
{
  "card id from packet": {
    "reviewer": "owner identity",
    "reviewed_at": "ISO date/time",
    "correct": true,
    "usefulness": 2,
    "unsupported_claims": 0,
    "policy_violation": false
  }
}
```

Use usefulness 0 for unusable, 1 for partial, 2 for useful; correctness is separate. Grade correct abstentions as useful only when the missing-evidence task calls for one. Use the packet without its separate answer key; keys and checkpoints stay hidden while grading. Identical task/answer pairs must receive consistent grades.

```sh
python3 products/kenn/tooling/scripts/run_seal_experiment.py grade --packet /path/to/offline/pilot/blind-progress.json --grades /path/to/grades.json --out /path/to/review
CUDA_VISIBLE_DEVICES=1 python3 products/kenn/tooling/scripts/run_seal_experiment.py run --data /path/to/reviewed/data.json --baseline /path/to/pinned/baseline.json --base-model /path/to/existing/Qwen3-4B-Instruct-2507 --approvals /path/to/approvals.json --labels /path/to/review/owner-labels.json --out /path/to/offline/pilot
```

`grade` binds grades to saved answers and rescores without a provider. Resume reuses completed, unchanged adapters and saved answers so the owner grades the text actually evaluated. The identity manifest rejects changed datasets, backend, budgets or seeds. Each execution has its own request/response receipt; resumed compute counts against the run ceiling. If later grades change an already completed policy-selection trajectory, start a fresh run directory rather than treating stale candidates as on-policy samples. Hash checks reject mixed artifacts.

## Budgets and the two updates

Defaults: 2 outer rounds, 2 candidate sets per round, 2 contexts per set, at most 4 examples/context, 4 inner and 4 policy optimizer steps, batch size 1, 2048 tokens/sequence, 8192 training-token ceiling, 768 self-edit output tokens, rank 8, learning rate `2e-4`, 20 GB CUDA allocator ceiling, 300 s/operation, and 3600 s cumulative run compute. Selection requires at least 0.01 reward gain and retention at least the original baseline. Values and default rationales are written in `identity.json`; `--limits` takes a JSON object of overrides within hard ceilings. Record why any override is needed alongside the run.

B/C/D use the same optimizer-step and token ceilings. Actual prompt/target tokens and examples used are recorded; they are **not claimed to match exactly**. The worker spreads a short step schedule across the examples rather than silently consuming only the first context. Oversize policy completions or reviewed answers are rejected, never truncated. Trial generation, evaluation, load and policy-training costs remain additional D overhead. A learning-efficiency curve requires separate development runs with predeclared budgets and reviewed data counts, then one frozen selected configuration for final evaluation; this pilot does not measure steps-to-quality.

For each D round, generate from the current immutable policy, train each candidate in a fresh process from that same policy, evaluate against independent reviewed references, and measure retention. Successful context→JSON self-edit generations become outer SFT targets on the original policy. Temporary inner adapters are never policy starting states. Recompute baseline reward and resample after each update; failed or forgetting trials are not reinforced. A policy update that loses baseline retention is rolled back as a disposable candidate, with its evidence retained.

Fresh processes, physical GPU 1 visibility checks before imports, local-only model loading, starting-checkpoint hash checks and process-group termination on timeout protect trial isolation. Adapters are saved separately; no base weights are merged or overwritten. The worker records GPU load/prefill/decode, allocator peaks, actual training tokens and time, and recognizes the existing KENN abstention wording. It labels first-visible timing and Mac pressure unknown. Generation timing includes per-token synchronization overhead and must not be presented as a serving benchmark.

Start calibration with default `--proxy-screen 0`: measure every reviewed trial's quality screen and actual reward gain. Pearson association is null with fewer than three trials or constant scores. An optional higher threshold skips adaptation and records **unmeasured** gain for screened candidates; it cannot measure false negatives without later audited adaptations. Never use this option to claim B.10's speedup without measured calibration and total costs.

After development choices are frozen:

```sh
CUDA_VISIBLE_DEVICES=1 python3 products/kenn/tooling/scripts/run_seal_experiment.py final --data /path/to/reviewed/data.json --sealed /path/to/sealed.json --baseline /path/to/pinned/baseline.json --base-model /path/to/existing/Qwen3-4B-Instruct-2507 --out /path/to/offline/pilot
python3 products/kenn/tooling/scripts/run_seal_experiment.py grade --packet /path/to/offline/pilot/blind-final.json --grades /path/to/final-grades.json --out /path/to/final-review
```

The sealed reservation is written before any answer call; a second `final` is refused even after a failure. Grade saved outputs; do not rerun or tune on final answers. The pipeline never enables serving or publishes a model.

## M3 product measurement and amortization

Offline A/B/C/D are HF CUDA knowledge or frozen-retrieval comparisons. They do not yet implement the complete quantized KENN product journey. For product qualification, use the existing `measure_chat_latency.py` with a fresh FakeLive process, reviewed development questions, current index and explicit 4B model environment. Keep both generation and grounding active. Its `cache-condition cold` drops the semantic answer cache; it does **not** prove the model was unloaded. Declare model-cold/warm separately, and use actual native cache counters. Companion displayed-answer timing requires a UI measurement; streaming TTFT is not a substitute.

Example for the unchanged model, without changing the running server:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M KENN_LLM_CACHE=0 python3 products/kenn/tooling/scripts/measure_chat_latency.py --cases /path/to/reviewed/product-cases.json --surface stream --cache-condition cold --build-manifest /path/to/pinned/baseline.json --receipt /path/to/M3-receipt.json --review-capture /path/to/M3-review.json
```

Declare task IDs/questions identical to the frozen reviewed dataset. Use an isolated test profile for this existing harness's cache/history storage. Adapter export or alternate serving is a later reviewable action; these commands do not switch the production model. Repeat comparable cold/warm runs and capture complete/displayed timing, load/prefill/decode, peak memory/pressure, model switches, truncations, abstentions, fallbacks and proposal-policy journeys. Current receipts leave some fields unknown; timestamp UI and OS observations alongside them. The conversational training runner cannot prove the existing proposal executor's boundaries by QA alone.

`product-report` imports existing `kenn.chat_latency.v2` receipts without inference. Its `kenn.seal.product_receipts.v1` input has `baseline`, a `receipts` list of `{arm, model_condition, model_digest, path, model_switches}` entries, and optional common-unit `costs`. Receipt manifests must identify Apple M3 / 16 GiB, model digest and unchanged source/index/template/generation identities. It rejects GPU hardware as Mac evidence. It groups arm × model condition × surface × actual cache condition, preserves missing measurements as null, and exports a blind product packet. Semantic correct/useful counts remain separate from complete grounded delivery. Efficiency credits only the latter, in actual inference groups; unknown completion leaves efficiency unknown. Partial timing coverage cannot produce a p50/p95.

```sh
python3 products/kenn/tooling/scripts/run_seal_experiment.py product-report --data /path/to/reviewed/data.json --receipts /path/to/product-receipts.json --out /path/to/product-report
python3 products/kenn/tooling/scripts/run_seal_experiment.py grade --packet /path/to/product-report/blind-product.json --grades /path/to/product-grades.json --out /path/to/product-review
python3 products/kenn/tooling/scripts/run_seal_experiment.py product-report --data /path/to/reviewed/data.json --receipts /path/to/product-receipts.json --labels /path/to/product-review/owner-labels.json --out /path/to/product-report
```

For final product receipts, pass the already frozen `--sealed` file; keep final grades separate from development. Supply amortization costs only after measuring them in a declared common monetary or energy unit: `{unit, baseline_per_answer, arms: {D: {per_answer, extra_adaptation}}}`. Usage volume is `ceil(extra_adaptation / (baseline_per_answer - per_answer))` when savings are positive; otherwise null. Include generation, adaptation, policy training, evaluation, conversion and review overhead in extra cost. Adding GPU seconds to Mac seconds is not a cost model.

## Small pilot preparation, 13 October

The ignored local directory `.runtime/seal-pilot-2026-10-13` contains draft and approved copies, a separate reserved final file, an 18-card source/reference packet, an owner approval receipt, limits and preflight receipts. `review-development.md` contains two training contexts with four ordinary targets, seven reward questions and two retention checks. `review-sealed.md` contains seven final reference questions. Packet SHA-256 is `8e1af5b6c88fd10bd60961ff4e958cac2d91651a4aff7ff70babfb492a408d19`.

Family isolation, quantities, reference structure, duplicates and sealed fingerprints passed structural validation using test attestations only in memory. No test attestations were saved. Jack subsequently approved the exact displayed packet in chat. `owner-approval.json` records the approval scope and his earlier uncertainty; it represents owner acceptance, not independent expert certification or blind model-answer grading. The approved copy binds all 38 source/target records and passes validation. The untouched draft retains empty approvals and false permissions and remains rejected. Primary technical references and arithmetic were checked separately; the full W3C license notice is preserved beside the data. Corrections require new hashes and review. This tiny reference-conditioned packet checks the training/review workflow; its answers cannot establish full KENN retrieval, grounding, execution or broad language quality.

The latest remote retry, with keys disabled and password authentication enabled, refused TCP connections on port 2022 before authentication. Checkpoint inspection and GPU execution did not occur. No server was restarted. Physical GPU 1 with `CUDA_VISIBLE_DEVICES=1` remains required. Connection details and credentials were not saved in these artifacts.

The owner's 1B-class question is documented in the [research note](../research/KENN_SEAL_RESEARCH_2026-10-13.md#smaller-model-question-13-october). A 1.7–2B challenger is worth considering before 0.8B. The current baseline and architecture guard remain 4B; smaller checkpoints require verified backend compatibility and distinct manifests before any trial. No smaller model was downloaded or selected.

## Result and exact changed files

The runnable pipeline, fixture dry run, asset snapshot, approved pilot validation and scoped tests are measured here. A larger independently reviewed corpus, matching HF checkpoint, actual GPU trials, proxy/gain calibration, learning-efficiency curves, sealed owner grades and grounded M3 adapter measurements remain unavailable. **SEAL's value over ordinary fine-tuning, inference savings and amortization remain unmeasured.** Serving is disabled and there is no promotion recommendation. Grounding, model selection, dependencies, permissions, CI and Live behavior were not changed. Existing unrelated edits, including earlier dirty sections of the plan, were preserved.

Files changed for this request, relative to `products/kenn`:

- `KENN_PLAN.md`: current 4B decision, active MLX comparison lineage, download model and C4 offline experiment queue.
- `docs/research/KENN_SEAL_RESEARCH_2026-10-13.md`: pinned primary research and B.10 limits.
- `docs/runbooks/KENN_SEAL_OFFLINE_EXPERIMENT.md`: this contract, baseline, verification and commands.
- `tooling/scripts/run_seal_experiment.py`: isolated CLI entry point.
- `tooling/seal_experiment/__init__.py`: package contract.
- `tooling/seal_experiment/records.py`: schemas, source/target approvals, partition and budget checks.
- `tooling/seal_experiment/experiment.py`: comparison arms, both updates, review pauses, sealed-independent scoring and blind grading.
- `tooling/seal_experiment/backends.py`: synthetic fixture and immutable, bounded CUDA subprocesses/receipts.
- `tooling/seal_experiment/cuda_worker.py`: local LoRA generation/training and GPU telemetry.
- `tooling/seal_experiment/cli.py`: snapshot, dry run, reviewed run, one-shot final, grading and report commands.
- `tooling/seal_experiment/measurements.py`: grouped M3 receipt analysis, unknown-field handling and common-cost amortization.
- `tooling/tests/test_seal_experiment.py`: review, leakage, numeric, retention, isolation, timeout, cache, cost and CLI examples.
