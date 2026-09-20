"""Pure, Live-independent browser-tree search used by device insertion.

Extracted from ``track.py`` so this logic is unit-testable without a
running Ableton Live instance (that module imports the ``Live`` package,
which only exists inside Live's embedded Python and cannot be imported in
a normal test process).

This closes a real bug found during KENN's real-Live device-insertion
qualification: requesting a device by a short name such as "Reverb" could
silently resolve to an unrelated device such as "Convolution Reverb"
whenever the substring match was reached first in breadth-first order.
The fix is a two-pass search -- an exact name match anywhere in the tree
always wins over any substring match, no matter which one breadth-first
traversal happens to reach first.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol


class BrowserItem(Protocol):
    name: str
    is_loadable: bool
    children: Iterable[Any]


def find_browser_device_item(search_locations: Iterable[Any], device_uri: str) -> Any | None:
    """Search a browser tree for the best match for ``device_uri``.

    An exact ``item.name == device_uri`` match anywhere in the tree always
    wins over a substring match, even if the substring match is reached
    first by breadth-first traversal. Only falls back to the first
    substring match (in breadth-first order) when no exact match exists
    anywhere. Returns ``None`` if neither is found.
    """
    pending = list(search_locations)
    visited: set[int] = set()
    first_substring_match: Any | None = None

    while pending:
        item = pending.pop(0)
        marker = id(item)
        if marker in visited:
            continue
        visited.add(marker)

        try:
            item_name = str(item.name)
        except Exception:
            item_name = ""

        is_loadable = bool(getattr(item, "is_loadable", False))
        if is_loadable and item_name == device_uri:
            return item
        if is_loadable and first_substring_match is None and device_uri in item_name:
            first_substring_match = item

        try:
            pending.extend(list(item.children))
        except Exception:
            # Some Live browser items do not expose children; they are
            # simply leaves in the search tree.
            continue

    return first_substring_match


__all__ = ["find_browser_device_item"]
