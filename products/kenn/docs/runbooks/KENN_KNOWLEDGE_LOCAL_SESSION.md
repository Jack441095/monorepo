# KENN knowledge: the local steps, in order

The checklist for the knowledge work that needs the Mac, the owner or a GPU box. It is not a roadmap: the items are
already in `KENN_PLAN.md` (C1, C5, L2 and the 13 Oct decisions under stage 2), and this page only puts their local
steps in the order they depend on each other. Tick progress in the plan, not here.

Why this order: the evidence says most wrong answers come from retrieval choosing the wrong note, not from missing
knowledge (11 Oct reference-figure check; 8 Oct ranking diagnosis). So measure the retrieval fix first, then let
the owner's grades say which misses are real gaps, and only then add notes and rebuild once.

Everything runs with `KENN_LIVE_BACKEND=fake`; nothing here writes to Live. Mains power for every timed run.

## 1. Measure the retrieval draft against main (Mac, about 30 minutes)

Branch `draft/synonym-weight-stemming`: untyped topic synonyms at 0.35, typed words reach their inflections, each
typed word counted once. The commands, the bar and what was left out are in that branch's
`docs/evidence/KENN_SYNONYM_WEIGHT_AND_STEMMING_DRAFT_2026-10-13.md`. In short:

```bash
cd ~/path/to/monorepo && git pull --ff-only origin main && git fetch origin
git worktree add workspace/worktrees/kenn/synonym-weight origin/draft/synonym-weight-stemming
ln -s "$PWD/products/kenn/apps/backend/src/kenn/data" \
      workspace/worktrees/kenn/synonym-weight/products/kenn/apps/backend/src/kenn/data
for tree in . workspace/worktrees/kenn/synonym-weight; do
  (cd "$tree/products/kenn" && python3 tooling/scripts/evaluate_retrieval_modes.py --cutoff 4 \
     --output "/tmp/retrieval-$(git rev-parse --short HEAD).json")
done
(cd workspace/worktrees/kenn/synonym-weight/products/kenn && \
  KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests)
```

Then the 8 Oct ranking-diagnosis scripts in `kenn-evaluation-data` for probe concepts and the abstain rows. Merge
only with no loss on coverage, held-out or probe concepts, measured together. If it holds, the next retrieval item
is the topic multiplier (×0.45 to ×3.45), which the draft deliberately left alone.

## 2. Grade v7 (owner)

The review sheets are `cand-*.review.md` in `kenn-evaluation-data/2026-10-11-gate-qualification-bench-v7/`.
Owner grades are the answer gate's open half (8 Oct decision), and the wrong rows are the failed-question list L2
says notes should be written for. `adjudicate_human_review.py` and `export_human_review_forms.py` in
`tooling/scripts/` handle packets built by the review builders, if you prefer forms to the sheets.

Then hand the graded rows to the next session. Each miss gets sorted into: the note is missing, the note ranked too
low, the excerpt was cut before the answer, or the gate refused a correct answer. Notes are drafted only for the
first kind.

## 3. Review the drafted notes (owner)

Two drafts were delivered as files on 13 Oct, each with a check sheet listing every figure and its source:

- `precedence-effect-haas.md`: three figures rest on secondary citations and are marked "please confirm"; two Live
  control names need checking in Live 12.
- `fabfilter-pro-q3-dynamic-eq-de-essing.md`: every claim checked against FabFilter's own Pro-Q 3 manual, pages
  13-15.

Keep them outside `Training_Data_Notes` until approved. On approval set `Status: Approved` and the `Reviewed:` date.
When the Pro-Q 3 note goes in, decide whether the probe row `trap-third-party-plugin` becomes an `answer` row; its
current wording says KENN has no FabFilter knowledge, which will no longer be true.

## 4. Rebuild once and bench (GPU box, then Mac)

- Copy the approved notes into the corpus, together with any notes from step 2, so there is one rebuild, not
  several.
- Rebuild on the GPU box (physical GPU 1, `CUDA_VISIBLE_DEVICES=1`), never on the Mac (L2), with
  `python3 apps/backend/src/kenn/main.py build` and the parity, digest, recall and rollback evidence L2 asks for.
- Bench with the v7 harness on the new index. The result is not comparable with v1-v7, which ran on the pinned
  `v-5f6964698b76`; record it as a new baseline.

## 5. Reranker trial (after 1-4)

Decided 13 Oct: an off-by-default trial, served only if it clears experiment 2's bar (0.05 more recall@4 or 20%
fewer retrieval-caused failures, inside 150 ms p95 and 250 MB) on rows it was not tuned on. `onnxruntime` is
already a dependency; pin the model file by digest and licence when it is added.

## Also waiting on the Mac

- C1: `products/kenn/tooling/scripts/c1_supervised_session.sh` (seven stages, about 1.5 to 2 hours).
- `kenn-app` sync: `products/kenn/tooling/scripts/sync_kenn_app.sh --source-ref main --branch main --push`.
