# AGENTS.md

Guidance for AI coding agents and human engineers working in the NITE DSP codebase.

The goal of this repository is production-grade audio engineering software that is easy for humans to read, understand, maintain, and extend. Any code written here must read like it was crafted by a thoughtful human colleague—not generated in bulk by an automated tool.

---

## 1. Code & Comment Style: Human-Like, Clear, and Well-Commented

Code here should read like a colleague left it, not like a machine emitted it. Hold yourself to one test: would you be willing to have your name on the diff?

### Comment Generously, and Comment the Decision

A comment earns its line when it answers a question the code alone raises:

- Why this approach and not the obvious one.
- What breaks if this number, tolerance, ordering, or unit changes.
- Where the value came from — the measurement, the standard, the paper, the date, the machine.
- What was tried and rejected, so the next person does not repeat it.
- What this code deliberately does *not* do, and who does it instead.

Density target: a reader who knows Python should never have to stop and ask "why?" more than once inside a single function. Comment the seams, not every line.

```python
# Before: correct, and a reader cannot tell why either constant is what it is.
peaks_db = min(peaks_db, -1.0)
gain = round(10.0 ** (delta_db / 20.0), 4)
```

```python
# After: both constants now carry the constraint that produced them.
# -1 dBTP is the ceiling: a summed master above it clips in the lossy
# encode we hand to streaming, and we would rather give up 0.1 dB of peak
# than ship a master that distorts on someone else's phone speaker.
peaks_db = min(peaks_db, -1.0)

# Four decimals, because Live quantises the raw fader to 1e-4, so a finer
# gain silently rounds on write-back and the next read disagrees with the
# value we measured here.
gain = round(10.0 ** (delta_db / 20.0), 4)
```

### Comments Explain *Why*, Never Just *What*
- **Skip the restatement**: `if meter > 1.0:` needs no `# check if meter is greater than 1.0`. It needs `# Live's post-fader meter can report slightly above 1.0 during transient overshoots, so clamp here to avoid distortion`.
- **First person plural is natural**: *"we read the mixer here because..."* or *"we cache by SHA-256 to avoid re-analyzing multi-megabyte audio frames"* sounds human and explains team intent.
- **Write field notes**: record the edge cases that bit us, with dates, Ableton OSC quirks, and platform bugs where relevant (`# Live ignores device view changes while the mixer view is folded, so select the track first`).
- **Every fallback branch gets a line**: on each `except`, each early `return None`, each degraded path, say what happens there and why returning is safe.
- **Every literal gets a unit**: `-1.0` becomes `-1.0 dBTP`, `2048` becomes `2048 samples (46 ms at 44.1 kHz)`, `0.16` becomes `0.16 cosine overlap threshold`.
- **Docstrings state the contract**: one line on what it returns or changes, plus any surprising side effect or caller obligation. Expand only when the reasoning genuinely needs the room.

### No Boilerplate (the one hard guardrail)
Plenty of comments still means every comment is load-bearing. Specifically out: ASCII banners (`# ---------------- Helpers ----------------`), docstrings that echo the signature (`"""Sets volume of track."""`), `"Note:"` / `"This function is responsible for..."` openers, and decorative emojis in comments or commit logs. Delete any comment you cannot make specific.

### Plain, Specific English (Zero AI Slop)
- Speak directly in short, crisp sentences using concrete audio and programming terms.
- **Banned filler hype**: Do not use words like *robust*, *seamless*, *comprehensive*, *leverage*, *cutting-edge*, *orchestrate*, *delve*, or *ensure that*.
- State exact numbers and units: say `-1 dBTP`, `4:1 ratio`, `100 ms release`, `port 11000`, `250 ms timeout`.

### Match the Surrounding File
- When editing an existing file, adopt its naming conventions, indentation, docstring format, and import styles. Do not introduce a foreign style into an established module.
- Match the file's comment *register* — terse measured notes or chatty explanation — while keeping the density target above. A new module or a new subsystem gets the fuller treatment even if its neighbours are bare.
- Keep abstractions lean: solve the real problem directly. Avoid defensive layers for scenarios that can never occur.

### Before You Report Done
- Reread your own diff top to bottom as if you inherit it in six months with no memory of the ticket. Every branch, constant, and fallback carries a why, or the commenting is not finished.
- Delete every comment that only restates its line.

---

## 2. Testing as Executable Documentation

- **Tests read like clear examples**: Name test functions for the exact human behavior or boundary they protect (e.g., `test_other_one_moves_to_paired_track_when_clear`, `test_parameter_quiz_rejects_hallucinated_parameters_and_units`).
- A regression test should explain in one line what broke and why the regression cannot recur.
- When creating new features, always include unit and integration tests verifying happy paths, boundary failures, and isolation.
- Mutation-check new regression tests once before merge: change the guarded code and confirm the test fails.

---

## 3. Repository Hygiene & Engineering Boundaries

- **Live Belongs to the Producer**:
  - Daily engineering and test automation use `FakeLiveBackend`, mocks, and deterministic fixtures.
  - Never write directly to a running Ableton Live session unless conducting an owner-scheduled, supervised release soak.
- **Security & Secret Hygiene**:
  - Never commit remote hostnames, IP addresses, credentials, passwords, or personal connection strings to git.
  - Zero private audio, user stems, or personal session data in git commits.
- **GPU Constraints**:
  - Only GPUs 0 and 1 are authorized for KENN tasks on multi-GPU nodes. GPUs 2–7 are multi-tenant and strictly off-limits.
- **Human Commit Discipline**:
  - Single-line plain commit message explaining what changed and why it matters (e.g., `Add Stage 4 project memory with explicit preferences, answer citations, and REST lifecycle`).
  - **NEVER** include automated AI attribution trailers (`Co-Authored-By: Claude...`, `Generated by...`, etc.).
  - Use neutral branch and tag names such as `draft/`, `feature/`, or `fix/`; omit AI tool names.
- **KENN sharing**: Before publishing KENN changes or importing a teammate's `kenn-app` branch, follow `products/kenn/AGENTS.md`. The standalone repository must mirror the committed product tree without exposing the rest of this repository.
- **KENN planning**: `products/kenn/KENN_PLAN.md` is the sole roadmap and work queue. Dated evidence describes its recorded build; it is not an execution prompt. Update the plan instead of creating competing plans or handoffs.
- **Agent skills**: Matt Pocock's engineering skills are vendored in `.claude/skills` (Claude Code, opencode) and `.agents/skills` (Codex, opencode) — same files in both, see the README beside them. Reach for them to grill a plan, run a diagnosis loop, do TDD, or review a diff on standards and spec. They must not spawn competing plans or tickets: `products/kenn/KENN_PLAN.md` stays the single roadmap.
