# KENN KNOWLEDGE BASE — HYGIENE FIX PASS — AGENT PROMPT (V1)

> **What this file is:** a reusable, self-contained prompt that drives an AI coding agent to fix the five concrete corpus-hygiene issues surfaced by the 2026-09-21 Phase 1 inventory (see `KENN_KNOWLEDGE_BASE_5000_NOTE_SCALEUP_PROMPT_V1.md` §2 gate) — **before** any bulk ingestion toward the 5,000-note target proceeds. This is fix-first groundwork, not the scale-up itself.
>
> **How to use it:** open the workspace root (`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/handoff/kenn-full-product-slo`) and instruct the agent: *"Execute `KENN_KNOWLEDGE_BASE_HYGIENE_FIX_PROMPT_V1.md` in full. Produce every deliverable in §7."*
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-21 · **Supersedes:** none · **Depends on:** Phase 1 inventory findings, 2026-09-21

---

## 0. Role, mission and success criteria

You are a **data-hygiene engineer** for KENN's knowledge corpus. Your mission: fix five specific, already-identified problems in `apps/backend/src/kenn/Training_Data_Notes/` (775 files) without losing data, without fabricating facts to fill gaps, and without breaking retrieval.

**This repo is NOT under git** (`git status` fails with "not a git repository"). There is no version-control safety net — you must build your own via backups (§1, R0) before touching a single file.

**The five issues to fix (from Phase 1 inventory, all independently verified 2026-09-21):**
1. No contradiction-registry baseline has ever been run against the corpus — success criteria for the future scale-up can't be measured without one.
2. 382 of 775 files (49%) carry `Source: Official Reference Documentation` as a placeholder when they are actually paraphrased YouTube masterclass transcripts — provenance mislabeling.
3. At least 2 near-duplicate note pairs exist (found in a 10% sample; more likely exist corpus-wide) — no dedup tooling exists yet.
4. `ableton-spectral-resonator.md` has a self-contradicting status: a top `Status: Approved` header and a later `**Status:** Draft` line in the body.
5. 4 files have no `Status:` field at all: `ableton-meld-synth.md`, `ableton12-live-audio-effect-reference-pt11.md`, one further `-pt15.md` file (confirm exact name), `ableton12-live-instruments-ref-pt20.md`.

**Success criteria (all must hold before you stop):**
1. A timestamped, restorable backup of `Training_Data_Notes/` exists before any write.
2. Contradiction registry has been run against the full corpus; a baseline report (contradiction count, list of conflicting note-ID pairs) is saved to `docs/reports/`.
3. Every file whose `Source:` field says "Official Reference Documentation" has been re-checked: if its actual content is a YouTube-transcript paraphrase, the field is corrected to reflect that (e.g. `Source: YouTube Masterclass Transcript (paraphrased)` plus the original video/creator if recoverable from the note body or a matching transcript file); if it genuinely is manual/reference-derived, leave it and note that in the report.
4. A dedup pass has run across the full 775-file corpus (not just the sample) using a documented method (embedding similarity via existing ONNX/BM25 tooling, or fuzzy filename+content-hash fallback if ONNX is unavailable). Every near-duplicate pair found is either merged (keep the more complete/accurate note, redirect or delete the other) or, if genuinely distinct on inspection, documented as a false positive — never silently deleted without a one-line justification in the ledger.
5. `ableton-spectral-resonator.md`'s status conflict is resolved to a single, correct `Status:` value based on reading the actual note content and its `Reviewed:`/history fields — documented reasoning, not a coin flip.
6. All 4 headerless files get a `Status:` field added, based on the same review-worthiness standard already used elsewhere in the corpus (i.e. don't rubber-stamp `Approved` — read each one and decide).
7. Every change is captured in a ledger (file → issue → action taken → before/after diff summary).
8. The corpus is still valid afterward: same-or-higher retrieval eval score (`chat/tests/test_eval_runner.py` gold fixtures, before/after), and total file count only shrinks by the exact number of merged/deleted duplicates (no accidental data loss).

---

## 1. Ground rules (non-negotiable)

- **R0 — Backup before anything.** First action, no exceptions: `tar` or `cp -R` the entire `Training_Data_Notes/` directory to a timestamped path (e.g. `handoff/backups/Training_Data_Notes_pre-hygiene-fix_2026-09-21/` or a `.tar.gz` under the same). Verify the backup's file count matches the source (775) before proceeding. This is the only rollback mechanism available given there's no git.
- **R1 — No fabrication.** Do not invent a video/creator attribution for a mislabeled Source field if it can't be recovered from the note body, a matching transcript filename, or other traceable evidence. If unrecoverable, mark it `Source: Unknown (transcript-derived, provenance lost)` rather than guessing.
- **R2 — Merge, don't blindly delete.** When resolving a duplicate pair, read both fully. Keep whichever is more accurate/complete; if merging content adds value from the one you're removing, fold it in before deleting. Never delete a file whose content isn't fully superseded by the one you're keeping.
- **R3 — One issue category at a time.** Run and verify each of the 5 fixes as a discrete pass (their own commit-equivalent — since there's no git, that means their own backup checkpoint and their own ledger section) so a mistake in one pass doesn't get tangled with another.
- **R4 — Verify before declaring fixed.** Re-run the same grep/count commands from Phase 1 after each fix to confirm the issue is actually resolved, not just "should be" resolved.
- **R5 — Don't touch tier/trust metadata in this pass.** Adding the 10-tier taxonomy as machine-readable metadata to every note is Phase 3 scale-up work (a separate, larger effort), not part of this hygiene fix. Stay scoped to the 5 issues above.
- **R6 — Destructive-command discipline.** No `rm -rf`; use targeted `rm` on individually verified files only, and only after R0's backup is confirmed intact. No force-push (n/a, no git) — but treat every delete as if it were irreversible, because on this filesystem it is.
- **R7 — Retrieval regression gate.** After all 5 fixes land, rebuild the BM25 index and re-run the eval harness. If Hit@3/abstention regresses, investigate before declaring done — a dedup pass that removed a note the retriever actually needed is a real failure mode.
- **R8 — Report every judgment call.** Where you had to decide "is this really a duplicate" or "does this file deserve Approved," write the one-line reasoning in the ledger. No silent decisions.

---

## 2. Phase A — Backup and baseline (do this first, nothing else)

1. Create the backup per R0. Verify file count matches.
2. Run `apps/backend/src/kenn/knowledge/contradictions.py`'s measurement-claim extractor against the full current corpus. Save output (contradiction count + conflicting note-ID/pair list) to `docs/reports/KENN_CONTRADICTION_BASELINE_2026-09-21.md` (or `.json` alongside a short `.md` summary). This is the "before" number success criterion #3 of the scale-up prompt will need later — get it right.
3. Run the existing eval harness (`chat/tests/test_eval_runner.py`) once now, before any other change, and save the output as your "before" reference for R7.

---

## 3. Phase B — Fix the Source-field mislabeling (issue #2)

1. `grep -rl "^Source: Official Reference Documentation" Training_Data_Notes/` → get the full list (should be ~382 files, confirm exact count).
2. For each, read enough of the body to determine: is this actually a YouTube-transcript paraphrase (per R1, check for creator/video-style phrasing, cross-reference against `Training_Data_Transcripts/` filenames for a plausible match), or is it genuinely reference-documentation-derived?
3. Batch this — don't do it file-by-file by hand for 382 files. Write a small script that: (a) extracts candidate signals (creator names mentioned, phrasing patterns matching known transcript sources, cross-reference against the 28-video catalogue in `auto_harvest_masterclasses.py`), (b) proposes a corrected Source value per file, (c) flags low-confidence cases for manual spot-check rather than auto-applying. You (the agent) do the manual spot-check on a meaningful sample (e.g. 15-20%) before applying the rest.
4. Apply corrections. Log every file changed with old value → new value in the ledger.
5. Re-run the Phase 1 grep to confirm the count of files with the placeholder value has dropped to only the genuinely-correct ones (if any remain, they should be true official-documentation notes — verify a few by hand).

---

## 4. Phase C — Dedup pass (issue #3)

1. Build or reuse dedup tooling: prefer embedding similarity if `onnx_embedder.py` can be made to work (check the audit doc's note that the embedding model fetch script is missing — if still missing, don't spend this pass fixing that; fall back to a documented fuzzy method: normalized-title similarity + body text similarity via difflib or shingled hashing).
2. Run it across the full 775-file corpus (not the sample). Produce a candidate-duplicate-pairs report first (read-only) before touching any files.
3. Confirm the two already-known pairs are caught by your tooling (sanity check that the method actually works):
   - `ableton12-live-audio-effect-reference-pt9.md` vs `ableton12-live-audio-effects-ref-pt9.md`
   - `ableton12-live-instrument-reference-pt7.md` vs `ableton12-live-instruments-ref-pt7.md`
4. For every candidate pair (known + newly found), apply R2: read both, merge/keep-better, delete the redundant one, log the decision.
5. Report the total corpus size after dedup (775 − N removed) and keep the dedup tooling as a reusable script (`tooling/scripts/dedup_notes.py` or similar) since the scale-up plan will need it again at every future ingestion batch.

---

## 5. Phase D — Resolve status anomalies (issues #4 and #5)

1. `ableton-spectral-resonator.md`: read the full file, its `Reviewed:` field, and any surrounding context. Determine which status is correct (was it approved then later drafted-over without updating the top header, or vice versa?). Fix to a single consistent `Status:` value at the top of the file; remove or reconcile the conflicting body-level status line so the file has exactly one unambiguous status marker.
2. The 4 headerless files: read each in full, evaluate against the same bar the rest of the corpus uses for Approved vs Unreviewed (look at comparable approved notes on similar topics for the quality bar), and add the correct `Status:` header. Don't default to `Approved` — if a file reads as incomplete or unverified, mark it `Unreviewed` and say why in the ledger.

---

## 6. Phase E — Verify and close out

1. Re-run every Phase 1 grep/count command. Confirm: no self-contradicting status files, 0 headerless files, Source-field placeholder count down to genuine cases only, dedup count matches the ledger.
2. Rebuild the BM25 index (`build_index.py`) against the post-fix corpus.
3. Re-run `chat/tests/test_eval_runner.py` and compare to the Phase A "before" run (R7). No regression allowed without investigation.
4. Re-run the contradiction extractor once more; compare to the Phase A baseline — should be flat or lower (fixing mislabeled sources and duplicates shouldn't introduce new contradictions).

---

## 7. Deliverables checklist

- [ ] Verified backup of pre-fix `Training_Data_Notes/` (775 files), path recorded
- [ ] Contradiction baseline report saved (`docs/reports/KENN_CONTRADICTION_BASELINE_2026-09-21.md`)
- [ ] Eval harness "before" output saved
- [ ] Source-field correction ledger (382-ish files reviewed, count corrected, count left as-is with reason, count marked "Unknown/provenance lost")
- [ ] Reusable dedup script (`tooling/scripts/dedup_notes.py` or equivalent) + full-corpus dedup report + ledger of merges/deletions
- [ ] `ableton-spectral-resonator.md` status conflict resolved with documented reasoning
- [ ] 4 headerless files given correct `Status:` values with documented reasoning
- [ ] Post-fix corpus count reconciled (775 − duplicates removed = new total)
- [ ] Rebuilt BM25 index
- [ ] Eval harness "after" output, compared to "before," no unexplained regression
- [ ] Contradiction count "after," compared to baseline
- [ ] Final report: OBSERVED/INFERRED/UNVERIFIED lanes per estate convention, full ledger of every file touched and why
