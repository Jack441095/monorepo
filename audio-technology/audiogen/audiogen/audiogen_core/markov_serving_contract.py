# core/markov_serving_contract.py
"""
Training ↔ runtime contract for Markov pickles loaded by `CompositionGenerator`.
Unpickle and bundle validation live in `composition.retrained_markov_loader`.

Tokenizer / n-gram hyperparameters (`order`, `smoothing`, `backoff_decay`) live on the
loaded model objects (`BaseMarkov` subclasses). There is no separate tokenizer-version
string in this repo: vocabulary is implicit in the trained transition tables. After
unpickling, read hyperparameters from the instance (serialized via `BaseMarkov.__getstate__`
in training scripts).

Bundle layouts are produced by training utilities such as:
  - `scripts/chord_jsonl_retrain.py` → chord bundle
  - `scripts/melody_jsonl_retrain.py` → melody bundle / bare `MarkovModelSet`
"""

from __future__ import annotations

# Optional monotonic int: runtime rejects unknown future formats. Legacy: key ``version``;
# new bundles should set ``bundle_format_version`` (and may keep ``version``).
MARKOV_BUNDLE_FORMAT_VERSION_KEY = "bundle_format_version"
CHORD_MARKOV_BUNDLE_FORMAT_VERSION_MAX = 1
MELODY_MARKOV_BUNDLE_FORMAT_VERSION_MAX = 1

# --- Chord Markov bundle (dict pickle) -----------------------------------------
CHORD_MARKOV_BUNDLE_KIND = "chord_markov_bundle"
# Expected keys on bundle dict: "degree", "bucket", optional "global_degree", "global_bucket"
# Each value must satisfy `composition.protocols.ChordProgressionMarkov` (train + get_probabilities).

# CONFIG.composition attributes that point to the chord pickle path / hot-reload:
CONFIG_CHORD_RETRAINED_MARKOV_ENABLED = "chord_retrained_markov_enabled"
CONFIG_CHORD_RETRAINED_MARKOV_PATH = "chord_retrained_markov_path"
CONFIG_CHORD_RETRAINED_HOT_RELOAD_ENABLED = "chord_retrained_markov_hot_reload_enabled"
CONFIG_CHORD_RETRAINED_HOT_RELOAD_INTERVAL_S = "chord_retrained_markov_hot_reload_interval_seconds"

# --- Melody Markov pickle -------------------------------------------------------
MELODY_MARKOV_BUNDLE_KIND = "melody_markov_bundle"
# Bundle dict keys: "kind", "global" (`MarkovModelSet`), optional "emotion_models", "family_models",
# optional "bundle_format_version" (int, <= MELODY_MARKOV_BUNDLE_FORMAT_VERSION_MAX). Bare
# `MarkovModelSet` pickle is also accepted.

CONFIG_MELODY_RETRAINED_MARKOV_ENABLED = "melody_retrained_markov_enabled"
CONFIG_MELODY_RETRAINED_MARKOV_PATH = "melody_retrained_markov_path"
CONFIG_MELODY_RETRAINED_HOT_RELOAD_ENABLED = "melody_retrained_markov_hot_reload_enabled"
CONFIG_MELODY_RETRAINED_HOT_RELOAD_INTERVAL_S = "melody_retrained_markov_hot_reload_interval_seconds"
