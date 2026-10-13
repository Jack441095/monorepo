# Figure tags off the delivered answer, request-scoped call timing, named empty streams — 13 October 2026

Cloud session, Fake Live, stubbed model replies. No model or Live run, so nothing here is a speed or quality result.
Three open follow-ups from the plan, each confirmed on the current code before it was changed.

## The producer saw the gate's [#n] tags

`d783942b` (11 Oct) has the model tag each figure with the excerpt it came from, and the gate checks that tag. The
plan's own follow-up: "answers show `[#2]` to the producer as written. Strip the tags or map them to the Sources
list numbering." Confirmed with the real `make_answer()` and `answer_payload()` over fixture retrieval: an accepted
answer reached the payload as "Set the release to 150 ms [#1] so the bass recovers".

Stripped rather than mapped. The Sources list under an answer is bulleted, de-duplicated and capped at three
(`sources_block`), so excerpt 2 is not reliably its second line, and two excerpts from one note share a bullet.

- `chat_grounding.display_answer()` removes every tag through the existing `repair_misattributed_citations()`, with
  each tag marked "no holder". It reuses that function's spacing rules (no glued words, no "()" left behind, line
  starts kept) and its refusal when a figure would change; on refusal the tagged text is returned. That refusal is
  real, not hypothetical: a pre-11 Oct hex id such as `efac7b4076db` holds "4076db", which reads as 4076 dB, so that
  tag stays.
- `_answer_payload_raw()` applies it after the last check that reads the tagged text and before the payload is
  built, so the companion's `/api/ask`, the background upgrade, session memory and the semantic cache all hold
  the producer's text. The gate still judges the tagged text (a test spies on it).
- Not changed: the streaming path (`answer_payload_stream`, used by `kenn.core.chat` and `chat_cli`, not by the
  companion app, which calls `/api/ask` with `stream: false`). Its tokens reach the terminal as the model writes
  them, so removing tags there needs a token-boundary filter; left as is.

Tests: `test_answer_citation_tags_display.py`, 11 cases. Removing the strip at payload construction fails the
producer-facing case.

## Route-log timing came from the global newest call

Audit item 2 (11 Oct): `c288275a` fixed the seconds/milliseconds mix-up; "take timing from request-scoped usage
rather than the global last call" was not done. `_last_call_timing()` read `_global_usage[-1]`. Local calls share
one model slot, and a refused request records its own `busy` row, but any call finishing later on another thread
became the newest record, so its load/prefill/decode was written onto this answer's row.

- `llm_rewrite` keeps the newest call per thread (`last_thread_usage()`); each HTTP request and each background
  upgrade runs on its own thread. `_last_call_timing()` reads that.
- `make_answer()` calls `forget_thread_usage()` on entry, like its other per-thread outcome fields, so on the
  terminal chat (one thread for every question) an answer that never reached the model does not borrow the
  previous question's call.

Tests: `test_generation_outcome_timing.py`, two new cases (a busy refusal logs `call busy 0ms` while another thread's
completed call is the global newest; an earlier answer's call on the same thread is not reused). Reading the global
newest again fails 2; dropping the reset on entry fails 1.

## The stream's empty reply was a bare reason

The plan's review follow-up: "The streamed path still logs the bare reason." A stream that dies already records
`generation stream cut short: <exception>`; one that ends with no text recorded only "generation returned no
answer", which the C1 harness counts as its own unexplained cause beside the payload path's named ones. It now
reads `generation returned no answer: empty reply` and stays transient (not cached).
Tests: `test_stream_no_answer_reason.py`, 2 cases.

The same follow-up's last part, "match the chat-test skip on the test name rather than a `tests/` path segment",
could not be located in this tree; its source commit (`2d8d779d`) predates the history kept in this clone. Left open.

## Checks

- Scoped: 19 passed (tags, empty stream, payload cache); 22 passed (generation outcome timing and log).
- Full backend suite (`KENN_LIVE_BACKEND=fake`): 4821 passed, 137 skipped, 1 failed, the pre-existing
  `test_query_typo_correction.py::test_typo_query_routes_to_production_and_avoids_weak_match_early_return`, which
  also fails on clean `main` (no git-ignored index in this container).
