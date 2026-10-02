"""A bass null at the listening chair never said "room" or "acoustic", so the room-placement note ranked 4th.

The wrapper's knowledge row upgrade-room-null caught it; the note's own tags are room modes and listening position.
"""

import pytest

from kenn.retrieval.retrieval import query_topics


@pytest.mark.parametrize("question", [
    "There is a very narrow bass null at my chair. Should I apply a large monitor-EQ boost at that frequency?",
    "Where should my listening position sit relative to the room modes?",
    "Do bass traps help with a bass null at the mix position?",
])
def test_a_room_mode_or_null_question_is_acoustics(question):
    assert "acoustics" in query_topics(question)


def test_a_plain_eq_question_is_not_pulled_into_acoustics():
    assert "acoustics" not in query_topics("My vocal sounds thin next to the guitars, what should I try?")
