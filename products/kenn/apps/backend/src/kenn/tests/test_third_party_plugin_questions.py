"""A question about a third-party plug-in is answered from general technique, and says the notes hold no manual for it."""

import pytest

from kenn.core import chat_answer
from kenn.core.chat_grounding import names_a_product

NO_MANUAL = "I don't have a manual for that plug-in in my notes"

COMPRESSION_NOTE = (
    120.0,
    {
        "kind": "note",
        "source": "glue-compression.md",
        "title": "Bus compression for glue",
        "tags": ["compression", "drums"],
        "text": "Short answer:\nA low ratio and a slow attack glue a drum bus together.\n\nTry this:\n1. Start with a low ratio.\n2. Set a slow attack.",
    },
)


@pytest.mark.parametrize("query, family", [
    ("how do i make a gritty wobble bass in Serum for dubstep", "serum"),
    ("how do i cut mud with FabFilter Pro-Q 3 on hip hop vocals", "fabfilter"),
    ("best Valhalla VintageVerb settings for a huge EDM snare", "valhalla"),
    ("how do i master a rock single with iZotope Ozone 11", "izotope"),
    ("how do i tune backing vocals naturally with Celemony Melodyne", "celemony"),
    ("how do i glue rock drums with Waves SSL G-Bus compressor", "waves"),
])
def test_the_plugin_maker_in_a_question_is_recognised(query, family):
    assert names_a_product(query) == family


def test_a_question_about_ableton_s_own_compressor_is_not_a_third_party_question():
    assert names_a_product("how do i glue rock drums with Glue Compressor") == ""


def test_a_third_party_plugin_with_no_note_gets_the_no_manual_line():
    caveat = chat_answer._uncovered_plugin_caveat("how do i glue rock drums with Waves SSL G-Bus compressor", [COMPRESSION_NOTE])
    assert caveat.startswith(NO_MANUAL)
    assert "\n" not in caveat


def test_a_third_party_plugin_the_notes_do_cover_gets_no_caveat():
    note = (120.0, {**COMPRESSION_NOTE[1], "text": COMPRESSION_NOTE[1]["text"] + "\nWaves SSL G-Bus: ratio 2:1 on the bus."})
    assert chat_answer._uncovered_plugin_caveat("how do i glue rock drums with Waves SSL G-Bus compressor", [note]) == ""


def test_the_no_manual_line_leads_the_answer_and_no_model_rewrite_is_asked_for(monkeypatch):
    query = "how do i glue rock drums with Waves SSL G-Bus compressor"
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *args, **kwargs: pytest.fail("asked the model"))

    answer, llm_used = chat_answer.make_answer(query, [COMPRESSION_NOTE], allow_llm=True, route="production")

    assert answer.startswith(NO_MANUAL)
    assert not llm_used


def test_the_no_manual_line_names_no_parameter_or_value():
    caveat = chat_answer._uncovered_plugin_caveat("how do i cut mud with FabFilter Pro-Q 3 on hip hop vocals", [COMPRESSION_NOTE])
    assert not any(ch.isdigit() for ch in caveat)
    assert "FabFilter" not in caveat and "Pro-Q" not in caveat
