# tests/test_composition_generator_markov_injection.py
"""Phase 2: inject Markov backends into CompositionGenerator (fast tests, alternate chains)."""
from __future__ import annotations

from ai.markov import ChordMarkov, GlobalChordMarkov
from ai.markov.melody.ensemble.model_set import MarkovModelSet

from composition.engine import CompositionGenerator


def test_injected_chord_and_melody_markov_identities_preserved() -> None:
    cm = ChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7)
    cb = ChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7)
    gm = GlobalChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7)
    gb = GlobalChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7)
    mset = MarkovModelSet(interval_order=4, rhythm_order=3, phrase_order=2, smoothing=0.01)

    gen = CompositionGenerator(
        enable_perf_monitoring=False,
        chord_markov=cm,
        chord_markov_bucket=cb,
        global_chord_markov=gm,
        global_chord_markov_bucket=gb,
        melody_markov_model=mset,
        skip_markov_retrain_load=True,
    )
    assert gen.chord_markov is cm
    assert gen.chord_markov_bucket is cb
    assert gen.global_chord_markov is gm
    assert gen.global_chord_markov_bucket is gb
    assert gen.melody_gen.markov is mset


def test_skip_retrain_and_injection_construct_without_pool_smoke() -> None:
    """Injected chord surface skips pool training by default (no emotion-pool overwrite)."""
    cm = ChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7)
    cb = ChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7)
    gen = CompositionGenerator(
        enable_perf_monitoring=False,
        chord_markov=cm,
        chord_markov_bucket=cb,
        skip_markov_retrain_load=True,
    )
    assert gen.chord_markov is cm
    assert gen._retrained_chord_markov_loaded_ok is False


def test_explicit_skip_chord_pool_training_false_still_trains_when_not_injected() -> None:
    gen = CompositionGenerator(
        enable_perf_monitoring=False,
        skip_markov_retrain_load=True,
        skip_chord_markov_pool_training=False,
    )
    assert gen.chord_markov is not None
