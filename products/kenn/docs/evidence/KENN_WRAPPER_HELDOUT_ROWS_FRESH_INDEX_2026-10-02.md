# Why the six held-out wrapper rows still fail — 2 October 2026

Diagnosis only, no behavior change. Follows [the echo rebuild receipt](KENN_ECHO_ROWS_BOX_REBUILD_2026-10-02.md).
Ranks come from `core/chat_retrieval.search` (the path the wrapper eval uses) on the fresh 3,907-chunk index built on
the GPU box, three-note edited copy, CPU, LLM off. Rank is by distinct source note.

| Row | Expected note | Rank | What actually fails |
| --- | --- | --- | --- |
| `upgrade-kick-tail` | `kick-drum-synthesis` | 4 | Behind two long Noisia transcript notes and `kick-tuning-with-bass`; the 3-source cut drops it, so the expected source is missing. |
| `upgrade-room-null` | `room-acoustics-monitor-placement` | 2 (tied score with the #1 note) | The note is cited, but the answer text is built from the FabFilter EQ note and tells the user to work the bass bands. The note's own rule ("do not EQ a narrow null caused by cancellation") is step 5, not the lead. This is the one to care about: the answer is the opposite of the right advice. |
| `upgrade-buffer-recording` | `audio-interface-buffer-latency` | 5 | Four vocal-recording notes outrank it, the match is judged weak and the engine abstains with no sources. The note already says "start around 64 or 128 samples". |
| `internet-itu-target-boundary` | `itu-bs1770-k-weighting-gated-loudness` | 1 | Right note on top, but the answer is the generic mastering template and never says "measurement", "specification" or "target". Answer composition, not retrieval. |
| `eval-followup-snare-layer-mono` | `snare-clap-layering` | 13 | Stereo-width and layering notes outrank it for the combined question. |
| `harsh-after-mastering` | none | no hit | The public wrapper abstains: no note is about harshness after mastering limiting. A real corpus gap. |

## Why these were not tuned here

Five of the six already contain, or rank next to, a note that has the answer. Closing them means changing ranking
weights, the three-source cut, or how the answer body is chosen. These are the held-out rows: adjusting the ranker
until they pass would stop them being held out, and a fix tuned to six questions is likely to move the other 128
coverage rows. Wording the notes to echo each question would repeat the problem the echo exclusion was added to stop.

What would be a sound fix, for Jack to schedule:

- Prefer a curated, approved how-to note over a long transcript note when their relevance is close (`upgrade-kick-tail`,
  `upgrade-room-null`, `upgrade-buffer-recording`, snare). Develop it against a separate tuning set and keep these six
  untouched for the check.
- Build the answer lead from the top curated note's "Short answer" instead of the top chunk, so a null is not answered
  with an EQ boost (`upgrade-room-null`, `internet-itu-target-boundary`).
- Write and review a mastering-harshness note (`harsh-after-mastering`); needs Jack's sign-off on the content.

## Limits

One index build on one machine; ranks are single runs. No code or note was changed for this receipt.
