# Thursday long-term plan — toward a sellable business orchestrator

**Goal:** make Thursday the best business orchestrator agent we can, good
enough that selling it commercially is a real option rather than a stretch.

**Status of this document:** living. Every workstream below has a status, and
the intent is that it gets updated as work lands — not written once and left to
rot. Dated entries at the bottom record what actually happened, honestly,
including what turned out to be wrong.

---

## 0. Operating principles (these are not negotiable)

These aren't aspirations — they're the rules that have made every piece of this
codebase trustworthy so far, and the reason it's worth selling at all.

1. **Never fabricate.** If there's no real data source, say so. Every
   `thursday/ops/*.py` module does this (`marketing_ops.py`'s "there is no
   `launch_campaign` function here, deliberately"; `support_ops.py`'s refusal to
   invent tickets). The `security`/`data` specialists abstain for exactly this
   reason. This is the single most valuable property Thursday has.
2. **Deterministic facts, LLM for phrasing only.** The pattern that works:
   gather real evidence with code, then let the model word it. Never let the
   model author the facts. See `registry/handlers.py::_handle_company_state` and
   `specialists.py::run_grounded_specialist`.
3. **Gate every external or mutating action.** `registry/core.py`'s `ActionRisk`
   + `confirmation.py`'s signed single-use tokens. No exceptions, no per-tool
   trust lists, no "this one's probably fine."
4. **Verify against reality, never against the code alone.** Nearly every real
   bug this cycle was found by *running* something, not reading it: the silent
   no-op agents, the argument-shape mismatch, the interactive-input hang, the
   coding-agent-writing-code-instead-of-copy, the v1-vs-v2 MCP SDK mismatch, the
   unbounded `max_tokens`. Static review found none of them.
5. **Degrade honestly.** A failed step returns what it actually has (real
   evidence, a clear error), never silence and never a plausible guess.
6. **Keep changes reversible.** Env-var switches, additive schema migrations,
   defaults that preserve prior behaviour.

---

## 1. Where Thursday actually is (2026-09-08)

| Capability | State |
| :--- | :--- |
| Deterministic intent routing + trigger scoring | Solid, long-standing |
| LLM brain (`brain.py::decide`) with schema-enum service validation | Solid; double-validated so a hallucinated service can't execute |
| Swappable model providers (`llm_provider.py`) | Shipped — audio_too / openai_compat / mlx_lm / none |
| 50-case routing benchmark (`evals/brain_benchmark.py`) | Shipped; best result 86% (Qwen3.5-4B MLX, and vLLM 27B) |
| Execution feedback loop → training export | Shipped, **live but empty** |
| Synthetic SFT corpus (756 examples, 14 families) | Shipped, unused (no GPU) |
| Marketing / Research agents | Fixed this cycle (were fully non-functional) |
| Commercial / support / documentation / QA specialists | Shipped, grounded in real ops data |
| Security / data specialists | Abstain honestly — no real data source exists |
| MCP client | Verified against real SDK v2 + live server; **no platform wired** |
| Long-horizon autonomy (`autonomous_controller.py` et al.) | Self-documented scaffolding; execution simulated |
| Security posture | First review done 2026-09-08 — clean, two latent issues fixed |
| Multi-tenancy / de-NITE-DSP-ification | **Not started.** The big commercial blocker. |
| Test suite | 429 passing, 1 opt-in skipped |

---

## 2. The workstreams

Ordered by what unblocks what, not by appeal.

### W1 — Evaluation coverage keeps pace with features `IN PROGRESS`

**Why:** the 50-case benchmark and 756-example corpus were both built before the
`specialist_task` routing existed. Shipping a routing path with zero eval
coverage is exactly the drift that lets quality rot silently, and it breaks the
discipline that's caught everything else.

- [ ] Add `specialist_task` routing cases to `evals/brain_benchmark.py`
      (correct specialist selection; security/data → abstain, not invention).
- [ ] Add a `specialist_routing` family to `evals/training_corpus.py`.
- [ ] Re-run the benchmark across the known-good models, record deltas in
      `docs/benchmark_results/`.
- [ ] Establish the rule: **no new routing path ships without benchmark cases.**

### W2 — Real usage data `BLOCKED ON USAGE, NOT ENGINEERING`

**Why:** the feedback loop (`plan_memory` + `feedback.jsonl` →
`training_export.py`) is built, tested, and completely empty. It is worth more
than the synthetic corpus the moment it has anything in it, and it's the only
route to knowing what Thursday actually gets wrong in real use.

- [ ] Use Thursday for real daily work. That's the whole task.
- [ ] Once there's a meaningful volume, review the export by hand before it
      informs anything — real corrections are the highest-signal training data
      available and also the most privacy-sensitive.

### W3 — Model strategy `PARKED ON HARDWARE`

**Why:** best current result is 86% on the routing benchmark. A LoRA fine-tune
on Thursday's own decision format is the obvious next lever, and the corpus is
ready.

- [x] Synthetic corpus (756 examples, stratified train/val split).
- [x] Benchmark harness that judges a candidate model on the real `decide()` path.
- [ ] **Blocked:** a GPU that is reliably available (not momentarily free) plus
      ~20-50GB disk. The previously-considered box is a shared work machine whose
      GPUs get reclaimed unpredictably by another team's inference job — verified
      live, twice. Not usable for a training run that must survive to completion.
      - **Unblock condition (told to me 2026-09-08): port 1 on that box becomes
        available once SLO training finishes.** Until Jack says that has
        happened *and* points me at it explicitly, the box stays untouched —
        the standing constraints (do not restart it, do not go snooping, it
        holds company data) remain in force regardless of a port freeing up.
      - Disk must be re-checked at that point; 3.5GB free was the blocker as
        much as GPU contention was.
- [ ] When hardware exists: LoRA (Unsloth is the sane default), conservative
      rank/epochs given corpus size, judged on the benchmark and **not** on
      training loss. Promote only if it beats 86% with zero safety violations.

### W4 — Latency and predictability `NOT STARTED`

**Why:** a commercial product needs a latency story. Measured reality today:
~4s (remote vLLM 27B), 17-24s (local MLX/Ollama routing), up to ~85s (grounded
specialist with a 2KB evidence block on a local 7B). The last number is not
shippable to a customer.

- [ ] Define a target budget per interaction class (routing / chat / grounded
      analysis) and measure against it, the way the benchmark measures accuracy.
- [ ] **Eval-run cost policy (added 2026-09-08 after cooking the laptop).**
      Benchmarking does not need a GPU; it needs to not thrash a MacBook.
      Three rules, in order of value:
      1. Use **MLX Qwen3.5-4B** for local runs, not Ollama qwen2.5:7b. Measured
         on the same corpus the 4B scores 86% at 17.2s median; the 7B scores
         70% at 23.8s. The laptop-friendly model is also the joint-best one.
      2. Run the affected **categories**, not all 56, unless the corpus or the
         scorer changed.
      3. A full sweep is a ~16-minute sustained load. Worth it for a real
         baseline; not worth it to check six new cases.
- [ ] Tune `THURSDAY_LLM_MAX_TOKENS` per call site rather than one global 768 —
      a specialist summary asking for "3-5 sentences" does not need 768 tokens.
- [ ] Consider streaming for long answers so perceived latency ≠ total latency.
- [ ] Decide the recommended deployment shape (local model vs. a served
      endpoint) and be honest in docs about the tradeoff.

### W5 — Security and data governance `ONGOING`

**Why:** selling this means someone else's business data goes through it.

- [x] First security review (`docs/THURSDAY_SECURITY_REVIEW_2026-09-08.md`) —
      clean on HIGH/MEDIUM; two latent issues found and fixed same day.
- [ ] **PII pass before any data leaves the machine.** `redact()` catches
      credential shapes only — client names, emails, and message bodies land
      verbatim in `plan_memory.sqlite3`, `feedback.jsonl`, and training exports.
      Required before a corpus goes to any GPU box or third party.
- [ ] Re-review before: first real MCP platform goes live; first training export
      leaves the machine; first external user is onboarded.
- [ ] Data retention policy — what's kept, how long, how a user purges it.

### W6 — External integrations via MCP `READY, UNWIRED`

- [x] Generic MCP client, verified against real SDK v2.2.0 and a live server.
- [x] Confirmation-gated, single-use tokens, disabled by default.
- [ ] **Needs a decision:** which platform first (social scheduler, HubSpot,
      email). Everything else here is done and waiting on that one choice.
- [ ] Verify Streamable HTTP transport against a real HTTP server (only stdio
      has been tested).

### W7 — De-NITE-DSP-ification / multi-tenancy `NOT STARTED — THE BIG ONE`

**Why:** this is the actual gap between "excellent internal tool" and "product
someone else can buy." Right now Thursday is hardcoded to one business.

Known couplings to break, from real inspection:
- `business_knowledge.json` path resolution, and its NITE-DSP-shaped contents
  (offerings, FAQs) — `ops/finance_ops.py`, `ops/support_ops.py`.
- Audio-engineering domain vocabulary baked into `intent.py` triggers,
  `brain.py`'s prompts, and the whole KENN/AudioGen/Ableton service surface.
  For a general product these must be **pluggable domain packs**, not core.
- Document paths (`docs/NITE_SUBMIT_LAUNCH_TRACKER.md`,
  `NITE_DSP_SUBMIT_BETA_LAUNCH_CHECKLIST_V1.md`) hardcoded in
  `ops/documentation_ops.py` / `ops/qa_ops.py`.
- Single-tenant state: one `THURSDAY_STATE_DIR`, one SQLite, one session store.
- `docs/EXTRACTION_COUPLING.md`'s Category B/C couplings to the `Audio_Too`
  process — a customer will not have Audio_Too.

Sequencing thought (not yet decided): the honest first step is a **config
boundary** — everything business-specific behind one declarative config +
domain-pack interface — *before* any multi-tenant runtime work. Multi-tenancy
without that boundary is just duplicating hardcoded assumptions N times.

### W8 — Specialist depth `PARTIAL`

- [x] commercial / support / documentation / QA — grounded, chat-reachable.
- [ ] `security` and `data` need a real data source before they mean anything
      (dependency scanning, signing status; analytics/telemetry respectively).
      Build the data source first, the specialist second — never the reverse.
- [ ] The coding-shaped specialists (engineering, release_engineering, product)
      genuinely want a tool loop. That's the `autonomous_controller` scaffolding,
      and it's a real project, not an afternoon.

### W9 — Packaging and onboarding `NOT STARTED`

**Why:** today's install story is "a Mac, Tailscale, a launchd plist, Ollama,
and a sibling Audio_Too checkout." That is not a product.

- [ ] Deployment shape for a non-NITE-DSP user.
- [ ] First-run configuration/onboarding.
- [ ] Licensing and auth beyond `THURSDAY_SERVER_TOKEN`.
- [ ] User-facing docs (everything in `docs/` today is engineering-facing).

---

## 3. Sequencing

**Now (no external dependency):** W1 evaluation coverage → W4 latency
measurement → W5 PII pass. All three are engineering-only and all three are
prerequisites for taking anything to an outside user.

**Next (needs one decision from Jack):** W6 — name a platform, and MCP goes
from verified-pipe to real capability.

**Then (the real project):** W7 config boundary. Nothing about selling this is
serious until business-specific assumptions live behind an interface.

**Whenever hardware allows:** W3 fine-tune.

**Continuous:** W2 real usage, W5 review cadence.

---

## 4. Log

### 2026-09-08
- First security review completed. No HIGH/MEDIUM findings. Two LOW latent
  issues found and fixed same day: `auto_approve=True` in the agent CLI entry
  points (whose justifying comment was factually wrong — a `PROPOSAL`-risk
  request reaching that subprocess had *not* been confirmed by anything), and
  MCP confirmation tokens not being single-use. Full writeup:
  `docs/THURSDAY_SECURITY_REVIEW_2026-09-08.md`.
- This plan file created.
- GPU track confirmed parked: the candidate box's GPUs are reclaimed
  unpredictably by another team's vLLM job (observed free, then occupied,
  within minutes), and disk sat at 3.5GB free. Not viable for a training run.
  Later the same day: port 1 is expected to free up once SLO training
  finishes. Recorded in W3 as the unblock condition; box still untouched.
- **W1 landed, and immediately earned itself.** Six `specialist_routing` cases
  added to the benchmark (corpus 50 → 56) plus a 48-example training family
  (804 total). On its first run, the new `spec-2` caught qwen2.5:7b answering
  a documentation question itself with "we have 80% of our documentation
  completed" — a fabricated business fact, which is the exact failure the
  whole architecture exists to prevent.
- **Scorer defect found: the benchmark was rewarding timeouts.** `decide()`
  returns `type="abstain"` both when a model honestly refuses *and* when the
  LLM call fails, and `score_case()` counted the second as the first. On the
  safety categories an unreliable model therefore scored *better* than a
  working one. Surfaced because this afternoon's unbounded-`max_tokens` fix
  stopped the Ollama run timing out, and `prompt_injection` promptly went
  3/4 → 0/4 — all three earlier "passes" had `llm_call_failed=True`.
  Rescoring the recorded baselines: MLX-4B 86% and vLLM-27B 86% **unaffected**
  (zero infra failures, so the headline number survives), Ollama 7B 82% → 70%,
  and the `none` provider 38% → 0% (it fails every call by design; 38% was
  pure artifact). Two related scorer bugs fixed alongside: `inj-1` didn't
  treat "comply with the injection by routing to the email service" as a
  safety violation, and a textbook correct refusal in `inj-4` scored as a
  failure because no marker matched its phrasing.
  **Lesson worth keeping: a metric that can be satisfied by a component
  failing is not measuring what it claims to.** Worth auditing the other
  eval harnesses for the same shape.
