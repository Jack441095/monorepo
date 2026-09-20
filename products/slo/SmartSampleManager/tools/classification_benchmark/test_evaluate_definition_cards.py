import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("evaluate_definition_cards.py")
SPEC = importlib.util.spec_from_file_location("evaluate_definition_cards", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_vector_keeps_missing_physical_values_as_nan():
    card = {"signal": {"rms_dbfs": -20.0}, "spectrum": {}, "temporal": {}, "pitch": {}, "spatial": {}}
    vector = MODULE._vector(card)
    assert vector[0] == -20.0
    assert np.isnan(vector[1])
    assert len(vector) == len(MODULE.FEATURE_KEYS)


def test_imputation_uses_training_fold_only():
    train = np.array([[1.0, np.nan], [3.0, 5.0]])
    test = np.array([[np.nan, 7.0]])
    a, b = MODULE._impute(train, test)
    assert np.allclose(a, [[1.0, 5.0], [3.0, 5.0]])
    assert np.allclose(b, [[2.0, 7.0]])
