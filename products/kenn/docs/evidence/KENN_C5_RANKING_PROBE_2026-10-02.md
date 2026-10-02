# Why the held-out wrapper rows are not a ranking-weight fix — 2 October 2026

Follows [the held-out rows receipt](KENN_WRAPPER_HELDOUT_ROWS_FRESH_INDEX_2026-10-02.md). That receipt said the fix was
a ranking or answer-lead change. This one tried to find a general change before touching code, and found none that
would hold up. No retrieval code was changed.

## Method

- Rebuilt the index on the GPU box from a fresh isolated copy (`/mnt/data/kenn-bakeoff/c5-20261002`, CPU, local
  manuals included): 3,907 chunks, 748 notes indexed, 39 skipped (38 plus the local harshness draft, which is
  Status: Draft). Same chunk count as the earlier receipt.
- Baseline on that index: coverage 128 / 128; wrapper held-out eval fails the same six rows.
- Probed `note_rank_key` for `upgrade-room-null`, `upgrade-kick-tail` and `upgrade-buffer-recording` and counted how
  many notes carry each topic.

## What the probe showed

`display_results` picks the primary note by `note_rank_key`: score, plus 30 per word of title/tag affinity, plus 5 per
topic overlap. The expected note loses on affinity, which counts any typed word that appears in a note's title or tags.

| Row | Winner (key, affinity) | Expected note (key, affinity) |
| --- | --- | --- |
| `upgrade-room-null` | FabFilter EQ frequency-range note (1485, 11) | `room-acoustics-monitor-placement` (1331, 5) |
| `upgrade-kick-tail` | Noisia "seven lessons" pt 1 (1630, 13) | `kick-drum-synthesis` (1029, 13), 4th |
| `upgrade-buffer-recording` | `home-vocal-recording` (1231, 10) | `audio-interface-buffer-latency` (1079, 10), 4th |

For the room row the winner wins on words like "frequency", "boost" and "EQ" matching its title. Those are common
words, so they count the same as the rare word that matters ("null").

## Why no general fix came out of this

- **Topic rarity.** The obvious idea is to weight topic overlap by how rare the topic is, so `acoustics` counts for
  more than `eq`. The topics are keyword-derived and loose: `midi` and `arrangement` tag 739 and 737 of 748 notes, and
  `acoustics` tags 156 (21%). Rarity does not separate the room note from the others, and a weight large enough to
  flip the room row (about 150 points on a score near 1,000) would move other rows.
- **Curated against transcript.** The earlier receipt suggested preferring curated notes over transcript notes. In the
  index the Noisia notes are marked `curated_kenn_note`, Status Approved, with no `transcript_file`. Only 21 chunks
  carry the transcript marker. The metadata cannot separate them, so a rule on it would not touch these rows.
- **Near-duplicate notes.** "Noisia seven lessons pt 1" and "7 things learned from Noisia pt 1" are two notes on one
  video and fill two of the three source slots on the kick row. Dropping the duplicate does not help on its own: the
  expected note's score (624) is under the 0.55 of the primary's (1,225 gives 674) that `display_results` requires of a
  second or third source.
- **Held-out rows.** Each of these changes would be tuned on the six rows it is meant to fix, so they would stop being a
  check.

## What would work, and what it needs

A passage-relevance model scoring the query against the top 12 to 20 retrieved chunks, as in experiment 2 of the
[research note](../research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md). It is general, it does not use the
six rows, and it can be scored on the 128 coverage rows as the tuning set. It needs a model file
(`cross-encoder/ms-marco-MiniLM-L-6-v2`, Apache-2.0, tens of MB) that is not on the box or the Mac, so I did not
download it. Running it as a measured spike on the box is the next step if Jack approves the download. If it does not
beat the current ranking on the coverage rows within the latency budget, the six rows stay as a known failing set.

## Other findings from this stretch

- `test_kenn_command_pilot.py::test_pilot_default_is_preflight_only_and_preserves_artifacts` failed on this Mac: the
  base model is not cached and there is no route to Hugging Face, and the dry-run wrote the raw `OSError` as its status
  where the test expects the word "unavailable". Fixed in `tooling/scripts/train_kenn_command_lora.py` by prefixing that
  status with `base_model_unavailable:`, like the missing-dependency case. KENN suite after the change: 3,551 passed,
  5 skipped, 0 failed.
- `/api/admin/reload-index` is a GET that clears caches and has no token. The obvious fix, requiring POST, would break
  `Audio_Too/server/app/suggested_notes_ops.py:164`, which calls it with GET. Left alone for a decision.

## Limits

One index build on one machine; ranks are single runs. The cross-encoder idea is untested here.
