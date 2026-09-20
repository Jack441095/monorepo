# ai/__init__.py
# Package marker for `ai`.

##Lazy exports for the ai package.
######### Avoid importing the full Markov stack at package import time so narrower
## subpackages remain importable in lighter environments.


from importlib import import_module

__all__ = [
    "DURATIONS",
    "BaseMarkov",
    "IntervalMarkov",
    "RhythmMarkov",
    "PhraseMarkov",
    "ChordMarkov",
    "GlobalChordMarkov",
    "MotifLibrary",
    "MelodyGenerator",
    "get_interval_bias",
]

_EXPORT_MAP = {
    "BaseMarkov": ("ai.markov.core.base", "BaseMarkov"),
    "DURATIONS": ("ai.markov.core.constants", "DURATIONS"),
    "get_interval_bias": ("ai.markov.melody.biasing", "get_interval_bias"),
    "MelodyGenerator": ("ai.markov.melody.generator", "MelodyGenerator"),
    "ChordMarkov": ("ai.markov.chord.models", "ChordMarkov"),
    "GlobalChordMarkov": ("ai.markov.chord.models", "GlobalChordMarkov"),
    "IntervalMarkov": ("ai.markov.core.models", "IntervalMarkov"),
    "PhraseMarkov": ("ai.markov.core.models", "PhraseMarkov"),
    "RhythmMarkov": ("ai.markov.core.models", "RhythmMarkov"),
    "MotifLibrary": ("ai.markov.motif", "MotifLibrary"),
}


def __getattr__(name):
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORT_MAP[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
