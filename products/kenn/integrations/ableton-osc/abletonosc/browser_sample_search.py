"""Pure, Live-independent helpers for matching a real file path against
Ableton's ``userfolder:`` browser URI scheme.

Extracted so this logic is unit-testable without a running Ableton Live
instance, mirroring ``browser_search.py``. The real URI format was learned
live (2026-09-06) by inspecting actual browser items under
``browser.user_folders``:

    userfolder:<url-encoded-registered-folder-root>#<colon-separated-relative-path>

e.g. ``userfolder:/Volumes/X/Samples%202021%20-%3E#2021:Bass:kick.wav``
reconstructs to ``/Volumes/X/Samples 2021 ->/2021/Bass/kick.wav``.

This only resolves a file that already lives inside a folder the user has
registered as a Place in Ableton's own Library preferences (Live >
Preferences > Library > Places) -- ``browser.add_item_to_places()``, which
would register one programmatically, does not exist on the real Remote
Script ``Browser`` object (confirmed live; it only exists on a separate,
unrelated Push 3 hardware-controller API). A sample outside every
registered Place cannot be found this way, and this module never guesses
around that -- see ``find_sample_item_by_path``'s return value.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Iterable
from urllib.parse import unquote


# A browser tree walk is expensive for a large personal library. Keep only
# exact, already-validated URI matches in memory. This is deliberately
# process-local and bounded: it is a performance hint, never a new source of
# authority, and a cache miss still uses the complete bounded tree search.
_PATH_CACHE_MAX_ITEMS = 4096
_PATH_CACHE: OrderedDict[str, Any] = OrderedDict()


def reconstruct_path_from_uri(uri: str) -> str | None:
    """Reconstruct a real absolute file path from a browser item's URI.

    Returns ``None`` for any URI scheme other than ``userfolder:`` (not
    handled here, never guessed) or a malformed ``userfolder:`` URI.
    """
    if not uri.startswith("userfolder:"):
        return None
    remainder = uri[len("userfolder:"):]
    if "#" not in remainder:
        return None
    root_encoded, relative_colon = remainder.split("#", 1)
    root = unquote(root_encoded)
    if not root or not relative_colon:
        return None
    relative = relative_colon.replace(":", "/")
    return root.rstrip("/") + "/" + relative


def find_sample_item_by_path(
    user_folders: Iterable[Any],
    target_path: str,
    *,
    max_depth: int = 12,
    max_children: int = 20000,
    stats: dict[str, Any] | None = None,
) -> Any | None:
    """Bounded, depth-first search of a browser user-folders tree for the
    loadable item whose real reconstructed path exactly matches
    ``target_path``. Returns ``None`` if nothing matches -- most commonly
    because the file's containing folder isn't registered as a Place.

    Depth-first (not breadth-first) matters here: a real user sample library
    can have many thousands of files spread across many sibling folders --
    breadth-first would exhaust ``max_children``/time exploring every
    sibling at each level before ever going deep enough to reach the target
    (confirmed live 2026-09-06: a breadth-first version visited 9000+ items
    without reaching a file 5 folders deep). Depth-first finds it in the
    common case without needing to touch most of the tree at all.

    ``stats``, if given, is filled in with bounded debugging counters
    (``visited``, ``sample_reconstructed_paths``, and ``cache_hit``) so a
    caller can tell a genuinely-missing Place apart from a search that ran
    out of bounds or a validated repeat lookup, without needing a separate
    diagnostic pass.
    """
    if stats is not None:
        stats["visited"] = 0
        stats["sample_reconstructed_paths"] = []

    cached = _PATH_CACHE.get(target_path)
    if cached is not None:
        cached_is_loadable = bool(getattr(cached, "is_loadable", False))
        cached_is_folder = bool(getattr(cached, "is_folder", False))
        cached_path = reconstruct_path_from_uri(str(getattr(cached, "uri", "")))
        if cached_is_loadable and not cached_is_folder and cached_path == target_path:
            _PATH_CACHE.move_to_end(target_path)
            if stats is not None:
                stats["cache_hit"] = True
            return cached
        _PATH_CACHE.pop(target_path, None)
    if stats is not None:
        stats["cache_hit"] = False

    pending: list[tuple[Any, int]] = [(item, 0) for item in user_folders]
    visited: set[int] = set()
    while pending:
        item, depth = pending.pop()
        marker = id(item)
        if marker in visited:
            continue
        visited.add(marker)
        if stats is not None:
            stats["visited"] += 1

        is_loadable = bool(getattr(item, "is_loadable", False))
        is_folder = bool(getattr(item, "is_folder", False))
        if is_loadable and not is_folder:
            reconstructed = reconstruct_path_from_uri(str(getattr(item, "uri", "")))
            if stats is not None and reconstructed is not None and len(stats["sample_reconstructed_paths"]) < 5:
                stats["sample_reconstructed_paths"].append(reconstructed)
            if reconstructed is not None and reconstructed == target_path:
                _PATH_CACHE[target_path] = item
                _PATH_CACHE.move_to_end(target_path)
                while len(_PATH_CACHE) > _PATH_CACHE_MAX_ITEMS:
                    _PATH_CACHE.popitem(last=False)
                return item
            continue
        if depth < max_depth and is_folder:
            try:
                children = list(item.children)[:max_children]
            except Exception:
                continue
            for child in children:
                pending.append((child, depth + 1))
    return None


def clear_sample_item_cache() -> None:
    """Clear the process-local exact-path lookup cache.

    The real Remote Script does not currently expose a browser-change event
    that KENN can subscribe to. Clearing is therefore available to lifecycle
    code and tests when a session or Places configuration changes.
    """
    _PATH_CACHE.clear()


__all__ = ["clear_sample_item_cache", "find_sample_item_by_path", "reconstruct_path_from_uri"]
