# KENN: Continue the North Star Plan (next execution prompt)

**Reference document:** `products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md`
**Active progress log:** `KENN_PROGRESS.md`
**Operating style:** plain, careful human engineering. No filler, no boilerplate, no AI attribution trailers in
commits (`AGENTS.md`).
**Invariants:**
1. **Live is Jack's.** Fake Live backend, mocks, offline fixtures. No real Live unless an owner-scheduled soak.
2. **GPU rule:** GPUs 0 and 1 only for KENN. GPUs 2–7 are multi-tenant.
3. **Safety model:** the model never writes to Live. proposal → Apply → OSC write → readback → receipt → undo.

---

## Where the last round left off

The previous prompt's five tasks are all done and recorded in the North Star plan: Stage 2 retrieval fusion and
the embedding/reranker bake-offs, 15/15 recipes qualified, the brain prompt compacted to ≤ 450 tokens, and the
`kenn-next-build` wording fixes merged.

The 28 Sept audit then ran over the safety and answer paths and found eight live defects, all now fixed and
tested. Full suite: **2,228 passed, 5 skipped, 0 failed**. Retrieval recall@4 0.9828, chat coverage 124/128,
abstention 43/44 — all unchanged from a stashed baseline, so the fixes cost nothing in answer quality.

**Stage 3b is new in the plan** and holds both the eight fixes and an eighteen-item open list. Read that stage
before picking anything up.

## Do not re-derive the audit

The findings are written up in the plan with file, line, mechanism and, where relevant, the numbers that prove
them. Verify against the code, don't re-hunt.

## Task 1 — Close the Stage 3b open list, in this order

Start with the two that are reachable and matter:

1. **Semantic answer cache is not project-scoped** (`core/session_memory.py:280-336`, read at `:165-277`).
   The `semantic_cache` table has no `session_id` column, so project A's full rendered answer can be served
   verbatim in project B for any query ≥ 0.95 cosine-similar — and `chat_answer.py:1762` enables this path
   precisely when there is *no* session context. This directly contradicts the Stage 4 cross-project-leak gate.
   Add the column, scope every read and write, and add a test that stores an answer in one session and asks the
   same question in another.
   Also bound it: the L2 list only ever appends, and every query scans it in full. A semantic match is currently
   written into the exact-match cache, which turns a soft 0.95 hit into a hard one.

2. **`validate_llm_plan` skips the device-parameter range check when it shouldn't** (`core/live_command.py:735`
   and `:845-851`). If the snapshot carries no parameters for the device, `capability_parameters` is empty and the
   whole range block is skipped; if a profile's bounds are non-numeric, both sides become NaN and the guard
   `math.isfinite(...) and ...` is False, so the check is skipped rather than failed. Both fail open on the path
   that writes to a device. Make them fail closed, and test both branches.

Then, in the plan's order: the `relative: true` volume drop, the `and clean_command` refusal guard, the
`LiveExecutor` undo path, `idempotency_bounds` eviction, the `endpoint_policy` fail-open default, the
`diagnostic_loop` inconclusive wedge, the `mix_recipes` zip, the discarded LUFS target, and the single-preference
loss.

## Task 2 — Ingest the Ableton Live Reference Manual (needs the owner's yes)

The Knowledge programme ranks the manual above curated notes, and the code is written, tested and waiting:
`pdf_evidence_class` labels it, `has_manual_subject_overlap` gates it, `display_results` prefers it. All six
index versions hold **zero** `official_ableton_manual` chunks, so the whole pathway is dead today.

Ingest it with a catalogue entry of category `ableton` and "manual" in the title or tags, then re-measure:

- `tooling/scripts/evaluate_retrieval_modes.py` — recall@4 on all four fixtures. The describe-it set (currently
  0.784) is where a real manual should move the needle; the earlier bake-off ceiling was 0.808 on that set, and
  that ceiling was set by *candidate recall*, not by the ranker.
- `tooling/scripts/eval_chat_coverage.py` — coverage must not drop. The four standing failures are
  `bass-processing`, `harsh-vocal-fix`, `ambiguous-lufs-target`, `wwise-mobile-ambience-memory`; watch whether
  the manual fixes any of them.

The open owner question at the bottom of the plan is whether to do this now or after Stage 2's parameter work.

## Task 3 — Re-record the chat coverage number

The plan claims 125/128; the tooling measures 124/128 on `main`. Both numbers are in the plan with the
explanation. Confirm which is right from a clean run and make the plan state one number.

## Task 4 — Gates still open on the plan

- **Stage 1 gate:** accuracy is met (494/505, 97.8%, 0 wrong plans). Still open: the human-review packet with
  two reviewers, p95 ≤ 4 s, and zero writes without Apply across shadow logs.
- **Stage 2 gate:** recall@4 is 0.983 / 0.784 / 0.425 against a 0.95 target on the describe-it and sealed sets.
  The evidence from both bake-offs is that **model size is not the route** — bge-base topped out at 0.81 and
  bge-reranker-base at 0.808, with the right note present in the top 20 for 87.2% of describe-it questions. The
  gap is vocabulary: notes describe devices technically, producers describe goals. The next lever is note wording,
  not a bigger model.
- **Stage 3 gate:** per-step latency ≤ 3 s and zero unauthorised writes across the pilot.

## Task 5 — Housekeeping

1. Tick the North Star boxes in the same commit as the work, with the date and the evidence.
2. Update `KENN_PROGRESS.md`.
3. Single-line plain commit message, no AI attribution trailers. Never commit hostnames, IPs, credentials or
   private audio.
