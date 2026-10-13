# Qwen3 1.7B compatibility evidence — 13 October 2026

The S4 candidate recorded in [KENN_PLAN.md](../../KENN_PLAN.md) is **Qwen/Qwen3-1.7B**, using the publisher’s pretrained/post-trained checkpoint with non-thinking mode pinned. Official metadata and nine rendered-template checks are verified below. Loading its native tokenizer, loading weights, adapter training, answer quality and M3/16 GB delivery remain unmeasured. The existing 4B identity guard remains unchanged; this evidence does not authorize assets, training or selection.

## Identity and provenance

Public metadata and small configuration/model-card text were read from Qwen's official Hugging Face repositories. No weights, native tokenizer data, model directories or dependencies were downloaded or installed. SHA-256 values for small text files were computed from the response bytes in memory. Weight/tokenizer-file hashes below are publisher-reported metadata, not local file verification. Immutable revisions were resolved from the official model metadata API on this date and then used for configuration reads.

| Checkpoint | Immutable revision | Published training stage | Mode |
| --- | --- | --- | --- |
| [Qwen/Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B/tree/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e) | `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` | Pretraining and post-training | Hybrid; explicitly pass `enable_thinking=False` |
| [Qwen/Qwen3-1.7B-Base](https://huggingface.co/Qwen/Qwen3-1.7B-Base/tree/ea980cb0a6c2ae4b936e82123acc929f1cec04c1) | `ea980cb0a6c2ae4b936e82123acc929f1cec04c1` | Pretraining only | Distinct checkpoint; its template does not establish instruction or thinking training |
| [Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/tree/cdbee75f17c01a7cc42f958dc650907174af0554) | `cdbee75f17c01a7cc42f958dc650907174af0554` | Pretraining and post-training | Non-thinking only |

The candidate's model card names `Qwen3-1.7B-Base` as its base model and labels the released chat checkpoint 1.7B. The two repositories must not be substituted for one another. The 4B card says it does not generate thinking blocks. These are publisher statements, not KENN behavior measurements. [1.7B card](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/README.md), [Base card](https://huggingface.co/Qwen/Qwen3-1.7B-Base/blob/ea980cb0a6c2ae4b936e82123acc929f1cec04c1/README.md), [4B card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/cdbee75f17c01a7cc42f958dc650907174af0554/README.md)

All three publish Apache-2.0 license text with SHA-256 `832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e` (11,343 bytes). Model license provenance is separate from permission to train shared weights on Ableton manuals or owner notes. [Candidate license](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/LICENSE), [Base license](https://huggingface.co/Qwen/Qwen3-1.7B-Base/blob/ea980cb0a6c2ae4b936e82123acc929f1cec04c1/LICENSE), [4B license](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/cdbee75f17c01a7cc42f958dc650907174af0554/LICENSE)

## Configuration comparison

Values below come from the immutable official configurations, not from an inferred size label. [1.7B config](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/config.json), [Base config](https://huggingface.co/Qwen/Qwen3-1.7B-Base/blob/ea980cb0a6c2ae4b936e82123acc929f1cec04c1/config.json), [4B config](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/cdbee75f17c01a7cc42f958dc650907174af0554/config.json)

| Field | 1.7B candidate | 1.7B-Base | 4B control |
| --- | --- | --- | --- |
| Architecture / model type | `Qwen3ForCausalLM` / `qwen3` | Same | Same |
| Hidden dimensions / feed-forward dimensions | 2048 / 6144 | 2048 / 6144 | 2560 / 9728 |
| Layers | 28 | 28 | 36 |
| Query / KV heads; head dimensions | 16 / 8; 128 | 16 / 8; 128 | 32 / 8; 128 |
| Vocabulary entries | 151936 | 151936 | 151936 |
| Stored dtype / tied embeddings | BF16 / true | BF16 / true | BF16 / true |
| BOS / config EOS token IDs | 151643 / 151645 | 151643 / 151643 | 151643 / 151645 |
| `max_position_embeddings` (tokens) | 40960 | 32768 | 262144 |
| `rope_theta`; `rope_scaling` | 1000000; null | 1000000; null | 5000000; null |
| Sliding window enabled | false | false | false |
| Config's recorded Transformers version | 4.51.0 | 4.51.0 | 4.51.0 |

The candidate card advertises 32,768 context tokens, its config permits 40,960 positions, and its tokenizer metadata declares 131,072 tokens. These are different metadata fields; none is a measured KENN operating limit. Keep the experiment's explicit context/output caps and count tokens with each model's own pinned tokenizer. [Candidate card](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/README.md), [candidate config](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/config.json), [candidate tokenizer metadata](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/tokenizer_config.json)

## Hash evidence

| File or extracted string | 1.7B candidate SHA-256 | 4B control SHA-256 |
| --- | --- | --- |
| `config.json` bytes | `1ddb5b89ebc90dcb417a45c213d818577e65976454d29385c8f6140771d95197` | `5beea1a4a34c62782bfb2f911c606741a3bab8f92d80a118fa053c28af12e8ba` |
| `tokenizer_config.json` bytes | `d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101` | `a62ff0a2472a0fa1b8eaabcb57c59b58afa42a22831dc141400b6e0cf2b65ce3` |
| Extracted `chat_template` string, UTF-8 | `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8` | `64f85b198065d0fba2a81f37e10ed68161ce2c19a754c7100e67e0ca2ee9c326` |
| `generation_config.json` bytes | `2325da0f15bb848e018c5ae071b7943332e9f871d6b60e2ed22ca97d4cb993d2` | `835fffe355c9438e7a25be099b3fccaa98350b83451f9fd2d99512e74f1ade48` |
| `README.md` bytes | `257e52c419dac2258852643f18af6c974f21f8c6c1b6f371b6cca6201cf29091` | `8e3dd0c3b5b11897cc71092ccfe517bb7a9783479baa3665aad73c8d1a2041cd` |

Sources are the revision-bound [candidate files](https://huggingface.co/Qwen/Qwen3-1.7B/tree/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e) and [4B files](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/tree/cdbee75f17c01a7cc42f958dc650907174af0554). The Base config hash is `1bb33a92c3548fbc68b889b490e810440435253598835bd71dff0396060c12db`, tokenizer-config hash `3c04ed3ca964ea2f6b2b5faf0dc4d31aec1cb1e8b4bcf63f402d295046b422b5`, and template-string hash `87a2728cb8dc9fe424d624542f6060ec05a1d285ebbec578bb078900e33396b5`. [Base files](https://huggingface.co/Qwen/Qwen3-1.7B-Base/tree/ea980cb0a6c2ae4b936e82123acc929f1cec04c1)

Publisher metadata reports the candidate's two BF16 weight files as:

| File | Bytes | Publisher LFS SHA-256 |
| --- | --- | --- |
| [Shard 1](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/model-00001-of-00002.safetensors) | 3,441,185,608 | `169ad53ec313c3a34b06c0809216e4fc072cce444a5d4ff2b59690d064130ed5` |
| [Shard 2](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/model-00002-of-00002.safetensors) | 622,329,984 | `912becff8d60672aa8628ef08c05898d9adf17c2ad4ae3caf99b065622fdeff9` |
| [Native tokenizer data](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/tokenizer.json) | 11,422,654 | `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4` |

The 4B publisher reports the same `tokenizer.json` LFS hash; that shared file does not make the distinct tokenizer configurations/templates interchangeable. The weight files total 4,063,515,592 bytes; storage bytes do not predict GPU allocation or M3 memory pressure. No local challenger checkpoint hash or HF-to-GGUF equivalence attestation exists from this work. [4B tokenizer file](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/cdbee75f17c01a7cc42f958dc650907174af0554/tokenizer.json)

## Static compatibility and remaining execution limits

1. **Existing worker rejects the challenger.** [CudaBackend](../../tooling/seal_experiment/backends.py) binds source hashes, full checkpoint hash and reviewed HF-to-served equivalence before requiring `model_type=qwen3` and `hidden_size=2560`. Both 1.7B variants have 2048 hidden dimensions. [CLI](../../tooling/seal_experiment/cli.py) also pins the served 4B model name. Merely editing a manifest or launching the worker directly would evade the existing model boundary; neither was done.

2. **Native architecture support is plausible, execution is unverified.** Transformers 4.51.0 includes Qwen3's causal-LM class and linear attention/MLP projections. The worker already uses native `AutoModelForCausalLM`, BF16, PEFT `target_modules="all-linear"`, and local-only loading. These source/config facts support investigating the same training family; they do not prove adapter construction, gradients, save/reload, BF16 device support or generation for this checkpoint. [Transformers Qwen3 implementation](https://github.com/huggingface/transformers/blob/v4.51.0/src/transformers/models/qwen3/modeling_qwen3.py), [PEFT all-linear support](https://huggingface.co/docs/peft/en/developer_guides/lora), [worker](../../tooling/seal_experiment/cuda_worker.py)

3. **Dependency ranges are insufficient evidence of a working environment.** Qwen's cards require Transformers at least 4.51.0; [requirements-training.txt](../../apps/backend/requirements-training.txt) allows 4.45 through versions below 5. That range admits versions without Qwen3. The local `python3` metadata reported Torch 2.12.1, Transformers 5.12.1, PEFT 0.19.1 and safetensors 0.8.0; its Transformers version is outside the declared range. This is an observation about the local interpreter, not the existing CUDA training environment. No packages were changed, and no claim about CUDA package compatibility follows. [Candidate requirements](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/README.md)

4. **Non-thinking templates differ.** Both 1.7B templates append an empty `<think>\n\n</think>\n\n` block to the assistant generation prefix when `enable_thinking=False`; 4B's template appends only its assistant header. The candidate uses `Qwen2Tokenizer`, pad token `<|endoftext|>` and EOS `<|im_end|>`; its generation EOS IDs are `[151645, 151643]`. Base's configured EOS is 151643. These exact fields belong in each model's distinct identity and generation receipts. [Candidate tokenizer metadata](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/tokenizer_config.json), [candidate generation config](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/generation_config.json), [Base tokenizer metadata](https://huggingface.co/Qwen/Qwen3-1.7B-Base/blob/ea980cb0a6c2ae4b936e82123acc929f1cec04c1/tokenizer_config.json), [4B tokenizer metadata](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/cdbee75f17c01a7cc42f958dc650907174af0554/tokenizer_config.json)

5. **Rendered string masking passed; native token masking is unmeasured.** Existing Jinja2 3.1.6 rendered the three pinned templates with single-turn, system-plus-user and multi-turn synthetic conversations: nine checks passed. Each full string began with its generation prefix and left exactly the assistant answer plus the end-of-message marker as its suffix. No native tokenizer was loaded, so the worker's additional token-ID-prefix check remains necessary. Tests that already reject token-prefix mismatches remain active. [encode_targets and its tests](../../tooling/tests/test_seal_experiment.py)

6. **Serving and useful-answer costs are unmeasured.** This CUDA worker requires physical GPU 1 and is not a Mac execution path. No 1.7B quantization, conversion, GGUF/MLX adapter compatibility, correct-answer improvement, retention result, latency, memory-pressure result or production recommendation was produced. Retrieval, grounding and proposal policy retain the existing product role. The approved pilot and lunch receipts were not changed. [Offline runbook](../runbooks/KENN_SEAL_OFFLINE_EXPERIMENT.md)

## Scoped verification

`KENN_LIVE_BACKEND=fake python3 -m pytest -q products/kenn/tooling/tests/test_seal_experiment.py -k 'training_masks_prompt_tokens or token_prefix_mismatch or gpu_guard_runs_before_importing'` passed **7 tests**, with 72 deselected. The nine in-memory Jinja rendering checks also passed. These verify current masking/GPU boundaries and template strings; they are not challenger model execution tests. No training, provider calls, GPU work, asset acquisition or selection ran.

On resume, the immutable configuration, tokenizer-configuration, generation-configuration, model-card and license bytes were read again for all three revisions. Every previously recorded metadata hash matched; all nine rendered-string prefix checks passed again. The receipt is ignored `.runtime/seal-preparation-verification/qwen-metadata-rechecked.json`. This remains a metadata/string check: native tokenizer IDs, weights, adapters and serving were not executed.
