# Cloud session handoff, 5 Oct 2026

Jack is travelling, so the next KENN session runs in the cloud on Tuesday 6 Oct. This page covers where things stand, what you can do
without the Mac, the rules, and how to hand the work back so Jack can pull it locally.

## The goal and where it stands

The only goal right now is KENN's 15 s / 70% local-delivery gate. To pass, at least 31 of the 44 answer-expected rows
in the 47-question probe (`products/kenn/tooling/scripts/probe_advanced_questions.py`) must be accepted from the model
in 15 s or less, in three clean runs in a row. The gate counts rows with `expect == "answer"`,
`delivered_by == "model"` and `final_seconds <= 15`.

**It has not passed.** The last three runs scored 31/44, then 27/44 twice. Never report it as moved unless a full probe
run on the Mac says so.

Most misses look like this: the background upgrade runs, and then the model's answer is rejected, so the template stays.
As of `fcd2914f` and `2be6a7c6`, every rejected upgrade carries the check that rejected it (`rejection_reason` on each
probe row, with counts in `overall.rejection_reasons`). The first probe run with reasons was going on the Mac as this
was written. Its result goes under the probe item in the plan.

## Next steps come from the plan

`products/kenn/KENN_PLAN.md` is the single roadmap. Work from its **"15 s gate path, 5 Oct 2026"** checklist at the
end, taking the first unticked item you can do from the cloud. Tick `- [x]` with commit hashes as items land, and don't
start a parallel plan or ticket list.

Items you can do from the cloud, in plan order:

1. **Review follow-ups** (from DeepSeek's sign-off on the rejection-reason work):
   - The rejection-reason tests stub the path. Add one that goes through the real `make_answer`, then
     `answer_upgrades`, then the probe row.
   - Inline rejections (`KENN_LLM_BACKGROUND=0`) aren't counted. Fall back to `validation["warnings"][0]`.
   - `_log_generation_outcome` reads `validation.get` outside its `try`. Move it in.
   - `packages/chat/tests/conftest.py` matches on `nodeid.split("tests/", 1)`, so it depends on the checkout path.
     Match on the trailing `file::test` instead.
   - Poll-transport errors in the probe aren't counted as a reason.
   - Split "generation returned no answer" into two reasons: the request failed or timed out, or the answer failed
     the structure check. Until then, nobody can tell whether truncation (audit finding 2) is the cause.
2. **Stop a template counting as a model answer.** Checked 5 Oct: no row in the last four runs was counted this way, so
   it's a correctness fix, not a gate fix. In `chat_answer.py`, around lines 2646–2676, `llm_enhanced` stays
   True after the quality gate swaps in `weak_match_answer`. That is finding 4 of the 5 Oct code audit.
3. **Unsupported measurements prompt fix.** The prompt and draft snippets invite the model to repeat earlier numbers,
   which the measurement check then rejects. One candidate is to strip numbers from the draft snippet. The checks
   themselves stay as they are (see the fixed values below).
4. **Answers that fit 128 tokens.** Start from branch `draft/answer-fits-128-tokens` (`6d670900`, `61c4206a`). The
   128-token cap stays: changing it is Jack's call. The fix is to make answers finish within the cap.
5. **Advice questions that name a track go to the model.** "What's your advice on drum bus compression?" is routed
   to Live inspection and answered "'Drum Bus' has: Compressor.", so the model is never asked. (Repeating the
   template work, from the audit, was dropped: it costs 70–120 ms. See the plan.)

Work on one item per branch: `draft/<short-name>` off `main`.

## What the cloud can and can't run

- **Can:** edit code; run unit tests; run `products/kenn/tooling/scripts/ci_verification.sh`, the same script kenn-app
  CI runs (Python 3.13, `pip install -r products/kenn/apps/backend/requirements.txt`). On a clean checkout there's no
  `data/index/CURRENT`, so tests that need the index skip, both in the backend and in the eight chat tests listed in
  `packages/chat/tests/conftest.py`. Expect 4229 passed / 130 skipped in the backend and 77 passed / 8 skipped in chat.
- **Can't:** run the probe or measure timing. The probe needs the Mac's Ollama model, the local index and fake Live.
  Any "this should help the gate" claim stays a hypothesis until Jack reruns the probe locally. Say that in the plan
  note and the commit message, not "fixed".
- **GPU box:** only if Jack has finished the setup. Branch `draft/gpu-box-wrapper` (`32e2783e`) has
  `products/kenn/tooling/gpu_box/gpu_box.sh` (verbs: `status`, `put`, `run`, `tail`) and a forced-command wrapper
  restricted to `/mnt/data/kenn-bakeoff/cloud`, GPU 0 and at least 40 GB free. Jack still has to do four things:
  - put the SSH key on the box
  - add the `KENN_GPU_KEY` secret
  - allowlist `www.haoee.com:2022`
  - approve the index copy

  Until then, don't try the box. The box is shared: send derived text only, never audio, and run `df -h /mnt/data`
  first.

## Rules (all still in force)

- **Commits:**
  - Never add a `Co-Authored-By: Claude ...` or any other AI trailer. The repo `CLAUDE.md` overrides the tool default.
  - Messages are one plain line saying what changed and why, and never mention AI or tools.
- **Merging:** nothing merges to `main` until a read-only reviewer who didn't write it has attacked the diff. Don't
  self-review as a substitute. Push the branch and leave it for review.
- **Code style:** follow the repo `CLAUDE.md`: human voice, comments that explain why, no filler, no banners.
- **Values that must not change:** `ANSWER_QUALITY_MIN_SCORE`, the 0.16 overlap threshold, `_RANGE_RE`,
  `_MEASUREMENT_RE`, `_measurements`, `EVIDENCE_SCAN_WINDOW`. Change the prompts and answers, not the checks.
- **Jack's calls:** the 128-token cap, hosted escalation (no hosted brain), and flipping the index `CURRENT`.
- **Parked; don't raise:** MLX or speculative decoding, the Developer ID, and the tester pilot.
- **Data:**
  - Never set `KENN_SKIP_EMBEDDINGS=1`.
  - Never rebuild or write the index.
  - Owner audio and corpora never enter the repo.
- **Permissions:** no new dependencies, permissions or CI changes without asking Jack.
- **kenn-app** (`Nite-DSP/kenn-app`): don't sync it from the cloud. It takes fast-forward-only sync commits after a
  fresh-worktree CI pass, which Jack does from the Mac.

## Handing back

So Jack can pull your work into the Mac:

1. Run `ci_verification.sh` on each branch before pushing. Name any failure that also fails on `main`, rather than
   hiding it.
2. Push every branch to `origin` (`Nite-DSP/monorepo`). Never force-push, and don't push to `main`.
3. Tick or annotate the plan items on the branch that does the work, with commit hashes.
4. At the end, add a short section below listing each branch, its head hash, what it changes and what still needs a
   probe run, then push it on `draft/cloud-handoff-notes`.

Jack pulls with `git fetch origin` and checks out the `draft/*` branches. Probe runs and merges happen on the Mac.

## State at handoff

- `main` and `origin/main`: see the push note in the plan. The rejection-reason work (`fcd2914f`, `2be6a7c6`), the
  chat-test skip (`b7738223`) and the gate-path checklist (`211644d0`) are on `main`.
- kenn-app `main` is `1c3ed858`, synced from monorepo `681dc674`. It doesn't include the four commits above yet.
- The local index on the Mac is `v-db8c6334cf63`. The probe uses `v-5f6964698b76` (4 Oct, no Related-questions chunks).
- Two eval-receipt tests fail locally only: `test_eval_runner` (5 cases) and `test_eval_chat_coverage` (3 cases). They
  are real note-ranking misses that overlap the C5 held-out rows, not a regression. They skip in the cloud.
- `products/kenn/docs/research/KENN_RETRIEVAL_2026-10-05.md` is Jack's retrieval research note. It's untracked on the
  Mac, so it isn't in the cloud checkout.

## Cloud session notes

(Add the branch list here before you finish.)
