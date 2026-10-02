# Echo-dependent coverage rows pass on a rebuilt index — 2 October 2026

Follows [the echo diagnosis](KENN_EVAL_ROWS_RELATED_QUESTION_ECHO_2026-10-02.md). That receipt left the answer text
written but not verified, because the plan says not to rebuild the index on this Mac. This one is the verification,
done on the GPU box.

## Method

- Copied the KENN tree plus the local, git-ignored `Training_Data_Notes` into two isolated directories under
  `/mnt/data/kenn-bakeoff/a3-echo-20261002/`: `orig/` (notes as they were) and `edited/` (notes with the step 7 text).
  Each has its own `data/index`, so nothing on the box's existing indexes or on the Mac's live index was touched.
- Built each index with `kenn/retrieval/build_index.py` on CPU, embeddings on, no `KENN_SKIP_EMBEDDINGS`.
- Ran `eval_chat_coverage.py --receipt` and `packages/chat/eval_runner.py --receipt` against each copy, LLM off.
- Stripped macOS `._*` files from the copied notes first; they broke note parsing on Linux.

## The three note edits

All in `apps/backend/src/kenn/Training_Data_Notes/`, step 7 of the "Try this" list. Texts for the first two are
also in the echo receipt; the third is new here.

- `thin-vocal-body.md`: "If the vocal was recorded too far from the mic, EQ will not fully fix it: a boost around
  150-300 Hz adds some weight, but the room and the missing proximity effect stay in the take. Treat EQ as a partial
  repair and re-record close, on-axis, if you can."
- `arrangement-energy-and-transitions.md`: "If the track feels boring and you are not sure what to do next, do not
  add a layer yet. Loop the flattest eight bars, mute half the parts, then bring back one thing at a time with a
  change at the section boundary (a filter move, a drop-out or a fill)."
- `mastering-prep-and-headroom.md` (new): "So, should you leave a limiter on before mastering? Take off any limiter
  that is only there for loudness. One that is part of the sound can stay if it is not clipping the output, and it
  is worth sending a second export without it so the mastering engineer can choose."

The third was not in the earlier plan. `mastering-prep-headroom` is a coverage row whose question is a line in that
note's own "Related questions", so it was echo-dependent too. The Mac's index predates `f0ebeba6` and still has
those question chunks, which is why that row looked fine here. A fresh index fails it.

## Results

Same code, same 3,907-chunk index size in both builds (748 notes indexed, 38 skipped as not approved, 2 PDFs).

| Run | Coverage | Coverage failures |
| --- | --- | --- |
| original notes | 125 / 128 | `arrangement-energy-transitions`, `mastering-prep-headroom`, `ambiguity-thin-vocal-eq-vs-recording` |
| two notes edited | 127 / 128 | `mastering-prep-headroom` |
| three notes edited | **128 / 128** | none |

Package-wrapper held-out eval: `passed=False` in all three runs, with the same six failing rows each time, so the
note edits changed nothing there: `harsh-after-mastering`, `eval-followup-snare-layer-mono`,
`upgrade-buffer-recording`, `upgrade-room-null`, `upgrade-kick-tail`, `internet-itu-target-boundary`. Abstention
26/26, public corpus boundary 13/13, negative-advice guard 29/30.

## What this does and does not show

- The two original echo coverage rows and the third found here now pass for answer-bearing reasons, not through the
  question list.
- `eval-followup-snare-layer-mono` is listed in the echo diagnosis as echo-dependent, but it is a held-out row and
  no note was written for it. It still fails. The other five held-out failures are the ones already recorded in the
  plan and were not touched.
- This is one run per index on one machine. The Mac's live index (4,642 chunks, v-db8c6334cf63) is stale against
  current code and was not rebuilt or promoted. Promoting a rebuilt index still needs the parity, digest, recall and
  rollback evidence the plan asks for.
- The note edits are local and git-ignored. The box copies are scratch; the notes on the Mac are the ones that
  count.
