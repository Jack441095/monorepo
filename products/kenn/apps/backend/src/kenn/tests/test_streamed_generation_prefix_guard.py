"""Streamed generation must reach the producer as the model writes it, without letting a rejected number out.

Phase 2 of the acceptance work, 2 Oct 2026. The stream used to append every token to a list, throw the list
away, and only yield text after the model had finished AND the gate had run, so time-to-first-token was the
whole generation plus the whole 1.16 ms validation pass. The gate's text work is 1.16 ms median / 1.87 ms max
over the 29 captured answers, so there is no latency to win by making validation faster; the only reason the
code buffered was to avoid showing the producer text the gate would discard.

Two of the gate's eight warnings are prefix-sound, so a cheap per-token guard can stop them before the number
leaves the building: unsupported measurements (8 of the 9 rejections in the 2 Oct 2026 run of 29 queries, 5 of
7 in the run before it) and claims it changed the Live set (2 of 7). Evidence overlap, answer quality and weak
grounding need the finished answer and none of them fired in either run, so the full gate still runs at
completion and stays authoritative.

These tests pin both halves: the stream really does emit as it goes, and the gate that must not be optimised
away is still there at the end.
"""

from __future__ import annotations

import re
import time

from kenn.core import chat_answer
from kenn.core.chat_grounding import (
    _STREAM_GUARD_CONTEXT_CHARS,
    StreamedAnswerGuard,
    _measurements,
    claims_live_change,
)

QUERY = "What release time should I use for sidechain compression on bass?"

# The three body sections of the real "Sidechain Bass To Kick" note, which is where the 2 Oct measurements
# (150 ms, 4:1, 5 ms, 6 dB) live. A fixture without real numbers would let a guard that ignores measurements
# pass by luck.
CHUNKS = [
    (
        1030.88,
        {
            "id": "sidechain-try",
            "kind": "note",
            "title": "Sidechain Bass To Kick",
            "source": "sidechain-bass-to-kick.md",
            "page": 0,
            "section": "Try this",
            "text": (
                "Put a compressor on the bass bus and key it from the kick. "
                "Set the sidechain input to the kick track, release around 150 ms so the bass "
                "recovers before the next kick, and a ratio of 4:1 keeps the pumping shallow. "
                "An attack of 5 ms lets the bass transient through, and a depth of 6 dB is plenty."
            ),
        },
    ),
    (
        980.0,
        {
            "id": "sidechain-short",
            "kind": "note",
            "title": "Sidechain Bass To Kick",
            "source": "sidechain-bass-to-kick.md",
            "page": 0,
            "section": "Short answer",
            "text": (
                "Key the bass compressor from the kick so the bass ducks under every hit. "
                "Start the release at 150 ms and set the ratio to 4:1."
            ),
        },
    ),
    (
        900.0,
        {
            "id": "sidechain-mistakes",
            "kind": "note",
            "title": "Sidechain Bass To Kick",
            "source": "sidechain-bass-to-kick.md",
            "page": 0,
            "section": "Common mistakes",
            "text": (
                "Depth past 6 dB reads as a sidechain artefact rather than musical pumping, and an "
                "attack of 5 ms or longer smears the bass transient against the kick."
            ),
        },
    ),
]

TERMS = {"total_docs": 3, "avg_len": 60.0, "lengths": [60] * 3, "idf": {}, "postings": {}}

# Accepted by the full gate as-is: every number is in the evidence, the mode boundary and both checklists pass.
ACCEPTED_ANSWER = """Short answer: Release the bass compressor at 150 ms and key it from the kick.

Try this:
1. In Live, put a compressor on the bass bus and send the kick to its sidechain input.
2. Set the release to 150 ms so the bass recovers before the next kick.
3. Set the ratio to 4:1 and the depth to 6 dB so the pumping stays shallow.

Check:
A/B the bass bus against the kick: the ducking should read as musical pumping, not as a gap.

Sources:
- Sidechain Bass To Kick (sidechain-bass-to-kick.md)
"""

# Same shape and same quality score, but almost none of its vocabulary is in the note: evidence overlap 0.12,
# under the 0.16 floor. Nothing about it is knowable until the answer is complete, which is the whole reason
# the gate cannot be folded into the stream guard.
LOW_OVERLAP_ANSWER = """Short answer: 150 ms is the number to reach for on the ducking send.

Try this:
1. In Live, wire the microdynamics chain with a crest factor trim before the intermodulation stage.
2. Calibrate the psychoacoustic glue bus against the harmonic ladder of the reference render.
3. Reposition the transient shaper and the granular recombiner until the spatio-temporal image settles.
4. Audition the midband correlation against the subharmonic synthesiser on every pass.
5. Keep the transient smearing below audibility with the plate ambience tail.
6. Sweep the kensworth contour and the Nyquist knee with the oscilloscope trace.
7. Trim the convolution tail so the intermodulation sidebands stay in phase.
8. Nudge the shelf crossover and the exciter drive until the sibilance settles.

Check:
Compare the bandwidth tilt, the stereophonic coherence, the macrodynamic crest and the midrange
phase against the master bus, then re-audition the halo, the toe, the preamp sag and the flutter.

Sources:
- Sidechain Bass To Kick (sidechain-bass-to-kick.md)
"""


def _word_tokens(text: str) -> list[str]:
    """The model's cadence, with trailing spaces kept so the pieces rejoin exactly."""
    return re.findall(r"\S+\s*", text)


def _model_tokens(text: str) -> list[str]:
    """Word tokens, except that a number stays welded to its unit.

    This is how the Qwen tokenizers we run behave often enough to matter, and it is the case the guard can
    fully win: with the number and its unit in one piece, the token that completes the measurement is also the
    token that carries it, so nothing of "900 ms" has to reach the producer.
    """
    return re.findall(r"\d+\s*(?:hz|khz|db(?:fs|tp)?|ms|%|lufs?|bpm|bits?)\s*|\S+\s*", text, re.I)


def _stream(monkeypatch, fake_stream):
    """The answer stream with retrieval, the model and the on-disk writers faked."""
    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: True)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer_stream", fake_stream)
    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "load_terms", lambda: TERMS)
    monkeypatch.setattr(chat_answer, "search", lambda *a, **k: list(CHUNKS))
    # Traces, citation trust and session memory are written to the repo's data dir; a test must not.
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kw: kw.get("confidence", ""))
    monkeypatch.setattr(chat_answer, "_update_session", lambda *a, **k: None)
    return chat_answer._answer_payload_stream_raw(QUERY, allow_llm=True)


def _template(monkeypatch) -> str:
    """The grounded answer every fallback path substitutes, read without a model in the way."""
    monkeypatch.setattr(chat_answer, "llm_enhance_answer_stream", lambda *a, **k: iter(()))
    return "".join(
        event["token"]
        for event in chat_answer._answer_payload_stream_raw(QUERY, allow_llm=False)
        if event.get("event") == "token"
    )


def _text_and_metadata(events) -> tuple[str, dict]:
    text = "".join(event.get("token", "") for event in events if event.get("event") == "token")
    metadata = [event["data"] for event in events if event.get("event") == "metadata"][-1]
    return text, metadata


def _consume(monkeypatch, fake_stream, produced: list[str]) -> tuple[str, dict]:
    """Drain the stream, recording each token event the moment the consumer receives it.

    The fake model reads `produced` while the stream is suspended between two `next()` calls, which is the only
    way a test can see what was already on the wire at the moment a given token was written.
    """
    events = []
    for event in _stream(monkeypatch, fake_stream):
        events.append(event)
        if event.get("event") == "token":
            produced.append(event["token"])
    return _text_and_metadata(events)


def test_the_first_model_token_reaches_the_producer_before_the_model_finishes(monkeypatch) -> None:
    """The producer holds the model's first token as soon as the second one arrives, and no later.

    Exactly one token of lookahead, which is what keeps a measurement split across a boundary from going out
    half-checked. Two things are asserted at once: the producer saw token 1 while the model was still writing
    (so this is streaming, not buffering), and it had not seen it before the model wrote token 2 (so the
    lookahead has not quietly grown).
    """
    produced: list[str] = []
    producer_had_when_model_wrote: list[list[str]] = []
    head, rest = "Short answer: ", ACCEPTED_ANSWER[len("Short answer: "):]
    body, tail = rest[: len(rest) // 2], rest[len(rest) // 2:]

    def fake_stream(*args, **kwargs):
        yield {"event": "token", "token": head}
        producer_had_when_model_wrote.append(list(produced))
        yield {"event": "token", "token": body}
        producer_had_when_model_wrote.append(list(produced))
        yield {"event": "token", "token": tail}
        yield {"event": "llm_usage", "data": {"prompt_tokens": 10, "completion_tokens": 20}}

    text, metadata = _consume(monkeypatch, fake_stream, produced)

    assert producer_had_when_model_wrote == [[], [head]], (
        f"token 1 went out on the wrong token: {producer_had_when_model_wrote}"
    )
    assert produced[:2] == [head, body]
    # What the producer assembled is the answer the gate accepted, so nothing is re-sent at the end.
    assert text == ACCEPTED_ANSWER
    assert metadata["answer"] == ACCEPTED_ANSWER.strip()
    assert metadata["generation_validation"]["accepted"] is True


def test_an_unsupported_measurement_mid_stream_never_reaches_the_producer(monkeypatch) -> None:
    """The rejection that caused 8 of 9 failures on 2 Oct 2026 has to be caught before the number is sent.

    The evidence side of the diff is fixed before the first token and the answer side only grows, so nothing
    later can redeem "900 ms". The producer must not be left holding it, and everything the model wrote after
    it must stay inside the building.
    """
    template = _template(monkeypatch)
    leaked = "release around 900 ms so the bass recovers"
    candidate = ACCEPTED_ANSWER.replace("release to 150 ms so", leaked)

    def fake_stream(*args, **kwargs):
        for token in _model_tokens(candidate):
            yield {"event": "token", "token": token}
        yield {"event": "token", "token": "\nTry this: set the ratio to 4:1 and the depth to 6 dB.\n"}

    text, metadata = _text_and_metadata(list(_stream(monkeypatch, fake_stream)))
    validation = metadata["generation_validation"]

    assert "900" not in text, text
    assert "ratio to 4:1 and the depth" not in text, "the stream did not stop at the rejection"
    assert metadata["answer"] == template
    assert validation["accepted"] is False
    assert validation["unsupported_measurements"] == ["900ms"]
    assert any("unsupported measurements" in warning for warning in validation["warnings"]), validation
    # The stream stops on the word before the number, and the held word goes back with it, so the digits never
    # leave either.
    assert text.rstrip().endswith("Set the release"), text


def test_a_measurement_split_across_tokens_never_reaches_the_producer_before_it_is_guarded(monkeypatch) -> None:
    """"Set the release to " | "900" | " ms": the digits wait for the token that condemns them.

    The model splits numbers from their units often enough that "900 ms" can arrive as two tokens, and "900"
    on its own measures nothing. Emitting it the moment it is written puts the number on the wire before
    anything knows it is unsupported. This is the case the one-token lookahead exists for.
    """
    producer_had_when_model_wrote: list[str] = []
    produced: list[str] = []

    def fake_stream(*args, **kwargs):
        yield {"event": "token", "token": "Set the release to "}
        producer_had_when_model_wrote.append("".join(produced))
        yield {"event": "token", "token": "900"}
        yield {"event": "token", "token": " ms"}
        yield {"event": "token", "token": " so the bass recovers.\n"}

    template = _template(monkeypatch)
    text, metadata = _consume(monkeypatch, fake_stream, produced)
    validation = metadata["generation_validation"]

    assert producer_had_when_model_wrote == [""], (
        f"the digits were on the wire before the unit that condemns them arrived: {producer_had_when_model_wrote}"
    )
    assert "900" not in text, text
    # The held token is dropped rather than flushed: it is the half of the measurement nothing has cleared.
    assert text.rstrip().endswith("Set the release to"), text
    assert metadata["answer"] == template
    assert validation["unsupported_measurements"] == ["900ms"]


def test_a_stream_that_ends_on_its_first_token_still_emits_that_token(monkeypatch) -> None:
    """The lookahead holds a token for the next one, and a stream ending on `done` has no next one.

    Withholding the last token would cost the producer the end of every answer, which is worse than the hole
    the lookahead closes.
    """
    produced: list[str] = []

    def fake_stream(*args, **kwargs):
        yield {"event": "token", "token": "Short answer: Release the bass compressor at 150 ms and key it from the kick.\n"}
        yield {"event": "llm_usage", "data": {"prompt_tokens": 10, "completion_tokens": 12}}

    text, metadata = _consume(monkeypatch, fake_stream, produced)

    assert produced == ["Short answer: Release the bass compressor at 150 ms and key it from the kick.\n"], produced
    assert text == produced[0]
    assert metadata["generation_validation"]["attempted"] is True


def test_a_mid_stream_claim_that_the_live_set_changed_never_reaches_the_producer(monkeypatch) -> None:
    """The second prefix-sound rejection: the model must not tell the producer it already made the change."""
    template = _template(monkeypatch)
    candidate = "I set the release to 150 ms. " + ACCEPTED_ANSWER

    def fake_stream(*args, **kwargs):
        for token in _word_tokens(candidate):
            yield {"event": "token", "token": token}

    text, metadata = _text_and_metadata(list(_stream(monkeypatch, fake_stream)))
    validation = metadata["generation_validation"]

    assert "I set the release" not in text
    # The claim trips on the second token, so nothing of the first went out and the producer gets the whole
    # grounded template as tokens rather than a fragment of a sentence it has to discard.
    assert text == template, text
    assert claims_live_change(candidate) is True, "the fixture has to trip the regex or the test proves nothing"
    assert metadata["answer"] == template
    assert any("claims it changed the Live set" in warning for warning in validation["warnings"]), validation


def test_the_full_gate_still_rejects_at_completion_when_evidence_overlap_falls_late(monkeypatch) -> None:
    """Overlap divides by an answer-term count that grows with every token, so it cannot be checked early.

    This answer streams cleanly: no number outside the evidence, no claim about the Live set. The 0.16 overlap
    floor is only breached once the whole thing is in, and the metadata event is what has to carry the
    correction. Deleting the completion-time gate would let this answer through, which is why the gate is not
    on the streaming path.
    """
    assert "900" not in LOW_OVERLAP_ANSWER

    def fake_stream(*args, **kwargs):
        for token in _word_tokens(LOW_OVERLAP_ANSWER):
            yield {"event": "token", "token": token}

    text, metadata = _text_and_metadata(list(_stream(monkeypatch, fake_stream)))
    validation = metadata["generation_validation"]

    assert text == LOW_OVERLAP_ANSWER, "streaming succeeded, so the producer got the whole candidate"
    assert validation["accepted"] is False
    assert validation["evidence_overlap"] < 0.16, validation["evidence_overlap"]
    assert "generated answer has insufficient evidence overlap" in validation["warnings"], validation
    assert metadata["answer"] != LOW_OVERLAP_ANSWER, "the metadata answer is the correction the producer reads"
    assert metadata["llm_enhanced"] is False


def test_a_stream_that_dies_mid_answer_still_falls_back_and_records_cut_short(monkeypatch) -> None:
    """29 Sept's rule still holds: a truncated candidate is not handed to the validator as if finished."""
    template = _template(monkeypatch)

    def fake_stream(*args, **kwargs):
        yield {"event": "token", "token": "Short answer: Release the bass compressor at "}
        yield {"event": "token", "token": "150 ms and key it from the kick.\n"}
        raise RuntimeError("llama.cpp connection reset")

    text, metadata = _text_and_metadata(list(_stream(monkeypatch, fake_stream)))
    validation = metadata["generation_validation"]

    assert metadata["answer"] == template
    assert validation["accepted"] is False
    assert validation["warnings"][0].startswith("generation stream cut short: RuntimeError:"), validation
    # The fragment is what already went out, so the template is not appended on top of it. The second token is
    # still held when the stream dies, and a held token only goes out on a clean finish.
    assert text == "Short answer: Release the bass compressor at ", text


def test_a_range_split_across_two_tokens_is_still_caught() -> None:
    """A measurement the tokenizer split across tokens is one measurement to the gate.

    _RANGE_RE rewrites "200-400 Hz" to its endpoints before _MEASUREMENT_RE reads it, which only works if the
    guard sees both halves. The carry window is what makes that true.
    """
    guard = StreamedAnswerGuard({"150ms"})

    assert guard.check("High-pass the mud ") is None
    assert guard.check("from 200") is None
    tripped = guard.check("-400 Hz.") is not None

    assert tripped, "a range broken across two tokens slipped through the guard"
    assert tripped and _measurements("High-pass the mud from 200-400 Hz.") - {"150ms"} == {"200hz", "400hz"}


def test_the_guard_window_is_wide_enough_for_the_longest_match_it_has_to_catch() -> None:
    """The carry has to hold a whole match, or a rejection is lost in the seam between two tokens."""
    longest = "I have gone ahead and quantized the channel"
    assert claims_live_change(longest) is True
    assert len(longest) <= _STREAM_GUARD_CONTEXT_CHARS, (
        "a claim longer than the carry would be missed when it straddles a token boundary"
    )

    # Straddling it: the first token stops mid-claim, the second completes it.
    guard = StreamedAnswerGuard(set())
    assert guard.check("I have gone ahead and ") is None
    assert guard.check("quantized the channel") is not None


def test_the_guard_does_not_rescan_the_whole_answer_on_every_token() -> None:
    """Cost guard. Re-scanning the accumulated text per token is the obvious way to build this and the wrong one.

    The full gate's text work is 1.16 ms median over the 29 captured answers, so a per-token full rescan would
    cost that per token and around 87 ms across a 1051-character answer. The window is 48 characters of carry
    plus one token, so the real figure is microseconds; the bound below is 25 ms, which fails loudly if
    someone swaps the window for the whole prefix.
    """
    answer = (ACCEPTED_ANSWER + LOW_OVERLAP_ANSWER)[:1051]
    tokens = _word_tokens(answer)
    assert len(answer) >= 1000 and len(tokens) > 100, (len(answer), len(tokens))

    guard = StreamedAnswerGuard({"150ms", "6db", "5ms"})
    started = time.perf_counter()
    for token in tokens:
        guard.check(token)
    total_ms = (time.perf_counter() - started) * 1000.0

    assert total_ms < 25.0, f"{len(tokens)} tokens took {total_ms:.2f} ms, which is a per-token rescan"


class _NoOrchestrator:
    def dispatch(self, *args, **kwargs):
        return None


def test_a_clarify_routed_query_streams_a_payload_instead_of_crashing(monkeypatch) -> None:
    """A vague query used to kill the whole stream with UnboundLocalError.

    The clarify branch read answer_mode before the line that assigns it, so "make it
    better" raised at classification time -- after the server had already sent the SSE
    headers, leaving the producer with a stream that opened and then silently stopped.
    The branch has to answer instead of raising. 2 Oct 2026: five queries crashed this
    way before the fix ("make it better", "fix it", "what should I do", "can you help",
    "improve it").
    """
    monkeypatch.setattr(chat_answer, "get_orchestrator", lambda: _NoOrchestrator())

    events = list(chat_answer._answer_payload_stream_raw("make it better"))

    kinds = [event.get("event") for event in events]
    assert kinds[:2] == ["metadata", "token"], kinds
    answer = events[0]["data"].get("answer")
    assert isinstance(answer, str) and answer.strip(), (
        "the clarify payload has to carry an answer the producer can read"
    )