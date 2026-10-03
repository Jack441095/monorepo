"""A model answer must not bring in plugin brands nobody mentioned (3 Oct: "advice on mixing low end?" named FabFilter Pro-Q3 and Timeless)."""

from __future__ import annotations

import pytest

from kenn.core.chat_grounding import generated_answer_validation, unasked_product_names

from kenn.tests.test_claim_citation_grounding import QUERY, RESULTS

PLAIN = "Short answer: shorten the release until the bass settles before the next kick."


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("Cut the mud with FabFilter Pro-Q3 around 250 Hz.", ["fabfilter"]),
        ("Try the Pro-D2 on the sibilance.", ["fabfilter"]),
        ("Add the Timeless delay for width.", ["fabfilter"]),
        ("Use iZotope Ozone to master it.", ["izotope"]),
        ("Waves SSL channel strip works here.", ["waves"]),
        ("Serum and Omnisphere both do this.", ["omnisphere", "serum"]),
    ],
)
def test_a_brand_nobody_mentioned_is_reported(answer, expected):
    assert unasked_product_names(answer, "how do I tighten my low end?") == expected


@pytest.mark.parametrize(
    "answer",
    [
        "Sine waves add up, and sound waves bounce off the wall.",
        "Use the EQ Eight and a Compressor in Live, then check the mono sum.",
        "Cut the mud with a high-pass at 30 Hz.",
    ],
)
def test_ordinary_words_and_stock_devices_are_not_brands(answer):
    assert unasked_product_names(answer, "how do I tighten my low end?") == []


def test_a_brand_the_user_named_may_be_used():
    assert unasked_product_names("In Pro-Q 3 pull 250 Hz down.", "I'm using FabFilter on the bus") == []


def test_a_brand_in_the_notes_may_be_used():
    assert unasked_product_names("Pro-L 2 has a true peak mode.", "limiting", "FabFilter Pro-L 2 true peak notes") == []


def test_the_gate_rejects_an_answer_that_names_a_plugin_nobody_asked_about():
    check = generated_answer_validation(
        QUERY, RESULTS, PLAIN + " Try FabFilter Pro-C 2 for it.",
        route="production", confidence="high", answer_mode="quick_fix",
    )
    assert check["unasked_products"] == ["fabfilter"]
    assert "generated answer names a product that nobody mentioned" in check["warnings"]
    assert not check["accepted"]


def test_the_gate_reports_nothing_for_an_answer_without_brands():
    check = generated_answer_validation(
        QUERY, RESULTS, PLAIN, route="production", confidence="high", answer_mode="quick_fix",
    )
    assert check["unasked_products"] == []
    assert "generated answer names a product that nobody mentioned" not in check["warnings"]
