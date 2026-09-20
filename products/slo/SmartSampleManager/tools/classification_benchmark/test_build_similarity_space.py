import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("build_similarity_space.py")
SPEC = importlib.util.spec_from_file_location("build_similarity_space", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_space_is_deterministic_and_not_a_classifier():
    x = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], dtype=np.float32)
    paths = ["/a.wav", "/b.wav", "/c.wav"]
    first = MODULE.build_space(x, paths)
    second = MODULE.build_space(x, paths)
    assert first["points"] == second["points"]
    assert first["n_points"] == 3
    assert first["safety"]["clusters_created"] is False
    assert first["safety"]["taxonomy_inferred"] is False


def test_mismatched_rows_fail_closed():
    try:
        MODULE.build_space(np.ones((2, 2), dtype=np.float32), ["/a.wav"])
    except ValueError as exc:
        assert "matching" in str(exc)
    else:
        raise AssertionError("mismatched embedding/path rows were accepted")
