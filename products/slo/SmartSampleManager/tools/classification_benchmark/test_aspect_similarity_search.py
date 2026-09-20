from pathlib import Path
import importlib.util

import numpy as np


MODULE_PATH = Path(__file__).with_name("aspect_similarity_search.py")
SPEC = importlib.util.spec_from_file_location("aspect_similarity_search", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_search_excludes_query_and_reports_aspects():
    paths = np.asarray(["/a.wav", "/b.wav", "/c.wav"], dtype=object)
    base = np.eye(3, dtype=np.float32)
    index = {"paths": paths, "version": "test", "cache_sha256": "x"}
    for aspect in MODULE.ASPECT_FEATURES:
        index[aspect] = base.copy()
    rows = MODULE.search(index, "/a.wav", {"spectrum": 1, "timbre": 0,
                                             "pitch": 0, "amplitude": 0}, 2)
    assert len(rows) == 2
    assert all(row["path"] != "/a.wav" for row in rows)
    assert rows[0]["path"] == "/b.wav" or rows[0]["path"] == "/c.wav"
    assert "spectrum" in rows[0]


def test_index_has_all_named_aspects(tmp_path):
    names = np.asarray(sorted({n for values in MODULE.ASPECT_FEATURES.values() for n in values}), dtype=object)
    cache = tmp_path / "cache.npz"
    np.savez(cache, F=np.ones((2, len(names)), dtype=np.float32),
             paths=np.asarray(["/a.wav", "/b.wav"], dtype=object),
             names=names, version="test")
    index = MODULE.build_index(cache)
    assert set(MODULE.ASPECT_FEATURES).issubset(index)

