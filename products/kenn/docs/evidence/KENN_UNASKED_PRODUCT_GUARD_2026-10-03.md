# Generated answers may not name plugin brands nobody mentioned, 3 Oct 2026

"advice on mixing low end?" produced a chain naming FabFilter Pro-Q3, Pro-D2 and Timeless. Nobody had mentioned FabFilter in that question, and the notes held no such product. Whether the model invented it or an earlier "fab filter" turn leaked into its context is still open (the advanced-question probe on the Mac settles that), but either way the answer should not reach the user.

## Change

`unasked_product_names` in `core/chat_grounding.py` looks for a closed list of third-party makers and products (FabFilter and its Pro-* line, Waves product names, iZotope, Soundtoys, Valhalla, UAD, Native Instruments, Serum, Omnisphere and a few others). A maker counts as unasked when the answer names it and neither the question nor the retrieved notes do. `generated_answer_validation` adds the warning "generated answer names a product that nobody mentioned" and an `unasked_products` field. The warning is appended after the existing ones so the first-warning grouping in `route_latency_report.py` doesn't move. A rejected answer falls back to the template like any other failed check.

Ableton's own devices are not on the list, and bare "waves" is not a brand (only the Waves product names are).

## Verification

Fake Live, from `products/kenn`:

- `test_unasked_product_names.py`: 13 passed. The gate test failed with the check switched off and passes with it on.
- Full backend suite: 4059 passed, 137 skipped, 9 failed. All 9 are in the earlier cloud baseline (the stream prefix guard, answer-upgrade context, loudness, note-section, sample-library and stream-delivery tests).

## Limits

The list is short and hand-written, so a brand it doesn't know still gets through. A plugin the user named in an earlier turn but not in the current question is treated as unasked, so a follow-up that uses it will fall back to the template; that is the safer side for now. The streamed path checks the finished answer, not each token. No real model was run.
