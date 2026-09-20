# AutoMix Masking De-Mask Correction

Type: AutoMix decision logic
Tags: automix, masking, de-mask, dynamic eq, relationship engine, mixdown, master bus, stem processing
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_renderer.py (_masking_moves_by_target, stage 1C), mixdown/mix_decision_engine.py (MixPlan.apply_masking_corrections)
Reviewed: 2026-07-16

Short answer:
AutoMix's relationship engine already detects when one stem is masking another (two elements competing for the same frequency band) and proposes a dynamic-EQ de-mask move — but for a long time that move was only ever logged as a suggestion, never actually applied to the render. This stage closes that gap: when a mix plan opts in (`apply_masking_corrections`), the highest-scored actionable de-mask move for each affected stem is applied directly to that stem, before it sums into the mix.

Try this — how a move gets selected and applied:
1. The relationship engine's output (`mix_plan.relationships`) is scanned for relationships already marked `status: "candidate"` — `review_required` and `existing_treatment_detected` relationships are skipped, since those aren't ready for an automatic move.
2. Only `dynamic_eq` candidate strategies are eligible (not static EQ, sidechain, or automation moves) — dynamic EQ is the most surgical and self-limiting option: it only reduces the overlap band while that band is actually excessive on this specific stem.
3. Candidates are ranked by their own score; only the single highest-scored move per target stem is kept, and the whole set is capped at 8 moves per song (`_MAX_MASKING_MOVES_PER_SONG`) so a busy arrangement with many relationships doesn't get over-corrected everywhere at once.
4. The kept move is applied as a bounded dynamic-EQ cut on the target stem alone (stage 1C, right after the stem's own resonance-detection pass) — never on the higher-priority "masker" stem, which is left untouched. The protected source keeps its priority; only the masked, lower-priority stem is adjusted.
5. This composes with — and runs before — the master-bus dynamic EQ pass (which still runs unchanged afterward and simply finds nothing left to cut here if this stage already fixed it).

Why it matters:
Without this stage, the relationship engine's masking analysis was pure diagnostics — real, computed evidence that never touched the actual render. A user (or KENN) could see "this stem is being masked" in a report and there was nothing AutoMix did about it automatically. Wiring this closed a genuine detect→correct gap, not a cosmetic one.

Common mistakes:
- Assuming every masking relationship the engine finds gets corrected — only `status: "candidate"` relationships with a `dynamic_eq` strategy do; `review_required` ones are intentionally left for a human/KENN judgment call, not auto-applied.
- Assuming the masker (higher-priority) stem gets adjusted — it never does. Only the masked (lower-priority, `intervention_target`) stem is touched, so the more important element in the relationship is never degraded to make room.
- Turning this on and expecting audible drama — it's a bounded, level-triggered cut on one specific band on one specific stem, sized by the candidate's own `max_reduction_db`; it is meant to be a corrective nudge, not a re-mix.

When this does not apply:
- Off by default (`apply_masking_corrections=False` on `MixPlan`) — this is listening-gated diagnostic functionality, not yet a production default. It has unit test coverage (7 tests in `tests/audio_analysis/test_mix_renderer_masking_corrections.py`) but not yet a blind-listening validation pass of its own.
- Does nothing if the relationship engine found no actionable `candidate` relationships with a `dynamic_eq` strategy — a mix with no real masking problems is untouched, same no-op guarantee as the master-bus dynamic EQ stage.

Related questions:
- Why did AutoMix cut a specific frequency on one of my stems but not others?
- What does it mean when a mix report flags a masking relationship as "candidate" vs "review_required"?
- Does AutoMix automatically fix masking between two stems, or just report it?
