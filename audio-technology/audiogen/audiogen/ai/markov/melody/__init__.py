# ai/markov/melody/__init__.py
# Package marker for `ai`.

# ai/markov/melody/__init__.py
"""
Melody generation module with modular components.
"""

from .biasing import (EMOTION_INTERVAL_BIAS, EMOTION_RHYTHM_BIAS,
                      get_interval_bias)
from .embellishments import apply_embellishments
from .generator import MelodyGenerator
from .ensemble import MarkovModelSet
from .motif_manager import MotifManager
from .motif_variations import (augment_motif, diminish_motif, fragment_motif,
                               invert_motif, retrograde_motif, sequence_motif)
from .note_generator import NoteGenerator
from .phrase_planner import PhrasePlan, PhrasePlanner
from .phrase_repetition import PhraseRepetitionMixin
from .post_processor import PostProcessor
from .tension_model import TensionModelMixin
from .utils import (chord_symbol_to_scale_degrees,
                    chord_symbol_to_scale_degrees_weighted)
from .voice_leading import VoiceLeadingMixin

__all__ = [
    # Main generator
    'MelodyGenerator',
    # Core components
    'NoteGenerator',
    'MotifManager',
    'PhrasePlanner',
    'PhrasePlan',
    'PostProcessor',
    'MarkovModelSet',
    # Biasing and utilities
    'get_interval_bias',
    'EMOTION_INTERVAL_BIAS',
    'EMOTION_RHYTHM_BIAS',
    'apply_embellishments',
    'augment_motif',
    'diminish_motif',
    'invert_motif',
    'retrograde_motif',
    'fragment_motif',
    'sequence_motif',
    'chord_symbol_to_scale_degrees',
    'chord_symbol_to_scale_degrees_weighted',
    # Mixins (if needed externally)
    'PhraseRepetitionMixin',
    'TensionModelMixin',
    'VoiceLeadingMixin',
]