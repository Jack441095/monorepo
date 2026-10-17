import pytest

from ai.markov.melody.harmony_symbol import simplify_harmony_function


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("", "maj"),
        ("CMaj7", "maj"),
        ("Cm7", "min"),
        ("Cdim", "dim"),
        ("C+", "aug"),
        ("Csus4", "sus"),
        ("C7", "dom"),
    ],
)
def test_simplify_harmony_function(symbol: str, expected: str) -> None:
    assert simplify_harmony_function(symbol) == expected
