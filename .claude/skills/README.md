# Vendored agent skills

Matt Pocock's engineering skills, vendored so Claude Code, Codex and opencode all
run the same set. Upstream: https://github.com/mattpocock/skills, MIT (see
LICENSE.mattpocock). Taken from commit d81f3a1 (release v1.3, 2026-09-29) on
2026-10-02.

There are two copies because the agents look in different places:

- `.claude/skills/` — Claude Code, and opencode
- `.agents/skills/` — Codex, and opencode

The two trees are byte-identical. To pull upstream changes, run `npx skills update`
from the repo root. To change a skill by hand, edit both trees.

Installed on purpose, a deliberately small set: code-review, codebase-design,
diagnosing-bugs, grill-me, grilling, research, tdd, wizard, writing-for-agents.

Left out: to-spec, to-tickets, triage, wayfinder, handoff and the rest of the
plan/ticket family. `products/kenn/KENN_PLAN.md` is the single roadmap and work
queue (see AGENTS.md), so skills that invent competing plans or tickets would
fight that rule. Add them only if that decision changes.

`skills-lock.json` at the repo root pins the source and per-file content hashes;
`npx skills experimental_install` restores from it.
