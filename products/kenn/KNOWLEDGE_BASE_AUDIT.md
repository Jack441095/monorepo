# KENN Knowledge Base — Provenance Audit (Work Package C)

**Date:** 2026-09-01. **Scope:** read-only audit of `Audio_Too/studio/kenn/kenn/Training_Data_Notes/` (the actual knowledge notes — distinct from `kenn/knowledge/*.py`, which is the reasoning/contradiction/trust-score *code*, not note content) against the sprint's Work Package C provenance spec. No code changed in this pass.

## What already exists (real, working, more than expected)

- **252 markdown notes**, each with a consistent structured format: `Type`, `Tags`, `Status` header fields, then `Short answer` / `Try this` / `Why it matters` / `Common mistakes` / `When this does not apply` / `Related questions` sections.
- **A real, enforced review-status gate.** `build_index.should_index_note()` excludes any note whose `Status` is not `approved`/`unmarked`/empty. Of 252 notes: 224 `Approved` (+10 with trailing-whitespace variants, still approved), 6 `Draft`, 12 `Unreviewed` — the 18 Draft/Unreviewed notes are correctly excluded from the retrieval index at build time, not just cosmetically labeled.
- **A contradiction-detection gate on every index rebuild.** `build_index()` runs `scan_for_contradictions(notes_dir)` and refuses to rebuild if open contradictions exceed `KENN_MAX_CONTRADICTIONS` (default 50) — real ingestion safeguard, not aspirational.
- **A dynamic trust-score system** (`kenn/knowledge/trust_scores.py`, SQLite-backed): a per-source score starting from a filename-heuristic default (`.pdf`/"manual" → 1.0, `.md`/"note" → 0.9, transcript/podcast → 0.7, else 0.5) and adjusted over time by usage/correction signals.

## Gaps against the Work Package C spec

| Required field | Coverage | Notes |
|---|---|---|
| Topic/subtopic | 252/252 (`Type`, `Tags`) | No strict subtopic taxonomy, but functional |
| Concise explanation | 252/252 (`Short answer`) | — |
| Practical recommendation | 252/252 (`Try this`) | — |
| Conditions/exceptions | 252/252 (`When this does not apply`, `Common mistakes`) | — |
| Review status | 252/252 (`Status`), **enforced at index time** | Real gate, not cosmetic |
| Source + author | **36/252 (14%)** (`Source creator`) | The other 216 are unsourced internal/practitioner notes with no attribution field |
| URL/doc reference | **36/252 (14%)** (`Source URL`) | Same 36 as above |
| Source date | **15/252 (6%)** (`Source version`) | Weak; `Reviewed:` (141/252, 56%) is a different field (internal review date, not source date) |
| Retrieval date | **0/252** | No field exists at all |
| Confidence (per-item) | **0/252** as a static field | The dynamic trust-score system is a real substitute, but see limitation below |
| Evidence class | **0/252** | No field distinguishes "standard/spec" vs "manufacturer manual" vs "practitioner note" vs "opinion" |
| Related Mix Review fault families | **0/252** as an explicit field | Free-text `Tags` partially cover it today: 14 notes tag `headroom`/`clipping`, 2 tag `imbalance`/`panning`/`stereo` — usable as a starting map, not a formal one |
| Knowledge-base version | **0/252**, no corpus-level version either | No versioning scheme found anywhere in the KB pipeline |

## The one real limitation worth flagging

The dynamic trust-score default is **filename-heuristic only** (`.md` → 0.9 regardless of content), so it currently cannot distinguish a cited AES standard (`aes-td1008-internet-streaming-loudness.md`, real external provenance) from an unsourced internal opinion note (`mix-review-low-headroom-clipping-repair.md`, no `Source` fields at all) — both start at the same 0.9 trust score. The `Source creator`/`Source URL` fields that *would* let the system tell these apart exist on only 14% of notes and are not read by `trust_scores.py` at all today.

## Recommendation (not executed this pass — audit only)

This is real infrastructure, not a rebuild. The smallest coherent next step would be:
1. Add `evidence_class` (e.g. `standard`, `manufacturer_manual`, `practitioner_note`, `internal_opinion`) and `related_fault_families` as new frontmatter fields, backfillable in bulk from existing `Source creator`/`Tags` data for the ~40 notes that already have it, defaulting the remaining ~210 to `practitioner_note`/`internal_opinion` rather than leaving the field absent.
2. Feed `evidence_class` into `trust_scores.get_source_default_trust()` so a cited standard actually scores higher than an unsourced note of the same file type.
3. Add `retrieval_date` at the point a chunk is served (in `chat_answer.py`'s response payload), not in the static note — this is a request-time fact, not a note-level fact, so it doesn't need a backfill.
4. Corpus-level KB version can be the index build's content hash (already computable from `chunks.jsonl`); this is cheap to add to the chat receipt's provenance block alongside `analysis_version`-style fields.

Not done in this pass because it touches the read-only `Audio_Too` engine tree (the notes and `trust_scores.py` both live there), which requires the same read-only-boundary care as the Mix Review work — this needs its own scoped work package, not a drive-by edit during an audit.
