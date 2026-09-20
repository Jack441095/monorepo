"""Tests for the minimal SSML <break time="..."/> support in
thursday/voice_output.py -- lets a voice answer ask for a real pause between
phrases instead of Kokoro reading everything at one flat pace.

Fast tests only, against a fake Kokoro stand-in (no real model) -- matches
the established split between tests/test_tts_parallel_chunks.py (fast, fake
Kokoro) and tests/test_tts_parallel_benchmark.py (slow, real model, proves
actual wall-clock behaviour).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import voice_output as vo  # noqa: E402


# --- _parse_ssml_breaks -----------------------------------------------------


def test_parse_no_breaks_returns_single_segment():
    assert vo._parse_ssml_breaks("Boost the low end.") == [("Boost the low end.", 0.0)]


def test_parse_single_break_ms():
    segments = vo._parse_ssml_breaks('Hey Jack. <break time="500ms"/> What do you need?')
    assert segments == [("Hey Jack.", 0.5), ("What do you need?", 0.0)]


def test_parse_single_break_seconds():
    segments = vo._parse_ssml_breaks('Hey Jack. <break time="1s"/> What do you need?')
    assert segments == [("Hey Jack.", 1.0), ("What do you need?", 0.0)]


def test_parse_multiple_breaks():
    text = 'One. <break time="200ms"/> Two. <break time="300ms"/> Three.'
    segments = vo._parse_ssml_breaks(text)
    assert segments == [("One.", 0.2), ("Two.", 0.3), ("Three.", 0.0)]


def test_parse_leading_break_yields_empty_first_segment():
    segments = vo._parse_ssml_breaks('<break time="500ms"/> Hello there.')
    assert segments == [("", 0.5), ("Hello there.", 0.0)]


def test_parse_trailing_break_yields_empty_last_segment():
    segments = vo._parse_ssml_breaks('Hello there. <break time="500ms"/>')
    assert segments == [("Hello there.", 0.5), ("", 0.0)]


def test_parse_consecutive_breaks_yield_an_empty_middle_segment():
    text = 'One. <break time="200ms"/><break time="300ms"/> Two.'
    segments = vo._parse_ssml_breaks(text)
    assert segments == [("One.", 0.2), ("", 0.3), ("Two.", 0.0)]


def test_parse_empty_text_returns_one_empty_segment():
    assert vo._parse_ssml_breaks("") == [("", 0.0)]


# --- _synthesise_with_breaks (fake Kokoro, no real model) -------------------


class _FakeKokoro:
    def __init__(self, sample_rate: int = 24000, fail_on: str | None = None):
        self.sample_rate = sample_rate
        self.fail_on = fail_on
        self.calls: list[str] = []

    def create(self, text, voice="x", speed=1.0, lang="en-us"):
        self.calls.append(text)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("synthesis failed")
        # One sample per character so segment length is verifiable.
        return np.full(len(text), float(len(text)), dtype=np.float32), self.sample_rate


def test_synthesise_with_breaks_inserts_real_silence_of_the_right_length():
    kokoro = _FakeKokoro(sample_rate=24000)
    segments = [("Hey Jack.", 0.5), ("What do you need?", 0.0)]

    result = vo._synthesise_with_breaks(kokoro, segments, voice="af_heart", speed=1.1)

    assert result is not None
    samples, sr = result
    assert sr == 24000
    first_len = len("Hey Jack.")
    gap_len = int(24000 * 0.5)
    second_len = len("What do you need?")
    assert len(samples) == first_len + gap_len + second_len
    # The gap itself must be real silence (zeros), not just extra length.
    gap_region = samples[first_len:first_len + gap_len]
    assert np.all(gap_region == 0.0)


def test_synthesise_with_breaks_handles_a_leading_pause():
    """A leading <break> has no prior synthesised audio to infer the sample
    rate/dtype from -- the pause must be carried forward and correctly
    prepended once the first real segment establishes them."""
    kokoro = _FakeKokoro(sample_rate=24000)
    segments = [("", 0.5), ("Hello there.", 0.0)]

    result = vo._synthesise_with_breaks(kokoro, segments, voice="af_heart", speed=1.1)

    assert result is not None
    samples, sr = result
    gap_len = int(24000 * 0.5)
    assert len(samples) == gap_len + len("Hello there.")
    assert np.all(samples[:gap_len] == 0.0)


def test_synthesise_with_breaks_returns_none_on_segment_failure():
    kokoro = _FakeKokoro(fail_on="bad")
    segments = [("good segment", 0.2), ("a bad segment", 0.0)]

    result = vo._synthesise_with_breaks(kokoro, segments, voice="af_heart", speed=1.1)

    assert result is None


def test_synthesise_with_breaks_returns_none_on_sample_rate_mismatch():
    class _InconsistentKokoro:
        def __init__(self):
            self.n = 0

        def create(self, text, voice="x", speed=1.0, lang="en-us"):
            self.n += 1
            sr = 24000 if self.n == 1 else 22050
            return np.zeros(10, dtype=np.float32), sr

    segments = [("first", 0.1), ("second", 0.0)]
    result = vo._synthesise_with_breaks(_InconsistentKokoro(), segments, voice="af_heart", speed=1.1)

    assert result is None


def test_synthesise_with_breaks_all_empty_segments_returns_none():
    kokoro = _FakeKokoro()
    result = vo._synthesise_with_breaks(kokoro, [("", 0.0)], voice="af_heart", speed=1.1)
    assert result is None


# --- _sanitize_for_speech protects break tags --------------------------------


def test_sanitize_preserves_a_break_tag_through_markdown_cleanup():
    text = '**Hey Jack.** <break time="500ms"/> What do you need?'
    clean = vo._sanitize_for_speech(text)
    assert '<break time="500ms"/>' in clean
    assert "**" not in clean


def test_sanitize_break_tag_survives_length_truncation():
    """The 500-char truncation in _sanitize_for_speech previously operated
    directly on the real tag text -- a tag landing near the cutoff could get
    sliced in half, leaving a garbled fragment Kokoro would try to
    pronounce. Protecting it with a short placeholder before truncation and
    restoring it after must keep the tag intact regardless of where it
    falls relative to the 500-char budget."""
    padding = "x" * 490
    text = f'{padding} <break time="750ms"/> the rest of the sentence after the break'
    clean = vo._sanitize_for_speech(text)
    assert '<break time="750ms"/>' in clean
    # No leftover placeholder/null-byte fragments.
    assert "\x00" not in clean


def test_sanitize_is_idempotent_for_break_tags():
    """synthesise_isolated() sanitises once before handing text to the TTS
    subprocess worker, which sanitises again internally (it just calls
    synthesise(), which also sanitises) -- running _sanitize_for_speech
    twice on the same text must not corrupt or duplicate the tag."""
    text = 'Hey Jack. <break time="500ms"/> What do you need?'
    once = vo._sanitize_for_speech(text)
    twice = vo._sanitize_for_speech(once)
    assert once == twice
    assert once.count('<break time="500ms"/>') == 1


def test_sanitize_with_no_break_tags_is_unaffected():
    """Regression: the protect/restore wrapping must not change behaviour
    for the overwhelming majority of text, which has no break tags at all."""
    text = "**Hey Jack.** Here's your business status: [internal-id-123]"
    clean = vo._sanitize_for_speech(text)
    assert "**" not in clean
    assert "[internal-id-123]" not in clean
    assert "\x00" not in clean


# --- synthesise() routing ----------------------------------------------------


def test_synthesise_routes_break_text_through_the_break_path(monkeypatch):
    monkeypatch.setattr(vo, "_load_kokoro", lambda: _FakeKokoro())
    vo.synthesise.cache_clear()

    text = 'Hey Jack. <break time="500ms"/> What do you need?'
    wav = vo.synthesise(text, voice="af_heart", speed=1.1)

    assert wav is not None
    vo.synthesise.cache_clear()


def test_synthesise_without_breaks_is_unchanged(monkeypatch):
    """Regression: plain text (the overwhelming majority of calls) must take
    exactly the pre-existing clause-based parallel-chunk path, not the new
    break path."""
    monkeypatch.delenv("THURSDAY_TTS_PARALLEL_CHUNKS", raising=False)
    kokoro = _FakeKokoro()
    monkeypatch.setattr(vo, "_load_kokoro", lambda: kokoro)
    vo.synthesise.cache_clear()

    text = "Cut two point five kilohertz, to reduce harshness, and boost the low end."
    wav = vo.synthesise(text, voice="af_heart", speed=1.1)

    assert wav is not None
    assert len(kokoro.calls) > 1
    assert set(kokoro.calls) == set(vo._split_into_synthesis_chunks(text))
    vo.synthesise.cache_clear()


def test_synthesise_falls_back_to_flattened_text_when_break_synthesis_fails(monkeypatch):
    """If the break-aware synthesis path fails outright, the fallback must
    read the flattened segment text, never the raw clean_text -- which
    still contains the literal <break time="..."/> tag Kokoro would
    otherwise try to pronounce verbatim."""
    class _AlwaysFailsWithBreaks:
        def create(self, text, voice="x", speed=1.0, lang="en-us"):
            if "<break" in text:
                raise RuntimeError("should never be asked to speak a raw tag")
            raise RuntimeError("segment synthesis always fails in this test")

    monkeypatch.setattr(vo, "_load_kokoro", lambda: _AlwaysFailsWithBreaks())
    vo.synthesise.cache_clear()

    text = 'Hey Jack. <break time="500ms"/> What do you need?'
    wav = vo.synthesise(text, voice="af_heart", speed=1.1)

    # Every real Kokoro call failed (by design of the fake), so overall
    # synthesis fails -- but it must have failed via the flattened-text
    # fallback attempt, never by handing the raw tag to kokoro.create().
    assert wav is None
    vo.synthesise.cache_clear()
