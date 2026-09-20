"""Podcast / spoken-word audio analysis and engineering (specialization).

Advice-only analysis tuned to dialogue and podcast delivery standards. Applies
no DSP; every threshold is a documented heuristic to be calibrated against a
real spoken-word corpus.
"""

from __future__ import annotations

from audio_analysis.podcast.podcast_analysis import (
    PODCAST_TARGETS,
    analyze_podcast,
)
from audio_analysis.podcast.podcast_report import render_podcast_report_html

__all__ = ["analyze_podcast", "PODCAST_TARGETS", "render_podcast_report_html"]
