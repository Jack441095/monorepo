# SEAL evidence for KENN's offline conversational experiment

**Reviewed:** 13 October 2026. **Scope:** KENN's conversational language-model layer, using disposable offline adapters; this is evidence, not a competing work queue.

Sources are the user-supplied PDF of [arXiv:2506.10943v2](https://arxiv.org/abs/2506.10943v2), revised 18 September 2025, and the authors' implementation pinned to [`6d9c9f9ee392c6cc618e771f399d436d190f6ca4`](https://github.com/Continual-Intelligence/SEAL/tree/6d9c9f9ee392c6cc618e771f399d436d190f6ca4). No upstream code, dependencies, models, or experiment datasets were imported.

## What SEAL actually learns

SEAL has two distinct updates. The inner update trains on a generated self-edit and produces a temporary adapted model. The outer update trains the original policy to generate better self-edits, using the adapted model's downstream performance as reward. Generating synthetic answers and fine-tuning once implements synthetic-data SFT, not the learned-policy comparison. The paper uses the same underlying model in both roles and discusses a separate teacher/student variant. [Paper §3.1, Algorithm 1](https://arxiv.org/html/2506.10943v2#S3.SS1)

For outer iteration `t`, sample each edit from policy checkpoint `θ_t`, adapt an isolated copy of `θ_t` to `θ′_t`, and evaluate `θ′_t` on reference tasks. Reinforce selected context-to-edit completions on `θ_t` to obtain `θ_(t+1)`. A candidate's temporary adapter must never become another candidate's starting state or the outer policy checkpoint. Sample new edits and recompute their rewards after the policy changes: reward depends on the current model, so stale trials are not interchangeable. These isolation requirements follow from Algorithm 1 and the paper's on-policy argument. [Paper §3.1](https://arxiv.org/html/2506.10943v2#S3.SS1)

The authors use ReST-EM: sample candidates in the E-step, then apply supervised learning to selected successful completions in the M-step. They report unstable PPO/GRPO experiments. In knowledge incorporation, each round uses 50 contexts, 5 edits per context, and 3 adaptation seeds per edit; the single best edit by mean post-adaptation performance is retained per context. Two rounds are run. Outer SFT uses 2 epochs, batch size 10, learning rate `3e-4`, and LoRA rank 64 / alpha 128. Those are paper settings, not suitable default budgets for an M3 pilot. [Paper §3.1 footnote 2 and Appendix B.2](https://arxiv.org/html/2506.10943v2#A2.SS2)

The pinned implementation makes the separation visible: [`TTT_server.py`](https://github.com/Continual-Intelligence/SEAL/blob/6d9c9f9ee392c6cc618e771f399d436d190f6ca4/general-knowledge/src/inner/TTT_server.py#L292) trains and evaluates a temporary LoRA; [`build_SFT_dataset.py`](https://github.com/Continual-Intelligence/SEAL/blob/6d9c9f9ee392c6cc618e771f399d436d190f6ca4/general-knowledge/src/EM/build_SFT_dataset.py#L20) ranks completions and exports prompt/completion pairs; [`train_SFT.py`](https://github.com/Continual-Intelligence/SEAL/blob/6d9c9f9ee392c6cc618e771f399d436d190f6ca4/general-knowledge/src/EM/train_SFT.py#L39) separately loads a model, trains the policy, and saves merged weights. Temporary adapter cleanup alone is not a checkpoint-integrity test: KENN needs explicit identity checks, fresh trial state, and failure-path cleanup.

## Appendix B.10: cheaper reward, with a narrower claim

The proxy replaces adaptation-and-evaluation reward with a human-written rubric. GPT-4.1 rates length, diversity, quality, and correctness from 1 to 5; their sum is the reward. It examines the passage and generated implications, not the candidate model's post-training answers. The code supports `proxy` and `both` modes and ranks candidates by `proxy_mean`. [Paper Appendix B.10](https://arxiv.org/html/2506.10943v2#A2.SS10), [pinned rubric implementation](https://github.com/Continual-Intelligence/SEAL/blob/6d9c9f9ee392c6cc618e771f399d436d190f6ca4/general-knowledge/src/utils.py#L240), [selection metric](https://github.com/Continual-Intelligence/SEAL/blob/6d9c9f9ee392c6cc618e771f399d436d190f6ca4/general-knowledge/src/EM/build_SFT_dataset.py#L40)

Table 9 reports:

| Reward | Base accuracy | Post-RL accuracy | Reported time |
| --- | ---: | ---: | ---: |
| Full adaptation reward | 32.0% | 47.0% | approximately 6 hours |
| Proxy rubric | 32.0% | 45.6% | approximately 5 minutes |

That is 1.4 percentage points less accuracy and approximately 72 times less reported training time, calculated from Table 9. The appendix does not report proxy/improvement correlation, confidence intervals, grader calibration, or a breakdown proving the same saving for all compute. Its 32.0% baseline also differs from main Table 2's 32.7%; keep each table's denominator and setting intact. These figures are evidence about that experiment, not predicted KENN results. [Paper Appendix B.10](https://arxiv.org/html/2506.10943v2#A2.SS10)

For KENN, deterministic grounding checks and reviewed labels can cheaply screen examples, but replacing GPT-4.1's rubric is an adaptation of the paper. Measure whether the screen predicts actual post-training gain on independent tasks, including false positives and negatives; do not reward a model solely for approving its own answers. Length should be a bounded budget rather than an incentive to pad explanations. Citation presence, schema validity, or checker acceptance cannot establish that a statement is true or that an adapter learned it. These are KENN experiment requirements, not findings demonstrated by B.10.

## What the reported results do and do not establish

The knowledge experiment uses Qwen2.5-7B and no-passage SQuAD QA. Main Table 2 reports single-passage accuracy of 32.7% unchanged, 33.5% passage-only SFT, 39.7% untrained-policy synthetic data, 46.3% GPT-4.1 synthetic data, and 47.0% SEAL. Evaluation uses 200 passages / 974 questions and GPT-4.1 grading. Appendix B.5 reports 750 inner trials per round and approximately 6 hours on two H100 GPUs. This establishes an improvement in that controlled task, not conversational usefulness, source-grounded citations, shorter decoding, or Apple Silicon performance. [Paper §4.2 and Table 2](https://arxiv.org/html/2506.10943v2#S4.SS2), [Appendices B.4–B.5](https://arxiv.org/html/2506.10943v2#A2.SS4)

Prompt choice is a serious confound: Appendix B.11 reports untrained-policy rewrite accuracy of 49.4%, already above the main implications-based SEAL result of 47.0%; applying RL to rewrite reaches 55.6%. Compare ordinary reviewed SFT, validated synthetic SFT, and learned-policy SEAL under matched budgets and prompts before crediting gains to the outer loop. [Paper Appendix B.11, Table 10](https://arxiv.org/html/2506.10943v2#A2.SS11)

Sequential edits still cause forgetting, and training depends on explicit downstream references. The paper proposes broader continual learning and generated evaluation tasks as future work. KENN should therefore split source/task families before variants are created, keep reward/development tasks separate from sealed final tasks, check retention after sequential updates, and retain retrieval and grounding for product evaluation. Learned weights cannot supply a fabricated citation or replace current session evidence. [Paper §5](https://arxiv.org/html/2506.10943v2#S5)

An offline pipeline or dry run can demonstrate schema, budgets, isolation, provenance, and selection behavior. Claim improved learning efficiency only after measured gains per reviewed example or training token; claim improved inference efficiency only after measured useful correct answers per serving cost. Report training cost separately and calculate its amortization against measured serving savings. LoRA does not inherently accelerate decoding, and GPU training times are not M3 serving evidence. Until actual training, blind owner grading, and M3 measurements exist, SEAL's value over ordinary fine-tuning remains unmeasured.

## Smaller-model question, 13 October

The publisher's non-thinking comparison reports the following scores. These are broad benchmarks, not KENN measurements. [Qwen3.5-2B model card](https://huggingface.co/Qwen/Qwen3.5-2B#benchmark-results)

| Model | MMLU-Pro | IFEval |
| --- | ---: | ---: |
| Current Qwen3-4B-2507 | 69.6 | 83.4 |
| Qwen3-1.7B | 40.2 | 68.2 |
| Qwen3.5-2B | 55.3 | 61.2 |
| Qwen3.5-0.8B | 29.7 | 52.1 |

A 1.7–2B challenger is the first size comparison to consider; 0.8B is a more aggressive trial. This is an engineering judgment, not a measured KENN result. Keep the current 4B control and compare blind correctness, units, follow-ups, abstention, retention and grounded useful answers per M3 serving cost. Adaptation may improve domain behavior; it cannot be assumed to recover all capacity lost by shrinking the model.

Qwen3-1.7B retains the Qwen3 family. Qwen3.5-2B uses a hybrid Gated DeltaNet/attention layout with a vision encoder. Both need separately verified training, template and serving compatibility; the current worker's Qwen3/2560-hidden-dimension guard accepts neither smaller model. No model was downloaded or selected. [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B#model-details), [Qwen3.5-2B architecture](https://huggingface.co/Qwen/Qwen3.5-2B#model-overview)
