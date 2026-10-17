# tests/test_retrained_markov_loader_compat.py
from __future__ import annotations

import pickle
import tempfile
from pathlib import Path

from composition.retrained_markov_loader import (
    load_chord_retrained_pickle,
    load_melody_retrained_pickle,
    markov_chain_hyperparams_sane,
)
from audiogen_core.markov_serving_contract import (
    CHORD_MARKOV_BUNDLE_KIND,
    MARKOV_BUNDLE_FORMAT_VERSION_KEY,
    MELODY_MARKOV_BUNDLE_KIND,
)


def test_markov_chain_hyperparams_sane_accepts_chord_markov() -> None:
    from ai.markov import ChordMarkov

    m = ChordMarkov(order=3, smoothing=0.01, backoff_decay=0.7)
    assert markov_chain_hyperparams_sane(m) is True


def test_bare_melody_pickle_rejected_when_interval_order_invalid() -> None:
    from ai.markov.melody.ensemble import MarkovModelSet

    m = MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1, smoothing=0.02)
    m.interval.order = 0  # type: ignore[assignment]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.pkl"
        with p.open("wb") as f:
            pickle.dump(m, f, protocol=pickle.HIGHEST_PROTOCOL)
        assert load_melody_retrained_pickle(p, hot_reload=False) is None


def test_melody_bundle_rejected_when_format_version_too_high() -> None:
    from ai.markov.melody.ensemble import MarkovModelSet

    g = MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1, smoothing=0.02)
    bundle = {
        "kind": MELODY_MARKOV_BUNDLE_KIND,
        "global": g,
        MARKOV_BUNDLE_FORMAT_VERSION_KEY: 99,
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "b.pkl"
        with p.open("wb") as f:
            pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
        assert load_melody_retrained_pickle(p, hot_reload=False) is None


def test_chord_bundle_rejected_when_format_version_invalid() -> None:
    from ai.markov import ChordMarkov

    bundle = {
        "kind": CHORD_MARKOV_BUNDLE_KIND,
        "degree": ChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7),
        "bucket": ChordMarkov(order=2, smoothing=0.01, backoff_decay=0.7),
        MARKOV_BUNDLE_FORMAT_VERSION_KEY: -1,
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c.pkl"
        with p.open("wb") as f:
            pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
        assert load_chord_retrained_pickle(p, hot_reload=False) is None


def test_melody_bundle_legacy_version_key_still_loads() -> None:
    """Training scripts wrote ``version`` before ``bundle_format_version`` existed."""
    from ai.markov.melody.ensemble import MarkovModelSet

    g = MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1, smoothing=0.02)
    bundle = {"kind": MELODY_MARKOV_BUNDLE_KIND, "version": 1, "global": g}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "b.pkl"
        with p.open("wb") as f:
            pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
        out = load_melody_retrained_pickle(p, hot_reload=False)
        assert out is not None


def test_melody_bundle_format_v1_still_loads() -> None:
    from ai.markov.melody.ensemble import MarkovModelSet

    g = MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1, smoothing=0.02)
    bundle = {
        "kind": MELODY_MARKOV_BUNDLE_KIND,
        "global": g,
        MARKOV_BUNDLE_FORMAT_VERSION_KEY: 1,
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "b.pkl"
        with p.open("wb") as f:
            pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
        out = load_melody_retrained_pickle(p, hot_reload=False)
        assert out is not None
        loaded = out[0]
        assert int(loaded.interval.order) == int(g.interval.order)
