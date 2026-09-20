"""Unit tests for the Live-independent userfolder: URI path matching.

Deliberately kept outside the ``tests/`` package (see test_browser_search.py
for why). Reproduces, with plain fake objects, the real URI format learned
live 2026-09-06: `userfolder:<url-encoded-root>#<colon-separated-relative>`.
"""

import importlib.util
from pathlib import Path

# Load the module directly from its file, bypassing `abletonosc/__init__.py`
# (which imports `Live` and is only importable inside Ableton's embedded
# Python). `browser_sample_search.py` itself has no such dependency.
_MODULE_PATH = Path(__file__).resolve().parent / "abletonosc" / "browser_sample_search.py"
_spec = importlib.util.spec_from_file_location("abletonosc_browser_sample_search", _MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
find_sample_item_by_path = _module.find_sample_item_by_path
reconstruct_path_from_uri = _module.reconstruct_path_from_uri
clear_sample_item_cache = _module.clear_sample_item_cache


class FakeBrowserItem:
    def __init__(self, name="", *, is_loadable=False, is_folder=False, uri="", children=None):
        self.name = name
        self.is_loadable = is_loadable
        self.is_folder = is_folder
        self.uri = uri
        self.children = children or []


REAL_URI = "userfolder:<LOCAL_VOLUME>/Samples%202021%20-%3E#2021:Resamples:2021:Bass:blatwaxOneshotBassElectricHighF.wav"
REAL_PATH = "<LOCAL_VOLUME>/Samples 2021 ->/2021/Resamples/2021/Bass/blatwaxOneshotBassElectricHighF.wav"


def test_reconstruct_path_from_uri_matches_the_real_observed_format():
    assert reconstruct_path_from_uri(REAL_URI) == REAL_PATH


def test_reconstruct_path_from_uri_handles_simple_single_level_relative_path():
    uri = "userfolder:/Volumes/X#kick.wav"
    assert reconstruct_path_from_uri(uri) == "/Volumes/X/kick.wav"


def test_reconstruct_path_from_uri_returns_none_for_other_schemes():
    assert reconstruct_path_from_uri("query:something") is None
    assert reconstruct_path_from_uri("") is None


def test_reconstruct_path_from_uri_returns_none_when_malformed():
    assert reconstruct_path_from_uri("userfolder:/Volumes/X") is None  # no '#'


def test_find_sample_item_by_path_locates_a_real_file_several_folders_deep():
    leaf = FakeBrowserItem("blatwaxOneshotBassElectricHighF.wav", is_loadable=True, uri=REAL_URI)
    bass_folder = FakeBrowserItem("Bass", is_folder=True, children=[leaf])
    year_folder = FakeBrowserItem("2021", is_folder=True, children=[bass_folder])
    resamples_folder = FakeBrowserItem("Resamples", is_folder=True, children=[year_folder])
    root_folder = FakeBrowserItem("Samples 2021 ->", is_folder=True, children=[resamples_folder])

    found = find_sample_item_by_path([root_folder], REAL_PATH)
    assert found is leaf


def test_find_sample_item_by_path_returns_none_when_folder_is_not_registered():
    # Simulates the real, honest limitation: a file whose containing folder
    # was never added as an Ableton Place has no matching item anywhere.
    unrelated_leaf = FakeBrowserItem("other.wav", is_loadable=True, uri="userfolder:/Volumes/X#other.wav")
    root_folder = FakeBrowserItem("X", is_folder=True, children=[unrelated_leaf])

    found = find_sample_item_by_path([root_folder], "<LOCAL_VOLUME>/testing-for-NITE-DSP/kick.wav")
    assert found is None


def test_find_sample_item_by_path_never_descends_into_a_loadable_leaf():
    # A loadable non-folder item's `.children` (if any exist accidentally)
    # must never be walked -- it's a leaf.
    leaf = FakeBrowserItem("kick.wav", is_loadable=True, uri="userfolder:/Volumes/X#kick.wav", children=[
        FakeBrowserItem("should-not-be-visited.wav", is_loadable=True, uri="userfolder:/Volumes/X#should-not-be-visited.wav"),
    ])
    found = find_sample_item_by_path([leaf], "/Volumes/X/should-not-be-visited.wav")
    assert found is None


def test_find_sample_item_by_path_is_bounded_against_cycles():
    leaf = FakeBrowserItem("kick.wav", is_loadable=True, uri="userfolder:/Volumes/X#kick.wav")
    folder = FakeBrowserItem("X", is_folder=True, children=[leaf])
    folder.children.append(folder)  # self-reference

    found = find_sample_item_by_path([folder, folder], "/Volumes/X/kick.wav")
    assert found is leaf


def test_find_sample_item_by_path_reuses_exact_validated_match_from_cache():
    clear_sample_item_cache()
    leaf = FakeBrowserItem("kick.wav", is_loadable=True, uri="userfolder:/Volumes/X#kick.wav")
    root_folder = FakeBrowserItem("X", is_folder=True, children=[leaf])

    first_stats = {}
    assert find_sample_item_by_path([root_folder], "/Volumes/X/kick.wav", stats=first_stats) is leaf
    assert first_stats == {"visited": 2, "sample_reconstructed_paths": ["/Volumes/X/kick.wav"], "cache_hit": False}

    second_stats = {}
    assert find_sample_item_by_path([], "/Volumes/X/kick.wav", stats=second_stats) is leaf
    assert second_stats == {"visited": 0, "sample_reconstructed_paths": [], "cache_hit": True}


def test_find_sample_item_by_path_discards_invalid_cached_item_and_falls_back_to_tree():
    clear_sample_item_cache()
    stale = FakeBrowserItem("kick.wav", is_loadable=True, uri="userfolder:/Volumes/X#kick.wav")
    root_folder = FakeBrowserItem("X", is_folder=True, children=[stale])
    assert find_sample_item_by_path([root_folder], "/Volumes/X/kick.wav") is stale

    replacement = FakeBrowserItem("kick.wav", is_loadable=True, uri="userfolder:/Volumes/X#kick.wav")
    stale.is_loadable = False
    replacement_root = FakeBrowserItem("X", is_folder=True, children=[replacement])
    stats = {}
    assert find_sample_item_by_path([replacement_root], "/Volumes/X/kick.wav", stats=stats) is replacement
    assert stats["cache_hit"] is False
