# Refactor handoff — 2 Oct 2026

State of the backend mega-function refactor, the method that produced the two committed
splits, and the measurement constraints that govern any claim made about KENN's LLM
subsystem. Written so an agent starting with no prior session can continue safely.

Everything below was measured on this machine. Where a number is a single sample rather
than a distribution, it says so.

---

## 1. Git state

Branch `kenn-refactorisation`, two commits ahead of `main` at `d15d199b`.

| Commit | What |
|---|---|
| `91b1b255` | Split the MCP intent router into per-family handler modules |
| `ce02289b` | Split `live_intent` rule parsing into four ordered stage modules, pinned by a 384-row corpus replay from the pre-split parser |

**Baseline after `ce02289b`:** 3061 passed, 2 failed, 5 skipped, 112 s, run with
`python3 -m pytest -q -p no:randomly` from `apps/backend/src`.

Both failures are **pre-existing and unchanged** — do not treat them as regressions:

- `test_kenn_command_pilot::test_pilot_default_is_preflight_only_and_preserves_artifacts`
  — environmental, fails on a huggingface connection, fails in isolation.
- `test_live_command::test_llm_plan_gets_one_structural_repair_attempt`
  — order-dependent, passes in isolation.

**Logistics that will bite you.** `products/kenn/runtime/` and `workspace/` are untracked
and **not** gitignored. Stage by explicit path; `git add .` sweeps them in. One function
per commit, single-line message, no AI attribution trailers.

---

## 2. The method — proven twice, follow it in this order

1. **AST census first, report before choosing cut points.** Never invent a decomposition
   from the function name. Group by vocabulary that already exists in the codebase.
2. **Characterise before moving.** Write the tests and run them against *unmodified*
   source first. A characterisation test that passes on day one proves nothing about the
   move.
3. **Prove equivalence from git history, not by blessing new output.** Reconstruct the
   pre-split function with `git show <sha>:path` into a temp tree, run both, diff
   byte-for-byte. Expectations must be generated from the pre-split code. Item 2 used
   96 phrasings × 4 session states = 384 rows, with provenance recorded in the fixture
   docstring.
4. **Mutate every seam.** Deliberately break each extracted boundary and confirm a test
   catches it. **A mutation that passes is a coverage finding to report — never a reason
   to weaken the test.**
5. **Revert and checksum every mutation.**
6. **Preserve order by sequential calls**, not a dispatch table, wherever order matters.
7. **Full suite as the commit gate.** Scoped runs are not sufficient.

**Leave-behind rule.** 441 lines in `live_intent.py` (`:2744-2855`, `:2861-3189`) were
deliberately left in place because they read state mutated elsewhere in the chain —
`insert_device_name` is written at one point and read 200 lines later. A partial
extraction that is proven beats a complete one that cannot be proven.

---

## 3. Safety constraints — hard rules

### Never modify, in any commit

- `ANSWER_QUALITY_MIN_SCORE`
- the 0.16 overlap threshold
- `_RANGE_RE`, `_MEASUREMENT_RE`, `_measurements`

### Coupled constants that break silently

- The **streaming prefix guard inspects only the first two chunks**. Changing how many
  chunks are buffered before the first guard call is a behaviour change, not a refactor.
- `EVIDENCE_SCAN_WINDOW = 12` is aliased by two sides of the system. Change both in the
  same commit or neither.
- The evidence gate in `core/chat_grounding.py` (`_gate_evidence_text`,
  `verify_claim_citations`, `evidence_measurements`) must be untouched, or fixed at
  **both** ends in the same commit.
- The deliberate deterministic parser stays authoritative for chat-originated DAW writes.

### Environment

- **Never** write to a running Ableton Live session. `FakeLiveBackend`, mocks, fixtures.
- **One CPU-heavy process at a time.** 16 GB, 4P/4E cores; load average has hit 21 before.
- **Never** `KENN_SKIP_EMBEDDINGS=1` — it misaligns the embedding matrix and degrades
  `hybrid_search` to BM25-only, which flatters acceptance for the wrong reason.
- Never rebuild the index on this machine. That needs the GPU box (GPUs 0/1 only).

---

## 4. What is left, in order

**Sequencing decision, 2 Oct 2026:** the refactor completes here *before* goal work starts,
rather than being deferred until after new features land. The reason is not effort. The
LLM subsystem work is retrieval, verification, and citations — it lands in `chat_answer.py`,
`chat_grounding.py`, and the retrieval path, so deferring the split lets the monoliths grow
instead of holding steady. And characterisation tests written after new features exist pin
whatever the code does then, bugs included: a split validated against a baseline that
silently absorbed a regression certifies that regression as intended behaviour. Items 1 and 2
were banked against a suite with exactly two understood failures; that is what makes a later
split certifiable at all.

**Handover point: the refactor stops after item 3b, by decision.** Items 3a, 4 and 5 below are
deliberately left undone, not abandoned or forgotten — 3a was judged likely to need iteration
on a 120-branch chain, which is the one shape this codebase has not yet proven the method
against. Do not read the remaining items as oversights. They carry the same method and the
same constraints, and the safety-critical one (item 4) is still the OSC write path.

| Item | Target | Size | Notes |
|---|---|---|---|
| 3b | `chat_answer._answer_payload_stream_raw` (`:1229`) | 642 lines | ~21 lines/branch, near-linear. In flight when this was written. |
| 3a | `live_command._handle_command_impl` (`:2945`) | 786 lines | **120 branches, 6.5 lines/branch.** Hardest remaining item — a flat chain where cut points are judgement calls. |
| 4 | `live_action_service.execute` (`:3645`) | 613 lines | The OSC write path. Do this last. |
| 5 | Delete 5 dead tool functions | 71 lines | Verified below. Own commit. |

### Dead code — verified 2 Oct 2026

In `autonomous_agent.py`, a tool is planner-callable only if its **bare name** sits in
**both** registries: `self.tools` (32 entries, built at `:852` as an *annotated*
assignment) and `_PLAN_TOOL_SCHEMAS` (22 keys, `:812`), gated at `:1091`.

Registry keys are bare — `"set_ableton_volume"` — while the functions are
`tool_set_ableton_volume`. And key/function names do **not** always correspond:
`tool_orchestrate_subagent` is bound under the key `"orchestrate"` and is live.

Of 37 `tool_*` functions (469 lines): 22 planner-reachable, 10 wired but not
planner-selectable (91 lines), and **5 wired into neither path — genuinely dead,
71 lines**:

- `tool_audit_live_session` (27)
- `tool_auto_remediate_session_issues` (18)
- `tool_generate_neural_bassline` (10)
- `tool_formulate_surgical_remediation` (8)
- `tool_synthesize_pro_rack` (8)

**Method warning.** Three intermediate counts here were reported confidently and were all
wrong (6, then 16, then 6 again) before references were resolved with `ast.walk`.
To audit reachability, resolve the **function each `KennTool` entry binds** (third
positional arg) — never derive a function name by string-munging the key.

A repo-wide scan also flagged 49 module-level defs never referenced in `src/` or
`tooling/`, but that is an **upper bound on candidates, not confirmed dead**: the repo
has 94 `getattr` and 8 dynamic-import sites a text scan cannot see. Verify per item.

### Two known defects, found but deliberately not fixed

- **`"pan track 2"` produces a broken example.** The clarify question suggests
  `"pan Snare / Clap 2 left"`, and the parser reads the `2` back as **2% left**. In the
  write path.
- **`set_tempo` is invisible to the order test.** `test_live_intent_rule_order.CHAIN_ACTIONS`
  omits it because `_tempo_request` writes into a dict bound to `fields`
  (`live_intent.py:2065`) and the AST scan at `:113-116` does not traverse it. A dropped
  tempo rule would change nothing observable. Currently covered only by the corpus replay.

### Shape warning on `live_intent.py`

At 3198 lines it is 62 functions with a **median size of 13 lines**, plus ~1164 lines of
module-level constants (291 of them). The top 10 functions hold 1326 of 2034 lines.

The 1241-line mega-function was the worst offender but was never the bulk. **Do not judge
this file by line count again — measure the shape.** The remaining weight is vocabulary
(291 constants), which wants relocating to data, not decomposing.

---

## 5. Measurement discipline

These govern every claim about the LLM subsystem. They are the reason several previously
reported numbers were withdrawn.

- **Acceptance at n=29 carries ±15 points.** Identical application code (9800a9e8 and
  a292dd4f) gave 23/29 then 22/29 accepted. **Quote no single before/after pair unless
  it exceeds that swing.** Progression so far: 41% (12/29) → 66% (19/29) → 76-79%.
- **TTFT is the only low-variance latency signal**: median 3.18 s, p95 5.04 s, against a
  complete-answer median of 21.74 s. Quote TTFT for latency work. Completion median read
  17.74 s then 21.74 s on identical application code — that was variance, not improvement.
- Measure with `tooling/scripts/measure_chat_latency.py --surface stream`, model
  `kenn-brain-qwen3-8b`, `KENN_LLM_CACHE=0`.

### Tier 1 device control is already shipped

Measured before any of this work: p95 **667 ms** against a 700 ms gate, 99.1% action
accuracy, 100% parameter accuracy, 99.6% track resolution across **294 real commands**
(`core/kenn/data/live_llm_shadow.jsonl`). **Do not rebuild it.** The remaining value is
the tail: the top 5% of controller requests hold 59.9% of total controller time.

### Phase 7 (claim citations) fails its gate

82.1% answered-anyway against a <10% target. The failure is **model non-compliance, not
a knowledge gap**: across 28 answers, 0 fabricated attributions and 0 invented chunk ids,
but only 2 of 11 numeric claims cited and 5 of 28 abstentions.

### Logprobs: available, but not yet a fabrication signal

Ollama `{"logprobs":true,"top_logprobs":N}` populates on this build via native
`POST /api/chat`. Two traps:

- The **chosen token's `logprob` is 0.0 for every token.** A "sum the logprobs over each
  claim" design sums to zero and detects nothing.
- `top_logprobs` **defaults to 0**, which returns only that zero. The usable signal is the
  margin over the non-chosen alternatives.
- `logprobs` returns a **list** when `top_logprobs > 0` and a **dict** otherwise. Parse
  defensively.
- The opening token always has a low margin (3.6-3.9). Never include it in a claim score.

Measured at **n=2 only**: value present in the note gave numeric min-margin 17.23 / mean
31.20; value absent gave min-margin 5.59 / mean 18.57. Directionally plausible, ranges
overlap almost entirely, and the second sample was contaminated by digits genuinely
copied from the same note. **No usable threshold exists yet.** Corpus-wide measurement is
outstanding.

### Known retrieval defect — a chunking bug, not a ranking bug

Related-questions sections are indexed as chunks and win on embedding cosine to a
**verbatim query echo** (0.531), not BM25. The fix is written and tested (fix-5) but the
index was **never rebuilt**. Two wrong diagnoses were already recorded and are worth not
repeating: term density does *not* explain it (2.53 vs 2.46; the winner had *fewer* term
hits, 13 vs 15), and re-weighting the chunk body does *not* fix it at 2× or 3×.

No reranker, embedder, or weighting scheme fixes this, because the winning chunk's body
*is* the query — the matched signal is identity, not relevance. Two fixes: rebuild the
index with fix-5 live (needs the GPU box), or filter Related-questions chunks at query time
(cheaper, no rebuild, unblocks the item without the GPU box).

---

## 6. Hardware ceiling

Apple M3, 16 GB unified memory, 4P/4E cores. 96 GB free internally; the workspace is on
an external volume.

**The chat model is effectively fixed at 8B** (`kenn-brain-qwen3-8b`, Q4_K_M, 5.0 GB).
Qwen3-30B-A3B-Instruct-2507 at Q4 needs ~18-19 GB and does not fit. A dense 14B-Q4 fits but
decodes at ~77 tok/s against the current 133-140. Answer quality must come from
architecture, not model size.

fp16/bf16 must be avoided on Apple Silicon CPU (emulated, ~0.01x). **CoreML/ANE is
actively harmful for short sequences** — queries here are 10-20 tokens. Use int8 ONNX.

The deliberative planner (Qwen3-4B, ~2.5 GB) gains relative weight: 8B + 4B is ~7.5 GB and
leaves headroom, and it already holds 100% contract validity and 100% safety pass rate
across 6 runs — a better track record than the chat brain.

---

## 7. Blocked

| Item | Blocker |
|---|---|
| Phase 8 — corpus growth | Needs a GPU-box index rebuild to be measurable. Not this Mac. |
| Phase 9 — model evaluation | Dead on 16 GB. 30B-A3B needs 18-20 GB. |
| Phase 7 rework | Awaiting a decision: rework or park. Deferred until the refactor lands. |
| `.gitignore` scope for `*.gguf`/`*.npy`/`*.safetensors`/`*.bin` | Awaiting approval. Low urgency. |