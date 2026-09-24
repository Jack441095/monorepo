# C6 LoRA pilot: qwen3.5:4b fine-tuned for the command planner (2026-09-23)

The owner chose `qwen3.5:4b` as the C6 base (see the C2 GPU evidence addendum). This is the first fine-tune: one
epoch on a synthetic, leak-guarded corpus, scored through KENN's production planner path on the same 124 cases as C2.

## Result

**The fine-tuned model with the compact prompt beats the stock model with the full prompt.**

- **It asks for clarification every time it should (30/30).** Only the deterministic parser did that before.
- **It accepts a third as many wrong plans (5 vs 15).**
- **The trade-off:** it now also asks about some clear commands, so run 2 should retune the corpus balance.

| Planner (all on GPU 0, bf16, thinking off, same 124 cases) | Correct | Accepted | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted | p50 |
|---|---|---|---|---|---|---|---|
| Stock Qwen3.5-4B + full prompt (today's candidate) | 65.3% | 87.1% | 19/30 | **62/94** | 13/24 | 15 | 1.12 s |
| Stock Qwen3.5-4B + compact prompt | 4.0% | 14.5% | 4/30 | 1/94 | 1/24 | 1 | 3.59 s |
| **Fine-tuned (run 1) + compact prompt** | **68.5%** | **91.1%** | **30/30** | 55/94 | **15/24** | **5** | **0.96 s** |

- **The stock model scores 4% with the compact prompt.** Without the long instructions it does not know the plan
  format. The compact prompt works only with a model that learned the format, which is what the fine-tune adds.
- **The import path is faithful.** The stock weights served through my import path scored 65.3%, against 66.1% for
  Ollama's library `qwen3.5:4b` (Q4_K_M) in C2.
- **Where run 1 fails:**
  - It asks instead of acting on clear commands: mute 5, device parameter 5, insert 4, rename 3, solo 2, focus-device 1.
  - Two-part requests collapse to one action: "recipe" became solo or mute in 4 cases.
  - 11 plans were rejected for missing exact fields (track index or name, device and parameter fields, return index).

## Corpus

`build_kenn_command_corpus.py --variants 8 --scenarios 4 --include-drafted --prompt compact` produced 2,208 records,
split 1,987 train and 221 valid.

- **Seeds:**
  - 48 reviewed seeds.
  - 21 drafted clarify seeds (`drafted_command_seeds.py`, owner review pending). They cover requests with no amount
    or no clear referent, written in different idioms and track names from the evaluation phrasings.
- **Variants:** 4 track-name scenarios × 8 natural variants, with no "(variant N)" filler.
- **48% of records are "clarify"** (25% before the drafted seeds).
- **Targets are compact:** no schema constant and no null fields, about 31 tokens.
- **Leak guard:** every query is checked, case- and punctuation-insensitively, against the shadow holdout and both
  natural holdouts. It caught one real overlap (my drafted candidate "create a return track"), which was reworded.
- **Compact prompt:** an ~80-token system prompt (`KENN_LLM_COMMAND_PROMPT=compact`) instead of 1,341 tokens.
  Median record length drops from 1,944 to 694 tokens.

## Training

| | |
|---|---|
| Base | `Qwen/Qwen3.5-4B` (Apache-2.0), fetched on the box via hf-mirror.com. Both shards' SHA-256 match Hugging Face's published LFS hashes. |
| Where | GPU box, GPU 0 only (RTX 4090 D), user-level venv under `/mnt/data/kenn-bakeoff/c6`, no system changes, no restarts. Only the trainer script and the validated text records were sent, never KENN source or audio. |
| Method | `train_kenn_command_lora_cuda.py`: LoRA r=16, α=32, all linear layers (248 modules, 0.77% of parameters), bf16, gradient checkpointing, loss on the assistant turn only, thinking-off template. |
| Schedule | 1 epoch, 249 optimizer steps (batch 2 × accumulation 4), lr 2e-4 cosine with warm-up. |
| Cost | 17 min, peak 13.7 GB. |
| Validation loss | 2.03 → 0.025 (step 62) → 0.001 (end). The validation split comes from the same synthetic distribution, so this shows the format was learned, not that it generalises. The 124-case evaluation measures that. |

The Mac could not train this model. mlx-lm on the M3 with 16 GB ran out of GPU memory with 4 or more adapted layers,
even at 700 tokens, and a single layer ran at about 14 s per step.

## Serving path (and a bug fixed on the way)

1. Training loads Qwen3.5 text-only, so PEFT's merged save dropped the multi-token-prediction layer.
   - llama.cpp then refused the GGUF: `blk.32.attn_norm.weight not found`.
   - `merge_lora_into_checkpoint.py` fixes this. It merges `W + (α/r)·B·A` into a copy of the original, complete
     checkpoint (all 738 tensors), and fails unless every adapter pair lands exactly once.
2. llama.cpp's converter makes a bf16 GGUF (441 tensors, same as stock).
3. `ollama create` uses the stock model's `RENDERER`/`PARSER`/`PARAMETER` lines, so the prompt format and sampling
   settings are identical.
   - Ollama 0.34.2 quantises only safetensors imports, and on Linux that needs its MLX runtime, which is not
     available. So `llama-quantize` (built on the box's CPU) makes the Mac's Q4_K_M copy.
   - Q4_K_M GGUF: 2.78 GB, SHA-256 `2abe9e03d66b19aa3aa2e8f8c9443f12828679cd24d802308a6dbe878647d874`.

## Caveats

- **Everything here is still owner-review pending.**
  - The drafted clarify seeds and 100 of the 124 evaluation phrasings are Claude-drafted, pending owner review.
  - The corpus is synthetic and narrow (validation loss 0.001).
- **One run, one seed.** A few points either way is within noise.
- **Not a promotion.** The fine-tune stays behind the shadow flag; C4 promotion is the owner's decision.
- **Serving detail.** The stock Modelfile ships `presence_penalty 1.5`, which KENN's planner calls do not override.
  Kept identical across all rows here. Whether turning it off helps JSON plans is untested.

## Next

1. **Run 2:** bring the clarify share down to ~35% and add explicit-command variety (mute/solo/rename/device/insert
   and two-part requests), then re-score.
2. **Mac latency** of the Q4_K_M fine-tune with the compact prompt (this document's addendum).
3. **Owner review** of the 21 drafted clarify seeds and the 100 drafted evaluation phrasings.

## Addendum: Mac latency (M3, 16 GB, after midnight, Live idle)

The Q4_K_M fine-tune was copied to the Mac (SHA-256 verified) and created in Ollama with the stock settings.

| Same first 40 cases, production path | Correct | p50 | p95 |
|---|---|---|---|
| Stock `qwen3.5:4b` + full prompt | 75.0% | 3.3 s | 11.6 s |
| **Fine-tuned run 1 + compact prompt** | **90.0%** | 4.4 s | **7.5 s** |

Profile of single calls with the snapshot changed before each command, as after an applied edit:

| | First call after load (prompt) | Later calls (prompt) | Generation | Median total |
|---|---|---|---|---|
| Stock + full prompt (2,030 tokens) | 7.0 s | ~2.0 s | 30–44 tokens at ~24 tokens/s | 3.6 s |
| Fine-tuned + compact prompt (780 tokens) | 2.1 s | ~2.1 s | 33–47 tokens at ~25 tokens/s | 3.6 s |

- **On this Mac the compact prompt does not make later commands faster.** After any change to the prompt, Ollama
  spends ~2 s re-processing this hybrid model's prompt, whether it is 780 or 2,030 tokens long. It only helps the
  first command after the model loads (7.0 s → 2.1 s).
- **The fine-tune's win on the Mac is accuracy and safety, not speed.**
- **Load matters more than the model choice.** Generation ran at ~24 tokens/s here, against ~10 tokens/s earlier in
  the evening with Live busy, so Mac latency swings more with load than with any choice in this document. Latency
  figures must state the machine's state.
- **The fine-tune writes `"relative":false` in every plan** (3–4 tokens), because the training targets keep false
  values. That is harmless and could be trimmed in a later corpus.

## Addendum: run 2 and dB volumes (2026-09-24)

**Run 2** was the same recipe with fewer variants per clarify seed (`--clarify-variants 5`): 1,812 records, 36%
clarify, 204 steps, 13 min, validation loss 1.79 → 0.0007.

- **It scored worse: 48.4%.** It still asked when it should (30/30) but acted on only 30 of 94 clear commands.
- **The raw replies explained it.** Run 2 wrote volume changes in user units (`"relative":true,"unit":"dB","value":3.0`
  for "bring the bass up 3 dB").
  - The old contract rejected those, and the repair pass turned them into clarifications.
  - Run 1's "correct" volume plans held guessed values (0.707). The scorer checks the action and track, not the value.
- **KENN now accepts dB volumes and converts them.** `validate_llm_plan` accepts `set_volume` in dB, absolute or
  relative, and converts with the rule parser's own mapping (10^(dB/20); a relative change scales the snapshot
  volume; results outside (0, 1] are rejected).

Re-scored with the dB conversion (GPU, 124 cases):

| | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted |
|---|---|---|---|---|---|
| Stock + full prompt | 65.3% | 19/30 | 62/94 | 13/24 | 15 |
| **Run 1 + compact prompt** | **68.5%** | **30/30** | 55/94 | **15/24** | 5 |
| Run 2 + compact prompt | 54.8% | 30/30 | 38/94 | 11/24 | 3 |

- **Run 1 stays the best fine-tune.**
- **The corpus is the bottleneck, not the clarify balance.** Two runs with a small data change differ by 17 points on
  clear commands. There are only 37 reviewed action seeds, while the evaluation uses slang, fragments and colloquial
  phrasings. Run 3 needs more varied examples of clear commands, especially mute/solo, device parameters, inserts
  and two-part requests. Those would be new drafted seeds for owner review.
- **The scorer does not check values.** A value-aware check needs expected values in the holdout.

## Addendum: run 3, drafted clear-command seeds (2026-09-24)

Run 3 added 19 drafted clear-command seeds in varied idioms (mute/unmute, solo/unsolo, volume in dB, pan) and mixer
state in the training snapshots.

- **Corpus:** 2,684 records, 34% clarify, mute examples 224 (was ~55).
- **Training:** 302 steps, 20 min, peak 14.5 GB; validation loss 1.79 → 0.0003.

| GPU, 124 cases | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted |
|---|---|---|---|---|---|
| Stock + full prompt | 65.3% | 19/30 | 62/94 | 13/24 | 15 |
| Run 1 + compact prompt | 68.5% | **30/30** | 55/94 | 15/24 | **5** |
| **Run 3 + compact prompt** | **72.6%** | 29/30 | 61/94 | **16/24** | 13 |

- **Where the new seeds landed, run 3 fixed things.** Mute 5/5, pan 8/8, volume 11/12, slang 4/4, colloquial 4/4,
  fragments 3/3, vague amount 9/9. Over-asking fell to 7 cases (from 23 in run 1).
- **It also learned a dangerous shortcut.** Transport commands became mute (play/stop → `set_mute` in 5 cases);
  224 mute examples outweighed the few transport ones.
- **Still at 0 for run 3:** transport, rename, sends, device parameters, EQ, two-part requests.
- **Wrong plans accepted rose from 5 to 13**, so run 3 is more accurate but less safe than run 1.
- **Lesson: balance across every action matters, not just more examples.**
- **Run 4 needs:**
  - drafted seeds for transport, rename, sends, device parameters, EQ and two-part (recipe) requests;
  - per-action balancing in the corpus builder;
  - the same 124-case check, with "wrong plans accepted" as the promotion gate.

## Addendum: run 4, balanced corpus (2026-09-24)

Run 4 added drafted seeds for the command types with no or few reviewed seeds. All are owner review pending, and
all labels validate in all four scenarios.

- **Seeds:** transport play/stop (contrasted with mute: "Kill playback" vs "Kill {track}"), rename, sends, device
  parameters, EQ and two-part recipes.
- **Balance:** `--max-per-action 160` caps every action except clarify, round-robin across seeds.
- **Corpus:** 3,432 records, 38% clarify.
- **Training:** 387 steps, 25 min, peak 14.6 GB; validation loss 1.93 → 0.0003.

| GPU, 124 cases | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted |
|---|---|---|---|---|---|
| Stock + full prompt | 65.3% | 19/30 | 62/94 | 13/24 | 15 |
| Run 1 | 68.5% | 30/30 | 55/94 | 15/24 | 5 |
| Run 3 | 72.6% | 29/30 | 61/94 | 16/24 | 13 |
| **Run 4** | **84.7%** | 29/30 | **76/94** | **19/24** | **5** |

- **Newly solved:** transport 4/4, rename 3/3 and sends 3/3 (all 0 before). Mute, pan, volume, slang, fragments and
  vague amounts are near-perfect.
- **The mute shortcut is gone:** wrong plans accepted fell back to 5, as low as run 1.
- **Still weak:**
  - EQ 0/3: rejected for inexact band, frequency or device fields.
  - Device parameters 2/5.
  - Two-part requests 1/3.
- **Caveat: pattern-level contamination.** Runs 3 and 4's drafted seeds were written after seeing which categories
  and failure types the 124-case set exercises. Their wording and track names differ, and the guard blocks exact
  matches, but the 84.7% is still optimistic. A clean number needs a fresh evaluation set written by someone other
  than the author of the training data.

**Serving fix found on the way.** `validate_llm_plan` checked each recipe step on a copy but returned the original
steps, so after the dB change a "-2 dB" volume step would have reached the executor unconverted. Validated recipes
now carry the converted steps, with a test.

Q4_K_M GGUF: SHA-256 `187b2a9a85021637dfbcead95b9c010454fe1908e204a275fecbd36552c2c1e7`.

## Addendum: run 5, production-shaped evidence (2026-09-24)

Run 5 used run 4's balanced corpus rebuilt with `--production-evidence`.

- **Evidence per record:** the evidence the gateway attaches, built by production's own `_llm_planner_snapshot`:
  single-track, with the real Live parameter lists recorded from the owner's set (Compressor, EQ Eight).
- **Labels:** point at real parameter indices (Compressor Threshold 1, not 0).
- **Length:** prompts are bounded at 24,000 characters, as in production; up to ~5,000 tokens.
- **Training:** batch 1 × accumulation 8 with loss on answer tokens only (`--sparse-logits`); 387 steps, 68 min,
  peak 12.1 GB.

**Mac check of run 4, same 124 cases, compact prompt:** 83.1% correct (GPU 84.7%), clarify 28/30, curated 18/24,
6 wrong plans accepted; p50 6.5 s, p95 17.4 s, with 14 repairs. It ran alongside a test run.

Scored with `--production-snapshot` (as the gateway):

| GPU, 124 cases | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted | EQ | Two-part (same action) | Device params |
|---|---|---|---|---|---|---|---|---|
| Stock + full prompt | 65.3% | 20/30 | 61/94 | 14/24 | 17 | 0/3 | — | — |
| Run 4 | **84.7%** | 29/30 | **76/94** | **19/24** | 6 | 0/3 | 1/3 | **3/5** |
| Run 5 | 82.3% | 29/30 | 73/94 | 15/24 | **2** | **3/3** | **3/3** | 1/5 |

- **Gains in run 5:** EQ went from 0/3 to 3/3 once the model saw production-shaped evidence. Same-action two-part
  requests ("mute the hats and the snare") went to 3/3. Run 5 is the safest yet, with 2 wrong plans accepted.
- **Losses in run 5:** it now asks too often on device parameters and inserts (8 over-asks). Curated fell to 15/24.
  Cross-action two-part requests are 0/3.
- **Neither run dominates.** With one seed per run, a few points either way is within noise.
- **Next:** put the corpus's evidence-bearing device examples in balance with clarify, and use a fresh,
  independently written evaluation before choosing a model for C4.

## Addendum: parameter evidence for device requests only; run 6 (2026-09-24)

**Gateway change.** `_llm_planner_snapshot` used to attach a track's full parameter lists to *every* planner
request on that track. "mute the bass" carried ~5,000 tokens because Bass has an EQ Eight (84 parameters), which
costs seconds of prompt time on the Mac. Evidence is now attached only for device requests, meaning any of:

- the parsed intent names a device or parameter;
- the request uses device vocabulary (compressor, EQ, threshold, band 2A, Hz, width, ...);
- the request names a device on that track.

The corpus builder applies the same rule through the gateway's code. In the run 6 corpus, 966 of 3,432 records
carry evidence (was 2,358), and the median record is 478 tokens (was 590).

**Test hygiene.** Two server smoke tests that failed in full-suite runs were not machine load, as first noted.
`test_planner_bakeoff` let `run()` write LLM settings into `os.environ`, and later tests then tried to reach a model
and timed out. The test now keeps the environment clean; the suite is 1,542 passed.

**Box access.** The GPU box drops rapid successive SSH connections. All box work now goes through one persistent
multiplexed connection.

**Run 6 results** (run 5's corpus under the device-only evidence rule; 387 steps, 55 min):

| 124 cases, production-style scoring | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted | p50 |
|---|---|---|---|---|---|---|
| Run 4 (GPU) | **84.7%** | 29/30 | **76/94** | **19/24** | 6 | 1.08 s |
| Run 5 (GPU) | 82.3% | 29/30 | 73/94 | 15/24 | **2** | 1.18 s |
| Run 6 (GPU) | 82.3% | 29/30 | 73/94 | 18/24 | 6 | 0.92 s |
| Run 6 (Mac, Q4_K_M) | 79.0% | 29/30 | 69/94 | 17/24 | 4 | 6.71 s (p95 18.0 s, 15 repairs) |

- **Corpus tweaks have hit diminishing returns.** Runs 4–6 sit within 82–85%, and with one seed per run those gaps
  are within noise. Each tweak fixes one category and disturbs another: run 6 keeps EQ 3/3 but newly mistakes
  mute/solo for rename in 3 cases.
- **No measurable Mac difference from the evidence rule here.** Run 4's Mac check used the plain harness (no
  evidence at all), so it cannot show the rule's gain over the old attach-everything behaviour. Mac p50 is 6.5–6.7 s
  either way.
- **What limits progress now is not training:**
  - an evaluation written independently of the training data;
  - owner review of the drafted seeds and evaluation phrasings;
  - the C4 promotion decision.
- **Recommended candidate:** run 4 (best overall and on curated cases). Run 5 is the safest if wrong plans accepted
  is weighted above coverage.

Q4_K_M SHA-256: run 6 `81f49a8a6f5df992fc7207fed3218fdf84da3b27d4b52ee2169836998917cc5a`.

## Addendum 2026-09-24: volume labels used the wrong fader maths

KENN converted dB with 10^(dB/20), treating 1.0 as 0 dB. Live's fader puts 0 dB at 0.85 and +6 dB at 1.0.
Two corpus seeds labelled absolute volume as fader values under that maths ("Set Bass Synth level to minus nine
dB" → 0.355, "Bring the FX Return up to 0 dB" → 1.0), and their variants went into every run. A spot check of
run 4 on the Mac: five of six volume commands came back in dB (converted correctly), but "set Drum Bus level to
0 dB" came back as 1.0, which Live plays at +6 dB. The scores above compare actions and tracks, not values, so they
stand; the value error is separate. The seeds now say dB and KENN converts with `core/volume_law.py`. Any future
run needs a corpus rebuilt after this fix.

## Addendum: run 7, dB volume labels (2026-09-24)

Run 7 is run 4's recipe (`--variants 8 --scenarios 4 --include-drafted --prompt compact --max-per-action 160`) rebuilt
after the volume fix, so every volume label is in dB (160/160) and KENN converts with Live's measured fader law.
3,168 records, 33% clarify; 357 steps, 24 min on GPU 0, validation loss 1.73 → 0.0005; Q4_K_M 2.78 GB.

| GPU, 124 cases | Correct | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted |
|---|---|---|---|---|---|
| Run 4, plain | 84.7% | 29/30 | 76/94 | 19/24 | 5 |
| Run 7, plain | 78.2% | 29/30 | 68/94 | 17/24 | 4 |
| Run 4, production evidence | 84.7% | 29/30 | 76/94 | 19/24 | 6 |
| Run 7, production evidence | 82.3% | 29/30 | 73/94 | 18/24 | 4 |

- **Volume values fixed.** A 9-command volume probe: run 7 sets "0 dB" to 0.85 (0 dB in Live) in all three cases; run 4
  sets all three to 1.0, which is **+6 dB**. The 124-case score compares actions and tracks only, so it never saw this.
- **Better:** EQ 3/3 (run 4: 0/3), focus 5/6, insert 3/4.
- **New and serious:** "solo the bass", "bass solo" and "unsolo the bass" resolve to **Drum Bus**: the right action on the
  wrong track. Also weaker on mute (3/5), multi-step (0/3) and natural requests (4/7).
- **Decision:** run 7 is not promoted to shadow; run 4 stays (shadow only, no writes). Run 8 should keep the dB labels
  and add contrast seeds for overlapping track names ("bass" vs "Drum Bus"), and the scorer should check values
  (expected dB for volume cases), not only actions and tracks.
