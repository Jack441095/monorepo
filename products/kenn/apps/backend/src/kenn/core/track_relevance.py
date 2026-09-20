"""Track-name relevance filtering for session-state display (item 1,
docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md).

Scoped down from the original "dynamic context windowing" brief: there is
no existing pipeline dumping full session state into general LLM answer
context to prune -- the only place a track list currently renders is
orchestrator.py's read-only "show my session" branch, which lists every
track regardless of what the user actually asked about. This narrows
that one place: a query naming a specific instrument/track surfaces just
the matching tracks; a generic "show my session" (nothing recognizable
in it) still shows everything, unchanged.
"""

from __future__ import annotations

import re
from typing import Any


def relevant_tracks(query: str, tracks: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Returns a filtered subset of `tracks` whose names the query
    mentions, or None if the query doesn't narrow anything down (no
    matches, or every track matched) -- callers should fall back to
    showing everything in that case. Deliberately never returns an empty
    list: under-filtering (showing more than needed) is the safe failure
    mode, over-filtering (hiding a track the user meant) is not.
    """
    if not tracks:
        return None

    query_words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) >= 3}
    if not query_words:
        return None

    matched = [
        track
        for track in tracks
        if (name := str(track.get("name", "")).strip().lower())
        and any(word in name for word in query_words)
    ]

    if matched and len(matched) < len(tracks):
        return matched
    return None
