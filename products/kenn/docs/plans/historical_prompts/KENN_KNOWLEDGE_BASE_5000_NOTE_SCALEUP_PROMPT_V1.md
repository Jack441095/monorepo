# KENN KNOWLEDGE BASE — 5,000-NOTE SCALE-UP — AGENT PROMPT (V1)

> **What this file is:** a reusable, self-contained prompt that drives an AI coding agent (Claude Code / Cline / Codex / any repo-aware agent) to grow KENN's approved knowledge-note corpus from its current size to 5,000 high-quality, correctly-classified notes — without diluting trust, causing contradictions, or padding the count with junk.
>
> **How to use it:** open the workspace root (`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/handoff/kenn-full-product-slo`) and instruct the agent: *"Execute `KENN_KNOWLEDGE_BASE_5000_NOTE_SCALEUP_PROMPT_V1.md` in full. Produce every deliverable in §8."* Run Phase 1 (inventory) in read-only mode first; only start bulk ingestion after the owner approves the plan in §6.
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-21 · **Supersedes:** none

---

## 0. Role, mission and success criteria

You are a **knowledge-base engineer** for an AI audio assistant (KENN, for Ableton Live). Your mission: take the approved note corpus from its current baseline to **5,000 approved notes**, while holding quality, trust-tier discipline, and retrieval accuracy constant or better.

### Baseline (verify, don't trust — re-count before starting)

- `apps/backend/src/kenn/Training_Data_Notes/`: 775 markdown files as of 2026-09-21 (763 `Status: Approved`, 5 `Status: Unreviewed`, remainder unclassified by header). Gap to target: **~4,225 net new approved notes**.
- `apps/backend/src/kenn/Training_Data_Sources/scraped_articles/`: 47 scraped article files (via `tooling/scripts/scrape_ableton_knowledge.py`, `scrape_large_ableton_corpus.py`, `scrape_producer_masterclass_articles.py`).
- `apps/backend/src/kenn/Training_Data_Transcripts/`: 15 of 28 catalogued YouTube masterclass transcripts harvested (`tooling/scripts/auto_harvest_masterclasses.py`, daemon running, was previously stuck on IP-level YouTube cooldowns — fixed 2026-09-21 to skip blocked videos instead of freezing).
- Canonical taxonomy (10 tiers, trust 1.0 → 0.2) and governance rules: `docs/reports/KENN_KNOWLEDGE_BASE_AUDIT.md` §2 and §5. Read this file in full before writing a single note.
- Note-generation tooling: `tooling/scripts/generate_knowledge_notes.py` (raw source → structured note).
- Trust scoring: `apps/backend/src/kenn/knowledge/trust_scores.py` (Manuals 1.0, Notes 0.9, Transcripts 0.7 defaults).
- Retrieval: `apps/backend/src/kenn/retrieval/build_index.py`, `index_store.py` (BM25, SQLite).
- Contradiction registry: `apps/backend/src/kenn/knowledge/contradictions.py`.

**Success criteria (all must hold before you stop):**
1. Approved note count (`Status: Approved` header, verified by grep, not by filename count) reaches **≥ 5,000**.
2. Every new note is classified under exactly one of the 10 taxonomy tiers (§2 of the audit doc) with the correct trust score, and states fact-vs-preference explicitly per Tier 5/6 rules.
3. Zero net-new unresolved contradictions: running `knowledge/contradictions.py`'s measurement-claim extractor over the full corpus before/after shows the contradiction count did not grow faster than the corpus (report the ratio).
4. Zero exact or near-duplicate notes (dedup pass documented in §4.2 — cite the method and the count removed/merged).
5. BM25 retrieval eval (`chat/tests/test_eval_runner.py` gold fixtures) shows no regression in Hit@3 / abstention behavior after the corpus grows — same test suite, before/after numbers cited.
6. No note in Tier 10 (Unsafe for Automatic Action) or unresolved Tier 9 (Conflicting) reaches `Status: Approved`.
7. Every claim in the final report cites file path, count command, or test output. No estimated numbers presented as measured.

---

## 1. Ground rules (non-negotiable)

- **R1 — Quality over count.** 5,000 junk notes is a failure, not a win. A note that duplicates an existing one, states an unsupported absolute ("always cut 500 Hz"), or invents a parameter is worse than no note.
- **R2 — Taxonomy or it doesn't get approved.** Every note must carry `Type`, `Status`, and an inferable trust tier per the audit doc's 10-tier scheme before it can move to `Status: Approved`.
- **R3 — No fabricated facts.** Do not let the agent (or any LLM step in the pipeline) invent DSP claims, Ableton parameter names/ranges, or manufacturer specs. Established-principle and official-behavior tiers (1–3) must trace to a real source (manual, standard doc, verified transcript) — cite it in the note.
- **R4 — Copyright and ToS discipline.** Scraped articles and YouTube transcripts are ingested for internal retrieval-augmented use, not verbatim republication. Summarize/extract atomic claims into original note text rather than reproducing large verbatim blocks. Respect robots.txt and site ToS on any new scrape target. Do not scale scraping in a way that gets NITE DSP's IP blocked or violates a publisher's terms.
- **R5 — Respect the YouTube harvester's rate limits.** The auto-harvester was previously stuck for 90+ minutes hammering one blocked video (fixed 2026-09-21, see `tooling/scripts/auto_harvest_masterclasses.py`). Do not remove the cooldown/backoff logic or run multiple harvester instances in parallel against the same IP.
- **R6 — Dedup before approval.** Every batch of new notes must be checked against the existing corpus (embedding similarity or fuzzy text match) before being marked Approved. Near-duplicates get merged, not both kept.
- **R7 — Destructive-command ban.** No `rm -rf` outside throwaway dirs, no force-push, no publishing scraped content externally, no paid-API calls at scale without owner sign-off on cost.
- **R8 — Secret hygiene.** `auto_harvest_masterclasses.py`'s `rsync_to_gpu()` currently writes a plaintext SSH password to `/tmp/kenn_askpass.sh`. Do not propagate this pattern to any new script; flag it in your report as a pre-existing issue rather than fixing it silently (out of scope for this task unless the owner asks).
- **R9 — LOM stays the source of truth.** New notes must never become a channel for live-control parameter values — those still come only from `get_device_parameters` per the audit doc's governance rules (§5). Notes are retrieval context, not executable instructions.

---

## 2. Phase 1 — Inventory and gap analysis (read-only)

1. Re-run the counts in §0 yourself; don't trust the numbers above without verifying (`find`, `grep -rh "^Status:"`).
2. Classify the existing 775 notes by taxonomy tier and by topic area (Ableton devices, mixing fundamentals, mastering, genre convention, Wwise/game audio, monitoring, workflow/automation, etc.) — sample if full classification is too slow, but state the sample size and method.
3. Identify thin topic areas relative to the 16 golden-eval categories in the audit doc (§4) — e.g., if "Automation" or "Mono Compatibility" has near-zero notes, that's a priority gap, not a nice-to-have.
4. Produce a gap table: topic area → current note count → estimated target count → source(s) that can fill it.

---

## 3. Phase 2 — Source expansion plan (evaluate each; get sign-off before scaling)

Ordered by expected yield-to-risk ratio:

### 3.1 Existing scrapers — scale up, don't reinvent
- `scrape_ableton_knowledge.py`, `scrape_large_ableton_corpus.py`, `scrape_producer_masterclass_articles.py`: audit their current target lists/query sets, identify why only 47 articles exist, and expand the source list (Ableton official docs/manual, Sound on Sound archive, manufacturer knowledge bases — respecting R4).

### 3.2 YouTube masterclass harvester — expand the catalogue
- Current catalogue is 28 videos (Dan Worrall, FabFilter, Mr. Bill, Baphometrix). Research and propose additional reputable channels/creators covering the thin topic areas from §2 step 3. Note: one catalogued video (`fx_8VhKBnzg`, "Mr. Bill — Studio Cast 2.1") is confirmed offline/unplayable — remove or replace it.
- Each transcript is raw text, not a note. `generate_knowledge_notes.py` must turn each into multiple atomic, tier-classified notes (one claim per note) rather than one giant transcript-shaped note.

### 3.3 Authored notes (highest trust, slowest to produce)
- Jack's own 12 years of studio/game-audio/Ableton experience is a source no scraper can replicate. Propose a lightweight capture workflow (e.g., short dictated voice notes → transcribed → structured into notes) for Tier 4–6 material that scraping can't reach authentically. Flag this as a candidate for owner involvement, not something the agent invents unsupervised.

### 3.4 Structured/reference sources (highest trust tier, likely small volume)
- EBU R128, ITU-R BS.1770, AES recommendations, official Ableton Live 12 manual sections. Small in count but fills Tier 1–3 gaps with maximum trust score. Prioritize for topics where Tier 1–3 coverage is currently thin.

**Deliverable for this phase:** a source-by-source yield estimate (expected new approved notes per source, with method and time/risk cost) that sums to covering the ~4,225-note gap, plus which sources need owner approval before scaling (anything scraping at higher volume/frequency, anything requiring new credentials or paid access).

---

## 4. Phase 3 — Ingestion pipeline (build once, run repeatedly)

1. **Raw → atomic extraction:** for each source type, extract one discrete claim per note (not one note per article/transcript). Use `generate_knowledge_notes.py` as the base; extend it if it doesn't already atomize well.
2. **Taxonomy + trust assignment:** classify each candidate note into one of the 10 tiers before it's written to disk. Tier 9 (Conflicting) and Tier 10 (Unsafe) notes never reach `Status: Approved` — route them to a quarantine folder instead.
3. **Dedup pass:** before marking `Status: Approved`, check each candidate against the existing corpus (embedding similarity via the existing ONNX/BM25 tooling, or a fuzzy-hash fallback if ONNX is still blocked per the audit doc). Merge or drop near-duplicates; log the count removed.
4. **Contradiction check:** run `knowledge/contradictions.py`'s measurement-claim extractor on each new batch against the existing corpus before approval. Any new conflict gets flagged for manual resolution, not silently approved.
5. **Batch, don't big-bang:** ingest in batches (e.g., 250–500 notes at a time), re-running the BM25 index build and the eval harness after each batch so a regression is caught early and attributable to a specific batch.

---

## 5. Phase 4 — Quality gates (apply to every batch)

- Sample-review at least 5% of each batch's new notes by hand (or by a second LLM pass acting as reviewer) against the audit doc's risk categories (taste-as-fact, invented parameters, overconfident loudness targets, prompt-injection risk in scraped text).
- Re-run `chat/tests/test_eval_runner.py` against the gold fixtures after each batch; Hit@3/MRR and abstention behavior must not regress.
- Track approved-note count, contradiction count, and eval score together after every batch so quality-vs-volume tradeoffs are visible, not discovered at 5,000.

---

## 6. Plan gate

Before ingesting anything beyond a small pilot batch (≤100 notes for pipeline validation), present: the gap table (§2), the source-by-source yield plan with risk flags (§3), and the batching/rollback plan (§4). **Wait for owner approval** before scaling scraping frequency/volume or touching any new external source. Read-only + pilot-batch-only until then.

---

## 7. Report format

Use the estate convention: `OBSERVED:` (command + output, cited) → `INFERRED:` (confidence HIGH/MEDIUM/LOW) → `UNVERIFIED:` (and why). All counts from actual `find`/`grep`/test-runner output; no estimates dressed as measurements.

---

## 8. Deliverables checklist

- [ ] Verified current-state counts (notes, status breakdown, taxonomy/topic classification) — §2
- [ ] Gap table: topic area → current → target → source(s) — §2
- [ ] Source-by-source yield plan with risk flags and owner-approval markers — §3
- [ ] Extended/repaired ingestion pipeline (`generate_knowledge_notes.py` + dedup + contradiction check) — §4
- [ ] Batch ledger: each batch's size, source, dedup count, contradiction count, eval score before/after — §4–5
- [ ] Final approved-note count ≥ 5,000, verified by `grep -rc "^Status: Approved"`
- [ ] No eval regression (BM25 Hit@3/abstention) across the full run
- [ ] Updated `docs/reports/KENN_KNOWLEDGE_BASE_AUDIT.md` reflecting the new corpus size and any taxonomy shifts
- [ ] Final report with OBSERVED/INFERRED/UNVERIFIED lanes, flagged risks (R8 secret hygiene, R4 copyright), and next-lever recommendations
