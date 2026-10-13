"""The grounding gate's [#n] tags are for the gate; the producer should never see them.

Since 11 Oct 2026 (`d783942b`) the model tags each figure with the excerpt it came from, "150 ms [#2]", and the
gate checks that tag against that excerpt. The plan recorded the follow-up the same day: the tag reached the
producer as written. Confirmed 13 Oct on the real payload path: an accepted answer read "Set the release to
150 ms [#1] so ..." in the companion. The Sources list under an answer is bulleted, de-duplicated and capped at
three, so an ordinal cannot be mapped onto it reliably; the tag is removed instead, after every check has read it.
"""

from __future__ import annotations

import pytest

from kenn.core import chat_answer, chat_grounding
from kenn.tests.test_payload_transient_cache import _model, cache_writes  # noqa: F401 (pytest fixture)
from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, QUERY

TAGGED = ACCEPTED_ANSWER.replace("150 ms so", "150 ms [#1] so")


@pytest.mark.parametrize("written, shown", [
    ("Set the release to 150 ms [#2] then listen.", "Set the release to 150 ms then listen."),
    ("Set the release to 150 ms [#2].", "Set the release to 150 ms."),
    ("Set the release to 150 ms ([#2]).", "Set the release to 150 ms."),
    ("Hard against it: 900 ms[#2] so it breathes.", "Hard against it: 900 ms so it breathes."),
    ("Old-style id 4:1 [#abc123def0aa] works too.", "Old-style id 4:1 works too."),
    ("- [#1] Set the ratio to 4:1 [#2]\n- Then", "- Set the ratio to 4:1\n- Then"),
])
def test_tags_come_off_without_gluing_words_or_moving_figures(written, shown):
    assert chat_grounding.display_answer(written) == shown


def test_an_answer_without_tags_is_returned_untouched():
    assert chat_grounding.display_answer(ACCEPTED_ANSWER) is ACCEPTED_ANSWER


def test_a_tag_whose_id_reads_as_a_figure_is_left_in_place():
    # A pre-11 Oct hex id like efac7b4076db holds "4076db", which the figure scanner reads as 4076 dB, so taking
    # the tag out would look like losing a figure. The guard keeps the text as the gate accepted it.
    written = "Set the ratio to 4:1 [#efac7b4076db] here."
    assert chat_grounding.display_answer(written) == written


def test_if_removing_a_tag_would_change_a_figure_the_tags_stay(monkeypatch):
    # The repair helper returns "" when the figures before and after differ. A visible tag is ugly but honest;
    # a silently altered figure is neither, so display falls back to the text the gate accepted.
    monkeypatch.setattr(chat_grounding, "repair_misattributed_citations", lambda answer, misattributed: "")
    assert chat_grounding.display_answer("150 ms [#1]") == "150 ms [#1]"


def test_the_producer_gets_the_answer_without_tags(monkeypatch, cache_writes):  # noqa: F811
    _model(monkeypatch, TAGGED)

    payload = chat_answer.answer_payload(QUERY)

    assert payload["llm_enhanced"] is True
    assert "[#" not in payload["answer"]
    assert "Set the release to 150 ms so the bass recovers" in payload["answer"]
    # The cache replays this payload to the next asker, so it must hold the same text the producer saw.
    assert all("[#" not in str(event) for events in cache_writes for event in events)


def test_the_gate_still_judges_the_tagged_text(monkeypatch, cache_writes):  # noqa: F811
    judged = []
    real = chat_answer.generated_answer_validation

    def spy(query, results, answer, **kwargs):
        judged.append(answer)
        return real(query, results, answer, **kwargs)

    monkeypatch.setattr(chat_answer, "generated_answer_validation", spy)
    _model(monkeypatch, TAGGED)

    chat_answer.answer_payload(QUERY)

    assert judged and all("[#1]" in text for text in judged)
