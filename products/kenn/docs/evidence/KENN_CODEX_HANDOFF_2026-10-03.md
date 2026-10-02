# Handoff for Codex, 3 October 2026

Repo `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo`, branch `fix/review-critical-2026-10-02` (head `7c17ccb8`). Plan:
`products/kenn/KENN_PLAN.md`. Read [KENN_C3_CORRECTIONS_STATUS_2026-10-03.md](KENN_C3_CORRECTIONS_STATUS_2026-10-03.md)
and [KENN_C3_FIVE_TURN_FIRST_RUN_2026-10-03.md](KENN_C3_FIVE_TURN_FIRST_RUN_2026-10-03.md) first.

## Where things stand

- The local delivery gate (70% of eligible knowledge requests get an accepted model answer within 15 s on M3 / 16 GB with
  Live open) is still failed on both the stream and payload surfaces. C1, C2 and C3 stay unticked.
- Model: Ollama `kenn-brain-qwen3-8b`, index `v-db8c6334cf63`.
- Pushed: five-turn runner and six scripted conversations; the invented-analysis fix (`d69db4b1`); correction handling
  (`7c17ccb8`: `is_correction_query` in `core/chat_routing.py`, tests in `tests/test_correction_followups.py`).
- Last full KENN suite, fresh pytest cache: 3,581 passed, 5 skipped, 0 failed. One smoke test,
  `test_server_smoke.py::test_main_chat_can_combine_explicit_mix_review_and_plugin_evidence`, fails in some orderings and
  passes alone. Known, cause unknown.

## Next, in order

1. Orchestrator and corrections. "Sorry, it is the acoustic guitar that is muddy, not the vocal." still routes to
   `ableton_controller` and gets a canned low-end reply, because `orchestrator.py` (`classify` / `dispatch`, called from
   `core/chat_answer.py` around line 1285) sees the raw query with no history. Either pass history in or skip the
   orchestrator when `is_correction_query` is true. Add a test named for the behaviour.
2. Other C3 gaps from the first run: "Cancel that, I will do it myself." is searched against the previous question;
   clarify replies ignore history; topic changes carry old context into the search.
3. Speed (C2). A deep-research workflow (`wf_79bf1216-30a`) was still running in Claude Code when this was written. If
   its report is not in the repo, ignore it. Web numbers are a shortlist only and every number needs its hardware stated.
   Any MLX comparison must use the Qwen3 8B lineage. New dependencies or model files need Jack's OK.
4. Parked, need Jack: reranker, Live-open comparison, review of `harsh-after-mastering-limiting.md`, held-out ranking
   rows, L1 (needs a real Live session Jack schedules).

## Rules (Jack's, do not break)

- One plain-line commit message. No AI attribution trailer, ever, whatever the tool's defaults say.
- Stage files explicitly. About 70 unrelated files are dirty (including `.github/workflows/*.yml`), and
  `products/kenn/runtime/` is untracked. Never `git add -A`. Keep diffs small.
- Run git from the monorepo root. Push the working branch only; pushing to main needs Jack to ask.
- Run the scoped tests before saying done and name pre-existing failures. Pytest from `products/kenn` with
  `PYTHONPATH="apps/backend/src:tooling"` and a fresh `-o cache_dir=/private/tmp/kenn-pcache-<anything>`.
- Plan ticks need a commit, the scoped command, the result, limits and a dated receipt. No runtime or private audio and
  no model prose in commits.
- Do not add dependencies, widen permissions or change CI without asking. Do not delete anything without asking.
- Engineer on fake Live (`KENN_LIVE_BACKEND=fake`). Real Live only for soaks Jack schedules. Don't rebuild the index on
  this Mac. One CPU-heavy job at a time.
- Shared GPU box (`ubuntu@www.haoee.com -p 2022`): only `slo_*` paths and KENN paths Jack has OK'd, GPU 0, root disk is
  chronically full, derived text and features only.
- Code and comments in a human voice: why, not what; tests named for behaviour (see CLAUDE.md).
- Don't raise the parked Developer ID / 3-tester pilot.

## Real-model run env

`KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama KENN_LLM_MODEL=kenn-brain-qwen3-8b KENN_LLM_CACHE=0 KENN_CHATS_DIR=<tmp>
KENN_DB_PATH=<tmp> KENN_LIVE_BACKEND=fake PYTHONPATH=apps/backend/src:tooling`, then
`tooling/scripts/run_conversation_cases.py` with `apps/backend/src/kenn/evals/five_turn_conversations.json`.

## Disclosure owed

Earlier this session `qwen3:4b` and `kenn-c6-run11` were deleted from Ollama, so they can't be recreated or re-hashed.
