"""
`composition` package.

Keep this module import-light to avoid circular imports between composition ↔ ai.markov.
Consumers should prefer importing concrete modules (e.g. `composition.engine`) directly.
"""

from __future__ import annotations

from typing import Any

__all__ = ["CompositionGenerator", "SongGenerator", "SongRender", "SongSectionSpec"]


def __getattr__(name: str) -> Any:
    # Lazy re-exports for backwards compatibility.
    if name == "CompositionGenerator":
        from .engine import CompositionGenerator as _CG

        return _CG
    if name in {"SongGenerator", "SongRender", "SongSectionSpec"}:
        from .song_generator import SongGenerator, SongRender, SongSectionSpec

        return {"SongGenerator": SongGenerator, "SongRender": SongRender, "SongSectionSpec": SongSectionSpec}[name]
    raise AttributeError(name)
