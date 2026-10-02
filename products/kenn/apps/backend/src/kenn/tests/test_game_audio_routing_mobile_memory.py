"""A mobile-build audio memory question routed to "production" because it never says Wwise, Unity or "game build".

The public wrapper refuses game audio by route, so this one was answered where its 27 siblings are refused.
"""

import pytest

from kenn.core.chat_routing import route_query
from kenn.retrieval.retrieval import query_topics


@pytest.mark.parametrize("question", [
    "My mobile build runs out of audio memory when ambience and combat are active. What should I reduce first?",
    "Our mobile build is over its audio memory budget on the second level. What goes first?",
])
def test_a_mobile_build_audio_memory_question_is_game_audio(question):
    assert "game_audio" in query_topics(question)
    assert route_query(question, []) == "game_audio"


def test_a_plain_mix_question_is_not_pulled_into_game_audio():
    assert route_query("My vocal sounds thin next to the guitars, what should I try?", []) != "game_audio"
