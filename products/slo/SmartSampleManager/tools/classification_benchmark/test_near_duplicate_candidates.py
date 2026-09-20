import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("near_duplicate_candidates.py")
SPEC = importlib.util.spec_from_file_location("near_duplicate_candidates", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_high_similarity_pairs_are_review_only():
    vectors = np.array([[1.0, 0.0], [0.999, 0.02], [0.0, 1.0]], dtype=np.float32)
    result = MODULE.build_candidates(vectors, ["/a.wav", "/b.wav", "/c.wav"], threshold=0.99, neighbours=2)
    assert result["n_groups"] == 1
    assert result["groups"][0]["member_count"] == 2
    assert result["groups"][0]["decision"].startswith("review_only")
    assert result["safety"]["byte_identity_proven"] is False


def test_bad_threshold_fails_closed():
    try:
        MODULE.build_candidates(np.ones((2, 2)), ["/a", "/b"], threshold=1.1)
    except ValueError as exc:
        assert "threshold" in str(exc)
    else:
        raise AssertionError("invalid threshold was accepted")
