"""Tests for thursday/ops_intake.py's shared pipe-delimited structured
command parser (factored out once thursday.ops.advertising_ops needed the
identical logic thursday.ops.marketing_ops already had).
"""

from __future__ import annotations

import pytest

from thursday.ops.ops_intake import parse_structured_command

PREFIXES = ["create thing:", "new thing:"]
ALIASES = {"colour": "color", "color": "color", "tags": "tags"}
LIST_FIELDS = {"tags"}


def test_objective_only():
    assert parse_structured_command("create thing: a widget", PREFIXES, ALIASES, LIST_FIELDS) == (
        "a widget", {},
    )


def test_case_insensitive_prefix_match():
    assert parse_structured_command("CREATE THING: a widget", PREFIXES, ALIASES, LIST_FIELDS) == (
        "a widget", {},
    )


def test_second_prefix_also_matches():
    assert parse_structured_command("new thing: a gadget", PREFIXES, ALIASES, LIST_FIELDS) == (
        "a gadget", {},
    )


def test_fields_parsed_and_aliased():
    text = "create thing: a widget | colour: red | tags: shiny, new"
    objective, fields = parse_structured_command(text, PREFIXES, ALIASES, LIST_FIELDS)
    assert objective == "a widget"
    assert fields == {"color": "red", "tags": ["shiny", "new"]}


def test_unrecognized_field_key_silently_ignored():
    text = "create thing: a widget | nonsense: whatever"
    objective, fields = parse_structured_command(text, PREFIXES, ALIASES, LIST_FIELDS)
    assert objective == "a widget"
    assert fields == {}


def test_field_segment_without_colon_ignored():
    text = "create thing: a widget | just some text with no colon"
    objective, fields = parse_structured_command(text, PREFIXES, ALIASES, LIST_FIELDS)
    assert objective == "a widget"
    assert fields == {}


def test_none_for_non_matching_text():
    assert parse_structured_command("what's the weather", PREFIXES, ALIASES, LIST_FIELDS) is None


def test_raises_on_empty_objective():
    with pytest.raises(ValueError):
        parse_structured_command("create thing: | colour: red", PREFIXES, ALIASES, LIST_FIELDS)


def test_list_field_strips_whitespace_and_drops_empties():
    text = "create thing: x | tags: a,  b ,, c"
    _, fields = parse_structured_command(text, PREFIXES, ALIASES, LIST_FIELDS)
    assert fields["tags"] == ["a", "b", "c"]
