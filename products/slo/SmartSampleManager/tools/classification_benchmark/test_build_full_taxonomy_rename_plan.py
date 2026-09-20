import build_full_taxonomy_rename_plan as module


def test_similarity_gate_is_optional_by_default():
    assert module.passes_similarity_gate(0.1, None)


def test_similarity_gate_rejects_low_or_invalid_values():
    assert module.passes_similarity_gate(0.730, 0.731) is False
    assert module.passes_similarity_gate(0.731, 0.731) is True
    assert module.passes_similarity_gate("not-a-number", 0.731) is False
