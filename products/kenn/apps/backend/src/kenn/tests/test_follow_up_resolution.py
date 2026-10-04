"""Short asks that lean on the previous question are searched together with it, and are not answered from the old evidence."""

import pytest

from kenn.core import chat_answer
from kenn.core.chat_routing import is_followup_query, route_query, search_query_with_history, should_use_history

HOUSE = [{"role": "user", "content": "how should i sidechain my kick and pads in this house track"}]
DRUMS = [{"role": "user", "content": "how do i compress rock drums to keep the transient snap"}]


@pytest.mark.parametrize("query, history", [
    ("louder or softer?", [{"role": "user", "content": "my hip hop backing vocals sit on top of the lead, how do i set the level"}]),
    ("what attack time though?", DRUMS),
    ("and for the chorus?", [{"role": "user", "content": "i automated my film vocal reverb for the verse, should it change later"}]),
    ("in mono too?", [{"role": "user", "content": "my game synth pads lose power when summed down, how do i fix phasing"}]),
    ("what ratio then?", [{"role": "user", "content": "how do i compress my EDM master bus without killing the drop"}]),
    ("before or after EQ?", [{"role": "user", "content": "my hip hop vocals sound harsh when i compress them, where do i de-ess"}]),
    ("on the bus or insert?", [{"role": "user", "content": "how do i saturate my drum group for more rock energy"}]),
    ("for trap hats too?", [{"role": "user", "content": "how do i use high-pass filtering to clean up my hi-hats"}]),
])
def test_a_follow_up_is_resolved_against_the_previous_question(query, history):
    assert is_followup_query(query)
    assert should_use_history(query, history)
    assert search_query_with_history(query, history).startswith(history[0]["content"])


def test_a_follow_up_with_no_previous_question_is_still_asked_back():
    # "louder or softer?" cold has nothing to be louder than, so it stays a clarifying question.
    assert route_query("louder or softer?", None, allow_llm=False) == "clarify"


@pytest.mark.parametrize("query", [
    "how do i fix bass on headphones too?",
    "how do i compress vocals then?",
    "what is the best compressor or limiter for a master?",
    "which reverb or delay for vocals?",
])
def test_a_full_question_is_not_taken_for_a_follow_up_because_of_its_last_word(query):
    assert not is_followup_query(query)


def test_and_the_bass_drops_the_kick_from_the_search_so_the_kick_answer_is_not_repeated():
    # The kick and pad question would otherwise outrank everything for "and the bass?".
    searched = search_query_with_history("and the bass?", HOUSE).lower()
    assert "kick" not in searched
    assert "sidechain" in searched and "bass" in searched


def test_a_follow_up_naming_a_new_instrument_ignores_the_answer_already_given(monkeypatch):
    old = [(9.0, {"kind": "note", "source": "kick-pads.md", "title": "Sidechain the pads", "text": "Pads duck to the kick. Bass stays put."})]
    fresh = [(8.0, {"kind": "note", "source": "bass.md", "title": "Sidechain the bass", "text": "Duck the bass to the kick."})]
    monkeypatch.setattr(chat_answer, "_load_session", lambda session_id="": {"last_retrieved_results": old})
    monkeypatch.setattr(chat_answer, "search", lambda *args, **kwargs: fresh)

    results, used_history, _relevance, _search, reused = chat_answer._resolve_results_with_topic_lock(
        "and the bass?", HOUSE, 5, [], {}, "s1"
    )

    assert used_history and not reused
    assert [chunk["source"] for _score, chunk in results] == ["bass.md"]


def test_a_follow_up_about_the_same_subject_still_reuses_the_notes_already_found(monkeypatch):
    old = [(9.0, {"kind": "note", "source": "drums.md", "title": "Drum compression attack", "text": "Attack time sets how much snap passes."})]
    monkeypatch.setattr(chat_answer, "_load_session", lambda session_id="": {"last_retrieved_results": old})
    monkeypatch.setattr(chat_answer, "search", lambda *args, **kwargs: pytest.fail("searched again"))

    _results, _used, _relevance, _search, reused = chat_answer._resolve_results_with_topic_lock(
        "what attack time though?", DRUMS, 5, [], {}, "s1"
    )

    assert reused


def test_a_parameter_follow_up_searches_again_when_the_cached_note_only_mentions_it(monkeypatch):
    # 4 Oct 2026 review: "what about the attack?" reused the vocal compression note and repeated its four steps.
    vocal = [{"role": "user", "content": "how do i set up a compressor on my vocal"}]
    old = [(9.0, {"kind": "note", "source": "vocal-comp.md", "title": "Vocal compression basics",
                  "text": "Start with a 3:1 ratio. Set attack around 10 ms. Set release around 80 ms."})]
    fresh = [(8.0, {"kind": "note", "source": "attack.md", "title": "Compressor attack and transients", "text": "Attack decides how much transient gets through."})]
    monkeypatch.setattr(chat_answer, "_load_session", lambda session_id="": {"last_retrieved_results": old})
    monkeypatch.setattr(chat_answer, "search", lambda *args, **kwargs: list(fresh))

    results, used_history, _relevance, _search, reused = chat_answer._resolve_results_with_topic_lock(
        "what about the attack?", vocal, 5, [], {}, "s1"
    )

    assert used_history and not reused
    assert [chunk["source"] for _score, chunk in results] == ["attack.md"]


@pytest.mark.parametrize("query, named", [
    ("and the snare?", "snare"),
    ("and the hats?", "hats"),
    ("and the synth?", "synth"),
    ("what about the pads?", "pads"),
])
def test_a_follow_up_naming_another_drum_or_a_synth_drops_the_kick_from_the_search(query, named):
    # 4 Oct 2026 review: kick and snare are both "drums", so "and the snare?" kept "kick" and the kick note won.
    kick = [{"role": "user", "content": "how do i make my kick punch through in a house track"}]
    searched = search_query_with_history(query, kick).lower()
    assert "kick" not in searched
    assert named in searched and "punch through" in searched
