"""A message that is only a plugin brand is a question back, not an answer about the generic word in it."""

from __future__ import annotations

import pytest

from kenn.core.chat_grounding import names_only_a_product
from kenn.core.chat_routing import is_unclear_query, route_query


@pytest.mark.parametrize("query", ["fab filter", "Fab Filter?", "fabfilter", "FabFilter Pro-Q 3", "izotope", "uad"])
def test_a_bare_brand_name_gets_a_clarifying_question(query):
    # 3 Oct: "fab filter" was read as the generic word "filter" and the model wrote a made-up description of a "Fab Filter".
    assert names_only_a_product(query)
    assert is_unclear_query(query)
    assert route_query(query, allow_llm=False) == "clarify"


@pytest.mark.parametrize("query", [
    "How do I de-ess a vocal with FabFilter Pro-Q 3?",
    "fab filter eq for the low end",
    "how do I set up a filter sweep",
    "low pass filter on a pad",
])
def test_a_brand_with_a_task_or_a_plain_filter_question_is_left_alone(query):
    assert not names_only_a_product(query)
    assert route_query(query, allow_llm=False) != "clarify"
