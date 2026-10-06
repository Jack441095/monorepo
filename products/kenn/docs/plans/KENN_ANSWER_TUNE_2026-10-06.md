# KENN answer tune: status at 11:50, 6 Oct 2026

This is the "Answer fine-tune on a 4B, agreed 5 Oct 2026" section of `KENN_PLAN.md`. The teacher pass was cut at 225
questions at 11:00, then run for about 40 more minutes and stopped at 329 questions, because Jack was travelling
for work.

## Where it stands

| Step | State |
| --- | --- |
| Questions from approved notes, leaving out the probe and held-out sets and anything near them | Done: 977 questions from 385 notes |
| Teacher answers from `qwen3:32b` through KENN's real answer path, gate-accepted, 128 tokens or fewer | Stopped at 329: 174 kept |
| Jack grades about 40 kept answers | Page is ready, nothing graded yet |
| LoRA on GPU 0 in `c6/venv`, with early stopping | Ready to start, not started (see below) |
| Merge, GGUF Q4_K_M, serve through Ollama on the Mac | Scripted inside the training job; the Modelfile is ready |
| 3 probe runs plus held-out against the plain 4B, on a quiet Mac on mains power | Waiting for the tune |
| Keep only if the probe and held-out both rise, the median is no slower, and the negative-advice guard holds | Waiting |

## Results so far

**Questions** (`build_brain_style_corpus.py questions`)

- 977 questions from 385 notes.
- The leak guard is strict. It left out 364 of the 768 approved notes, because the probe and held-out answers are
  built from them, and it dropped 639 questions that were close to a test question. "Close" means a word overlap of
  0.6 or more, or an embedding cosine of 0.60 or more.
- The 0.60 cosine was calibrated by hand on 6 Oct. Pairs that ask about the same thing in different words scored 0.62
  (a precedence question) and 0.83 (a sidechain question). Unrelated pairs scored 0.38 to 0.48.

**Teacher answers** (329 of the 977 questions)

| | At 11:00 | Final, 11:50 |
| --- | --- | --- |
| Questions recorded | 225 | 329 |
| Answers kept | 114 (51%) | 174 (53%) |
| Notes the kept answers come from | 71 | 106 |
| Train / valid | 105 / 9 | 156 / 18 (valid from 10 held-back notes) |

- None was dropped for hitting the 128-token cap.
- The split holds back whole notes for validation, so related questions never sit on both sides.
- Training targets now have a median of 87 words and a longest of 104, with the Sources block removed (next
  section). With it, the median was 103 words.
- At about 2.5 questions a minute, the remaining 648 questions would take about 4 more hours, for roughly 340 more
  examples. Rerunning the answers step resumes from `progress.jsonl`.

**Correctness.** The gate checks that an answer is grounded in the excerpts, not that it is right. In the 2-question
smoke test it let one answer through that gave Utility an HP/LP filter. Utility has no filter. The grades are the
only correctness check before training.

## Code (branch `draft/answer-tune`, not merged)

- `5455e1a5`, `698ede1d`: the question builder with the leak guard, and the answers step. The answers step is
  resumable from `progress.jsonl` and keeps only answers that stopped on their own, not ones cut off by the cap.
  The same commits add `--eval-every` and `--patience` early stopping to `train_kenn_command_lora_cuda.py`. When
  training stops early, it restores the best adapter before merging.
- `15f4519b`: if the tunnel drops, KENN falls back to its template answer. The questions it answered that way are no
  longer recorded as done-and-rejected, so a rerun asks them again.
- `cdaaf334`: training targets leave out the "Sources:" block. KENN's `llm_rewrite._with_sources` appends that block
  after the model answers, and the rewrite prompt tells the model not to write it. Training on it would teach the 4B
  to spend about 35 of its 128 tokens on a list KENN adds anyway, and push more answers into the cap. `examples.jsonl`
  keeps the full text. **The split written at 11:00 still had Sources in its targets; the 11:50 split does not** (0 of
  156 train targets contain it).
- Early stopping has not run on a GPU yet.

## Not started: training on the box

Copying the training data to the box and starting the job was refused by the session's permission check (shared
resource). Jack needs to run it or approve it. Everything is staged:

- Data on the Mac: `kenn-evaluation-data/2026-10-06-answer-tune/answers/train.jsonl` and `valid.jsonl`.
- Trainer: `tooling/scripts/train_kenn_command_lora_cuda.py` from `draft/answer-tune`. The box copy is older and has
  no early stopping.
- Job script: `kenn-evaluation-data/2026-10-06-answer-tune/answer1_box.sh`. It does five things:
  1. waits until GPU 0 is free, which happens once the 32B's 5-minute keep-alive lapses;
  2. trains 3 epochs with an eval every 4 steps and a patience of 2;
  3. converts the merged model to a bf16 GGUF;
  4. quantises it to Q4_K_M;
  5. deletes the intermediate files.
- Disk: `/mnt/data` has 24 GB free. The job's peak is about 16 GB: an 8 GB merged model plus an 8 GB bf16 GGUF.
  Afterwards only the Q4 (about 2.5 GB) and the adapter remain.

To start it, run on the Mac from the answer-tune worktree (`<box>` is the usual ssh target and port):

```bash
O=/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/kenn-evaluation-data/2026-10-06-answer-tune/answers
ssh <box> 'mkdir -p /mnt/data/kenn-bakeoff/c6/data_answer1'
scp $O/train.jsonl $O/valid.jsonl <box>:/mnt/data/kenn-bakeoff/c6/data_answer1/
scp tooling/scripts/train_kenn_command_lora_cuda.py $O/../answer1_box.sh <box>:/mnt/data/kenn-bakeoff/c6/
ssh <box> 'cd /mnt/data/kenn-bakeoff/c6 && (setsid nohup ./answer1_box.sh > answer1_box.out 2>&1 < /dev/null &)'
```

With 156 examples, one epoch is about 20 optimiser steps, so training should take minutes, not hours. When
`answer1_box.out` says `BOX DONE`, copy `answer1-q4km.gguf` into `kenn-evaluation-data/2026-10-06-answer-tune/` and run
`ollama create kenn-answer1 -f Modelfile.answer1` there. The Modelfile is the plain 4B's template with `FROM` changed.

## Grading

40 answers, sampled with seed 0 from the 114 kept at 11:00 (all 40 are still in the final 174):
https://claude.ai/artifact/BrcSDREy6ZLLRxskoDdq3J

Each card shows the question, the excerpts the model saw, and the answer, with Good / Fixable / Wrong buttons and a
note. Grades save as you go, so it can be done in pieces. Which sample id maps to which example is in
`answers/grading_sample.json`.

How the grades decide what happens:

- **Mostly good.** Train on all 174, or finish the teacher pass first for more data.
- **More than a few wrong.** Drop the wrong ones from `train.jsonl`. Then decide whether the gate needs a check for
  the kind of error that got through, before generating more answers.

## Decisions for Jack

1. Start the box job above now on 156 examples, or finish the teacher pass first (about 4 hours, about 510 examples).
   156 is small. The 25 Sept style LoRA had 345 examples and failed, though for other reasons: it was trained on its
   own answers and its targets were long.
2. Whether to train before grading. The plan says grade first. Training first only costs GPU time, and nothing ships
   until the grades and the benchmark are both in.
