# SLO correction promotion workflow v1

The correction path is intentionally four stages:

1. The application appends a pending, typed JSONL correction record before
   applying a user taxonomy override.
2. `ingest_cpp_correction_log.py` validates the log and emits a non-overwriting
   owner-review packet.
3. An owner fills a decision CSV with `accept`, `reject`, or `defer` for every
   packet row. Rejections and deferrals require a note.
4. `promote_correction_review.py` writes a promotion-candidate manifest and a
   receipt. Accepted rows are marked `owner_approved_pending_rebuild`.
5. `build_owner_approved_training_manifest.py` matches accepted rows against
   the canonical collection-aware manifest by path and complete-file SHA-256.
   Unknown paths, hash changes, duplicate aliases, and sealed validation rows
   are blocked.

The fifth step does **not** modify the training corpus. A separate dataset
rebuild must verify content identity, collection grouping, duplicate policy,
label authority, and the collection-held-out evaluation protocol before any
accepted row can become ground truth.

Safety invariants:

- no audio is copied, decoded, renamed, or modified;
- the source JSONL and review packet are immutable inputs;
- no model, policy, or rename plan is changed;
- every packet row receives an explicit owner decision;
- acceptance is not training promotion.

This separation is necessary because SLO's strongest measured gains came from
real breadth-first labels, while unreviewed corrections are still fallible
human observations and must not silently become a new benchmark.
