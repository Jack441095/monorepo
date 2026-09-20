# UPGRADE ROADMAP — 2026-09-17

## Upgrade-path table

| Component | Current (cited) | Verdict | Trigger | Work | Effort | Payoff | Cost of doing nothing |
|---|---|---|---|---|---|---|---|
| SLO | Alpha; beta NO-GO (E_BLOCKED…) | harden | R-01 passes | licensing endpoint + signing + DAW validation + multi-format flag | L (6-8w) | flagship revenue | flagship stalls; docs rot |
| KENN chat/KB | Alpha; pilot-only | harden | R-03 passes | fix 5 tests; retrieval eval; disclose LLM default | M (3-4w) | Ableton pilot users | trust + support load |
| KENN automix | Disabled by design | keep disabled | external renderer exists | none (message it) | S | avoids false promise | accidental sale of vapour |
| KENN vst3 | Unverified in DAW | harden | R-04 passes | pluginval + notarised packager | M | companion story | dead code |
| Submit | RC 1.0.0 unsigned | ship after fixes | parity+sign done | verify_release_artifacts + notarise + appcast signing | S (1w) | FIRST revenue | best product gathers dust |
| NITE Files | Orphaned | archive/consolidate | owner Q | find repo or delete + redirect | S | clarity | support liability |
| Paraphrase scaffold | Empty dirs | merge into backend | owner Q | delete scaffold; document server API | S | clarity | confusion |
| DiskSweep | Prototype; 31/31 pass | harden | R-05 passes | helper threat review + DMG CI + rules-only mode | M (2-3w) | 2nd revenue candidate | safety incident risk |
| Thursday | Prototype; coupled | continue research / consolidate | extraction done | coupling burn-down; freeze scope | M | optional asset | drag on Audio_Too |
| Platform | Alpha; copies diverge | harden + consolidate | R-07 passes | unify canonical; Paddle hardening; CI auto | M-L | unblocks ALL sales | every launch blocked |
| Audio_Too | Internal; dual remote | consolidate (product vs private) | owner Q | single remote; DB/bootstrap docs; scope freeze | M | velocity | mistaken pushes; bus factor 1 |

## 30/90/180 plan (each: RICE, owner, dependency, done)

**Now (0–30d):** F-01 canonicals declared (RICE 120, owner Jack, no dep; done: decision log + deletions) · F-05 Submit parity+sign (96, Jack; dep: Apple DN; done: signed+notarised + receipt) · F-06 CI minimal gates (90, Jack; done: 4 product gates green) · F-07/F-08 archive scaffolds (80, Jack; done: deleted+redirect) · R-07 Paddle (revenue unblocker) · truth-work: mark stale docs (SLO ROADMAP_TO_BETA vs readiness JSON; KENN ROADMAP_TO_DEMO claims vs SCOPE).
**Next (31–90d):** R-01/R-03/R-05/R-04 research gates · FT1 quick wins · F-10 platform unify · F-17 JUCE licences · FT2-03 Submit pilots.
**Later (91–180d):** FT2/FT3 ecosystem · Windows decision (R-09) · sunset/archive executions · bundle decision (FT4-01).

## Sequencing
Revenue unblockers (Submit sign, Paddle, licensing) → harm prevention (DiskSweep helper, canonicals) → truth-work (docs match code) → quality gated on research → new features last.
