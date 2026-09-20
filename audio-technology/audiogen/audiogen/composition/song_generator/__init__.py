# composition/song_generator/__init__.py
# Public entry point for `composition.song_generator`. Re-exports
# `SongGenerator`, `SongRender`, and `SongSectionSpec` — the exact surface
# every external caller imports (`from composition.song_generator import ...`),
# preserved from the pre-split module.
#
# `SongGenerator` itself is assembled from mixins living alongside this file:
#   - generation.py    -> GenerationMixin  (__init__, generate_song, best-of-k)
#   - scoring.py        -> ScoringMixin     (best-of-k candidate scoring)
#   - forms.py           -> FormsMixin       (default_form / pop_form / ... builders)
#   - form_helpers.py   -> FormHelpersMixin (emotion-arc / root-motion-arc / density targets)
#   - export.py          -> ExportMixin      (JSON report + MIDI export)
# This mirrors the existing `CompositionGenerator(PerformanceMixin, CachingMixin)`
# pattern in `composition/engine.py` / `composition/mixins/`.

from __future__ import annotations

from .export import ExportMixin
from .form_helpers import FormHelpersMixin
from .forms import FormsMixin
from .generation import GenerationMixin
from .models import SongRender, SongSectionSpec
from .scoring import ScoringMixin

__all__ = ["SongGenerator", "SongRender", "SongSectionSpec"]


class SongGenerator(
    GenerationMixin,
    ScoringMixin,
    FormsMixin,
    FormHelpersMixin,
    ExportMixin,
):
    """
    Offline song generator that stitches multiple arranged sections into a single
    global event timeline, and can export a MIDI file for audition/editing.
    """
