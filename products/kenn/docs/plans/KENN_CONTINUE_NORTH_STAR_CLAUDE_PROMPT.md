# KENN: Continue the North Star Plan (Claude Execution Prompt)

**Reference Document**: `products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md`  
**Active Progress Log**: `KENN_PROGRESS.md`  
**Operating Style**: Plain, careful human engineering. No filler, no boilerplate, no AI attribution trailers in commits (`CLAUDE.md`).  
**Safety & Hardware Invariants**:  
1. **Live is Jack's**: Use the fake Live backend (`run_fake_live_companion.py`), automated suites, and offline fixtures. Do not require real Live on the Mac unless running an owner-scheduled soak.
2. **GPU Rule**: Remote GPU box — ONLY GPUs 0 and 1 are allocated for KENN. GPUs 2–7 are multi-tenant and strictly off-limits.
3. **Safety Model**: Model never writes directly to Live. Every write is proposal → user Apply → OSC write → readback verification → receipt → exact undo.

---

## Context & Current Position

- **Main commit**: `60599d4` (`kenn-beta-2026-09-27-b`).
- **Soak #5 passed**: 8 hours, 481 samples, 0 errors, flat memory, 28 ms median latency.
- **Branches / Worktrees**:
  - `main`: Beta release tree.
  - `workspace/worktrees/kenn/next-build` (`kenn-next-build`): Tricky wording parser fixes, taken-back requests ("jk", "nah"), multi-track lists, lead note selection.
  - `workspace/worktrees/kenn/north-star` (`kenn-recipes`): 15 named mix recipes in `core/mix_recipes.py`, 14/15 qualified on fake Live (Glue needs real Live profile).
- **Retrieval state**: Fixture has reached **303 questions** (gate size met). Hybrid recall@4 is 0.98 on original, 0.74 on describe-it, 0.84 on techniques. "Use it when..." candidate lines exist.
- **Brain state**: Qwen3 8B selected. Local 16 GB M3 is token-bound (~75 tok/s prompt read, 17 tok/s write) taking 7–16 s due to ~1,400 tokens of notes in prompt. Box GPU 0 serves it in 2.8 s.

---

## Immediate Objectives

Execute the next logical sequence from `KENN_NORTH_STAR_2026-09-24.md`:

### Task 1: Complete Stage 2 Retrieval Gate (Push Recall@4 toward 0.95)
1. In `products/kenn`:
   - Inspect `evals/technique_purpose_retrieval_cases.json` and `evals/device_purpose_sealed_qwen8b.json`.
   - Run `tooling/scripts/measure_use_it_when_lines.py` across the 303-question fixture.
   - Test note wording adjustments ("Use it when…" lines in device notes) on the training half, measure on the held-out half.
   - Verify chat coverage (≥ 125/128) and abstention (≥ 43/44) do not regress.
2. Record measured recall numbers directly in `KENN_NORTH_STAR_2026-09-24.md` under Stage 2 with date and evidence.

### Task 2: Qualify All 15 Mix Recipes on Fake Live (Stage 3)
1. Switch to or integrate the `kenn-recipes` branch (`workspace/worktrees/kenn/north-star`).
2. Run `tooling/scripts/qualify_recipes_live.py` against the fake Live companion:
   - Identify why the 15th recipe (Glue compressor) failed.
   - Update `core/mix_recipes.py` or device parameter mapping for Glue Compressor so it passes with 100% exact undo.
   - Achieve **15/15 recipes qualified** on fake Live.
3. Ensure every recipe adheres to:
   - Real dB values (no fixed raw fader jumps).
   - Asking when roles match multiple tracks (e.g. two basses).
   - Exact undo walking backward through changes.

### Task 3: Unblock Stage 1 Brain Speed (Notes Prompt Compaction)
1. Solve the 7–16 s Mac latency bottleneck for Qwen3 8B:
   - Currently, ~1,400 tokens of retrieved notes are injected into the prompt.
   - Implement concise excerpt extraction (extracting only the relevant section or top 3 bullet points per note instead of full markdown text) to bring prompt notes under 450 tokens.
   - Benchmark TTFB and total response time with `tooling/scripts/route_latency_report.py` and `evaluate_chat_brain.py`.
   - Verify grounding check pass rate does not degrade.

### Task 4: Integrate Tricky Wording Fixes into Next Build
1. Review uncommitted / pending changes on `kenn-next-build` and `kenn-after-soak`:
   - Verify 2,067 test suite passes: `PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests`.
   - Confirm multi-track lists, negations ("don't mute the drum bus"), and joke retractions ("jk", "nah") pass cleanly.

### Task 5: Document & Commit
1. Tick the relevant checkboxes in `products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md` and update `KENN_PROGRESS.md`.
2. Write commit messages following repo guidelines: single plain line, explaining what changed and why, zero AI attribution tags.
