"""Tests for streaming TTS: sentence splitting + the speak_streaming pipeline.

The point of streaming TTS is to speak each sentence the moment it finishes
generating, instead of waiting 6-8 s for the whole answer. These verify the
sentence boundary logic and that sentences are spoken in order as chunks arrive.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import voice_output as vo  # noqa: E402


def test_split_emits_complete_sentences():
    sents, rem = vo._split_speakable("First sentence. Second one! A third?")
    assert sents == ["First sentence.", "Second one!", "A third?"]
    assert rem == ""


def test_split_keeps_partial_in_remainder():
    sents, rem = vo._split_speakable("Complete one. Partial without")
    assert sents == ["Complete one."]
    assert rem.strip() == "Partial without"


def test_split_does_not_break_decimals():
    sents, _ = vo._split_speakable("Cut at 3.5 kHz then boost 10.2 dB. Done.")
    assert sents == ["Cut at 3.5 kHz then boost 10.2 dB.", "Done."]


def test_split_on_newlines():
    sents, rem = vo._split_speakable("Step one\nStep two\n")
    assert sents == ["Step one", "Step two"]
    assert rem == ""


def test_speak_streaming_speaks_sentences_in_order():
    spoken: list[str] = []

    def sink(text, block=True):
        spoken.append(text)
        return True

    # Dribbled token stream forming two sentences.
    chunks = ["Make ", "the kick ", "punch harder. ", "Then side", "chain the bass."]
    full = vo.speak_streaming(iter(chunks), speak_fn=sink)

    assert full == "Make the kick punch harder. Then sidechain the bass."
    assert len(spoken) == 2
    assert "kick punch harder" in spoken[0]
    assert "sidechain the bass" in spoken[1]


def test_speak_streaming_flushes_unterminated_tail():
    spoken: list[str] = []

    def sink(text, block=True):
        spoken.append(text)
        return True

    vo.speak_streaming(iter(["No terminal punctuation here"]), speak_fn=sink)
    assert len(spoken) == 1
    assert "No terminal punctuation" in spoken[0]


def test_stream_kenn_answer_extracts_token_text():
    """The KENN stream yields {'event': 'token', 'token': ...} plus metadata/session
    events; the voice source must extract only the token text, in order."""
    from thursday import voice as tv

    events = [
        {"event": "metadata", "data": {}},
        {"event": "token", "token": "Make the "},
        {"event": "token", "token": ""},        # empty token ignored
        {"event": "token", "token": "kick punch."},
        {"event": "session", "data": {}},
    ]

    def fake_stream(query, *, limit=6, session_id=None):
        return iter(events)

    out = list(tv.stream_kenn_answer("how do I make my kick punch", _stream_fn=fake_stream))
    assert out == ["Make the ", "kick punch."]


def test_voice_command_uses_typed_failure_without_leaking_exception() -> None:
    from thursday import voice as tv

    def fail(_text, _session):
        raise RuntimeError("private stack detail")

    answer = tv.execute_voice_command("break", {"session_id": "voice-1"}, fail)
    assert answer == "Thursday could not complete the request."
    assert "private stack detail" not in answer


def test_streaming_source_feeds_speaker_end_to_end():
    """stream_kenn_answer → speak_streaming should speak the KENN answer's sentences."""
    from thursday import voice as tv
    from thursday import voice_output as vo

    events = [
        {"event": "token", "token": "Boost 3.5 kHz gently. "},
        {"event": "token", "token": "Then check mono."},
    ]
    spoken: list[str] = []

    vo.speak_streaming(
        tv.stream_kenn_answer("q", _stream_fn=lambda *a, **k: iter(events)),
        speak_fn=lambda text, block=True: spoken.append(text) or True,
    )
    assert len(spoken) == 2
    assert "3.5 kHz" in spoken[0]  # decimal not split
    assert "check mono" in spoken[1]


def test_pipelined_worker_synthesises_next_sentence_during_playback(monkeypatch):
    """The real fix for the reported "gap after each sentence" latency: with
    no speak_fn injected (the production path), synthesis of sentence N+1
    must start while sentence N is still playing, not after — otherwise every
    sentence boundary is a dead-air gap the length of one TTS synthesis call.
    """
    import threading

    from thursday import voice_output as vo

    synth_calls: list[str] = []
    play_calls: list[str] = []
    playback_started = threading.Event()
    release_playback = threading.Event()
    synth_started_during_playback = threading.Event()

    def fake_synthesise_isolated(text, voice=None, speed=None):
        synth_calls.append(text)
        if text.startswith("Second"):
            # Runs on the prefetch thread; wait for sentence 1's playback to
            # actually begin (deterministic ordering, no race with the flag
            # below) then confirm it hasn't finished yet.
            playback_started.wait(timeout=5)
            if not release_playback.is_set():
                synth_started_during_playback.set()
        return b"RIFFfakewavdata"

    def fake_play_wav_bytes(wav, *, timeout_hint_chars=0):
        play_calls.append(wav)
        if len(play_calls) == 1:
            playback_started.set()
            release_playback.wait(timeout=5)
        return True

    monkeypatch.setattr(vo, "synthesise_isolated", fake_synthesise_isolated)
    monkeypatch.setattr(vo, "_play_wav_bytes", fake_play_wav_bytes)

    def stream():
        yield "First sentence. "
        yield "Second sentence."

    result: dict = {}

    def run():
        result["full"] = vo.speak_streaming(stream())  # no speak_fn -> pipelined path

    thread = threading.Thread(target=run)
    thread.start()

    assert playback_started.wait(timeout=5)
    assert synth_started_during_playback.wait(timeout=5), (
        "sentence 2 synthesis did not start until sentence 1 finished playing "
        "-- the pipeline is not overlapping synthesis with playback"
    )
    release_playback.set()
    thread.join(timeout=5)

    assert result["full"] == "First sentence. Second sentence."
    assert len(synth_calls) == 2
    assert len(play_calls) == 2


def test_playback_does_not_block_generation():
    """The real win: while sentence 1 is playing, the generator keeps producing —
    so speech overlaps generation instead of waiting for the whole answer."""
    import threading

    playback_started = threading.Event()
    release_playback = threading.Event()
    gen_exhausted = threading.Event()
    spoken: list[str] = []

    def sink(text, block=True):
        spoken.append(text)
        if len(spoken) == 1:
            playback_started.set()
            release_playback.wait(timeout=5)  # hold playback of sentence 1
        return True

    def stream():
        yield "One. "
        yield "Two. "
        yield "Three."
        gen_exhausted.set()

    result: dict = {}

    def run():
        result["full"] = vo.speak_streaming(stream(), speak_fn=sink)

    thread = threading.Thread(target=run)
    thread.start()

    assert playback_started.wait(timeout=5)  # first sentence reached the sink
    # With playback of sentence 1 held, the producer must still drain the whole
    # generator (queue 2 and 3) — proving playback never blocks generation.
    assert gen_exhausted.wait(timeout=5)
    release_playback.set()
    thread.join(timeout=5)
    assert result["full"] == "One. Two. Three."
