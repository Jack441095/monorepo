"""Unit tests for the Live-independent browser-tree device search.

Deliberately kept outside the ``tests/`` package: that package's
``__init__.py`` eagerly binds a live OSC socket at import time (it expects
a running Ableton Live instance with this Remote Script installed), which
these tests must not require. ``abletonosc.browser_search`` has zero
dependency on the ``Live`` module, so it can be unit tested in a plain
Python process.

These reproduce, with plain fake objects, the exact real-Live bug found
during KENN's device-insertion qualification: a short name like "Reverb"
resolving to the wrong device ("Convolution Reverb") because a substring
match was reached before an exact match elsewhere in the tree.
"""

import importlib.util
from pathlib import Path

# Load the module directly from its file, bypassing `abletonosc/__init__.py`
# (which imports `Live` and is only importable inside Ableton's embedded
# Python). `browser_search.py` itself has no such dependency.
_MODULE_PATH = Path(__file__).resolve().parent / "abletonosc" / "browser_search.py"
_spec = importlib.util.spec_from_file_location("abletonosc_browser_search", _MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
find_browser_device_item = _module.find_browser_device_item


class FakeBrowserItem:
    def __init__(self, name, *, is_loadable=False, children=None):
        self.name = name
        self.is_loadable = is_loadable
        self.children = children or []


def test_exact_match_wins_even_when_a_substring_match_is_reached_first():
    convolution_reverb = FakeBrowserItem("Convolution Reverb", is_loadable=True)
    reverb = FakeBrowserItem("Reverb", is_loadable=True)
    category = FakeBrowserItem("Audio Effects", children=[convolution_reverb, reverb])

    found = find_browser_device_item([category], "Reverb")
    assert found is reverb


def test_falls_back_to_substring_match_when_no_exact_match_exists():
    align_delay = FakeBrowserItem("Align Delay", is_loadable=True)
    category = FakeBrowserItem("Audio Effects", children=[align_delay])

    found = find_browser_device_item([category], "Delay")
    assert found is align_delay


def test_returns_none_when_nothing_matches():
    unrelated = FakeBrowserItem("Auto Filter", is_loadable=True)
    category = FakeBrowserItem("Audio Effects", children=[unrelated])

    assert find_browser_device_item([category], "Reverb") is None


def test_a_non_loadable_category_sharing_the_device_name_is_never_selected():
    category_named_like_device = FakeBrowserItem("Compressor", is_loadable=False, children=[
        FakeBrowserItem("Compressor", is_loadable=True),
    ])

    found = find_browser_device_item([category_named_like_device], "Compressor")
    assert found is not None
    assert found.is_loadable is True


def test_search_is_bounded_against_cyclic_or_repeated_children():
    leaf = FakeBrowserItem("Reverb", is_loadable=True)
    category = FakeBrowserItem("Audio Effects", children=[leaf])
    category.children.append(category)  # self-reference

    found = find_browser_device_item([category, category], "Reverb")
    assert found is leaf


def test_exact_match_found_deeper_in_the_tree_still_beats_an_earlier_substring_match():
    substring_hit = FakeBrowserItem("Color Limiter", is_loadable=True)
    exact_hit = FakeBrowserItem("Limiter", is_loadable=True)
    first_location = FakeBrowserItem("Audio Effects", children=[substring_hit])
    second_location = FakeBrowserItem("Instruments", children=[exact_hit])

    found = find_browser_device_item([first_location, second_location], "Limiter")
    assert found is exact_hit
