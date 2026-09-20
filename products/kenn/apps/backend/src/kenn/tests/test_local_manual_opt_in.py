from __future__ import annotations

from kenn.retrieval.build_index import should_index_pdf


def test_local_product_manual_requires_explicit_opt_in() -> None:
    entry = {"index_policy": "local_opt_in"}
    assert should_index_pdf(entry) is False
    assert should_index_pdf(entry, include_local_manuals=True) is True


def test_reference_only_pdf_cannot_be_enabled_by_manual_opt_in() -> None:
    assert should_index_pdf({"index_policy": "reference_only"}, include_local_manuals=True) is False


def test_unrestricted_curated_pdf_keeps_existing_default_behavior() -> None:
    assert should_index_pdf({"index_policy": "index"}) is True
