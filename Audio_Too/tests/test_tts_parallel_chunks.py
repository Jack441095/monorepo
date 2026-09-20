"""Tests for opt-in parallel-chunk TTS synthesis (docs/audits/2026-07-19-tts-latency-optimization.md).

Fast tests here cover the pure chunk-splitting logic and the concatenation
path against a fake Kokoro stand-in (no real model, no real speedup claim).
The one test that proves the actual wall-clock win is
tests/test_tts_parallel_benchmark.py, marked slow -- it needs the real
Kokoro model loaded, same reasoning as tests/test_release_health_latency.py.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import voice_output as vo  # noqa: E402


# --- _split_into_synthesis_chunks -------------------------------------------


def test_split_short_text_stays_single_chunk():
    assert vo._split_into_synthesis_chunks("Boost the low end.") == ["Boost the low end."]


def test_split_falls_back_to_word_midpoint_when_no_punctuation():
    # No comma/semicolon/colon to split at -- this is exactly the shape of
    # the real TTS_TEST_SENTENCES SLO case that motivated the fallback
    # (scripts/eval/release_health_check.py's "Cut two point five kilohertz
    # to reduce harshness." has no clause punctuation at all).
    chunks = vo._split_into_synthesis_chunks("The kick and bass are masking each other")
    assert len(chunks) == 2
    assert " ".join(chunks) == "The kick and bass are masking each other"


def test_split_word_midpoint_lands_near_the_middle():
    chunks = vo._split_at_word_midpoint("Cut two point five kilohertz to reduce harshness.")
    assert chunks == ["Cut two point five kilohertz", "to reduce harshness."]
    for c in chunks:
        assert len(c) >= vo._MIN_CHUNK_CHARS


def test_split_at_clause_boundaries_when_both_sides_are_long_enough():
    chunks = vo._split_into_synthesis_chunks("Cut two point five kilohertz, to reduce harshness.")
    assert chunks == ["Cut two point five kilohertz", "to reduce harshness."]


def test_split_falls_back_to_single_chunk_when_a_piece_is_too_short():
    # "ok," is well under _MIN_CHUNK_CHARS -- splitting here would spawn a
    # thread to synthesise two words, not worth the overhead.
    text = "ok, cut two point five kilohertz to reduce harshness"
    chunks = vo._split_into_synthesis_chunks(text)
    assert chunks == [text]


def test_split_caps_chunk_count_and_merges_the_tail():
    text = (
        "boost the low end around eighty hertz, cut the harsh two kilohertz range, "
        "widen the stereo image slightly, tighten the low end below fifty hertz, "
        "and add a touch of plate reverb to the vocal"
    )
    chunks = vo._split_into_synthesis_chunks(text)
    assert len(chunks) <= vo._MAX_CHUNKS
    assert len(chunks) > 1
    # Nothing from the original text is dropped (ignoring the comma/space
    # normalisation splitting/rejoining performs).
    assert "".join(chunks).replace(" ", "") == "".join(
        p.strip() for p in text.split(",")
    ).replace(" ", "")


def test_split_empty_text_returns_no_chunks():
    assert vo._split_into_synthesis_chunks("") == []
    assert vo._split_into_synthesis_chunks("   ") == []


# --- _synthesise_chunks_parallel (fake Kokoro, no real model) ---------------


class _FakeKokoro:
    """Returns a distinctive constant-value array per chunk so concatenation
    order is verifiable, with an artificial per-call delay to prove calls
    actually overlap rather than serialise."""

    def __init__(self, delay_s: float = 0.05):
        self.delay_s = delay_s
        self.calls: list[str] = []

    def create(self, text, voice="x", speed=1.0, lang="en-us"):
        self.calls.append(text)
        time.sleep(self.delay_s)
        # Encode which chunk this is directly into the sample values so the
        # test can verify ordering without depending on call order.
        value = float(len(text))
        return np.full(100, value, dtype=np.float32), 24000


def test_synthesise_chunks_parallel_preserves_order():
    kokoro = _FakeKokoro(delay_s=0.02)
    chunks = ["short one", "a slightly longer second chunk"]
    result = vo._synthesise_chunks_parallel(kokoro, chunks, voice="af_heart", speed=1.1)
    assert result is not None
    samples, sr = result
    assert sr == 24000
    assert np.all(np.isfinite(samples))
    # First 100 samples correspond to chunk 0's distinctive value, the last
    # 100 to chunk 1's -- proves concatenation kept the original order even
    # though both chunks were dispatched concurrently.
    assert samples[0] == float(len(chunks[0]))
    assert samples[-1] == float(len(chunks[1]))


def test_synthesise_chunks_parallel_actually_overlaps():
    delay = 0.15
    kokoro = _FakeKokoro(delay_s=delay)
    chunks = ["first chunk of text", "second chunk of text", "third chunk of text"]
    t0 = time.time()
    result = vo._synthesise_chunks_parallel(kokoro, chunks, voice="af_heart", speed=1.1)
    elapsed = time.time() - t0
    assert result is not None
    # If calls serialised, this would take >= 3 * delay. Overlapping calls
    # should land close to one delay plus scheduling overhead.
    assert elapsed < 2 * delay, f"chunks did not overlap: {elapsed:.3f}s for {len(chunks)} x {delay}s"


def test_synthesise_chunks_parallel_returns_none_on_any_failure():
    class _FlakyKokoro:
        def create(self, text, voice="x", speed=1.0, lang="en-us"):
            if "bad" in text:
                raise RuntimeError("synthesis failed")
            return np.zeros(10, dtype=np.float32), 24000

    result = vo._synthesise_chunks_parallel(
        _FlakyKokoro(), ["good chunk", "bad chunk"], voice="af_heart", speed=1.1
    )
    assert result is None


# --- default-on gating (promoted 2026-07-20; THURSDAY_TTS_PARALLEL_CHUNKS=0 is
# the rollback switch) ---------------------------------------------------------


def test_parallel_chunks_enabled_by_default(monkeypatch):
    monkeypatch.delenv("THURSDAY_TTS_PARALLEL_CHUNKS", raising=False)
    assert vo._parallel_chunks_enabled() is True


def test_parallel_chunks_can_be_explicitly_disabled_via_env_var(monkeypatch):
    monkeypatch.setenv("THURSDAY_TTS_PARALLEL_CHUNKS", "0")
    assert vo._parallel_chunks_enabled() is False
    monkeypatch.setenv("THURSDAY_TTS_PARALLEL_CHUNKS", "1")
    assert vo._parallel_chunks_enabled() is True


def test_synthesise_chunks_by_default(monkeypatch):
    """With the flag unset (the new default), synthesise() must split
    clause-heavy text and call kokoro.create() once per chunk, not once on
    the full text."""
    monkeypatch.delenv("THURSDAY_TTS_PARALLEL_CHUNKS", raising=False)
    vo.synthesise.cache_clear()

    kokoro = _FakeKokoro(delay_s=0.0)
    monkeypatch.setattr(vo, "_load_kokoro", lambda: kokoro)

    text = "Cut two point five kilohertz, to reduce harshness, and boost the low end."
    wav = vo.synthesise(text, voice="af_heart", speed=1.1)
    assert wav is not None
    assert len(kokoro.calls) > 1
    assert set(kokoro.calls) == set(vo._split_into_synthesis_chunks(text))
    vo.synthesise.cache_clear()


def test_synthesise_falls_back_to_single_call_when_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("THURSDAY_TTS_PARALLEL_CHUNKS", "0")
    vo.synthesise.cache_clear()

    kokoro = _FakeKokoro(delay_s=0.0)
    monkeypatch.setattr(vo, "_load_kokoro", lambda: kokoro)

    text = "Cut two point five kilohertz, to reduce harshness, and boost the low end."
    wav = vo.synthesise(text, voice="af_heart", speed=1.1)
    assert wav is not None
    assert kokoro.calls == [text]
    vo.synthesise.cache_clear()
