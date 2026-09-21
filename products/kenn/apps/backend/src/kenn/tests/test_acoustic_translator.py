"""Unit tests for Acoustic Terminology Translation Engine and LLM System Prompt Integration."""

from kenn.core.acoustic_translator import (
    analyze_acoustic_descriptors,
    build_acoustic_guidance_prompt,
    ACOUSTIC_DICTIONARY,
)
from kenn.llm.llm_rewrite import build_system_prompt


def test_acoustic_dictionary_keys():
    expected_terms = {"muddy", "harsh", "boxy", "sibilant", "thin", "boomy", "dark", "dull", "honky", "flabby"}
    for term in expected_terms:
        assert term in ACOUSTIC_DICTIONARY
        rec = ACOUSTIC_DICTIONARY[term]
        assert rec.descriptor == term
        assert rec.filter_type in {"bell", "high_shelf", "low_shelf", "high_pass", "low_pass", "de_esser"}


def test_analyze_acoustic_descriptors_single_term():
    recs = analyze_acoustic_descriptors("The lead vocal sounds too muddy in the mix.")
    assert len(recs) == 1
    assert recs[0].descriptor == "muddy"
    assert recs[0].target_frequency_hz == 300.0
    assert recs[0].suggested_gain_db == -3.0
    assert recs[0].suggested_q == 1.4
    assert recs[0].filter_type == "bell"


def test_analyze_acoustic_descriptors_multiple_terms():
    query = "Why are my acoustic guitars sounding boxy, harsh, and boomy?"
    recs = analyze_acoustic_descriptors(query)
    descriptors = {r.descriptor for r in recs}
    assert descriptors == {"boxy", "harsh", "boomy"}


def test_analyze_acoustic_descriptors_case_insensitive():
    recs = analyze_acoustic_descriptors("PLEASE FIX THIS SIBILANT VOCAL!")
    assert len(recs) == 1
    assert recs[0].descriptor == "sibilant"
    assert recs[0].target_frequency_hz == 7000.0


def test_build_acoustic_guidance_prompt_empty():
    prompt = build_acoustic_guidance_prompt("How do I freeze a track in Ableton?")
    assert prompt == ""


def test_build_acoustic_guidance_prompt_active():
    prompt = build_acoustic_guidance_prompt("The bass synth sounds boomy and muddy.")
    assert "Acoustic Translation Guidance:" in prompt
    assert "'boomy': Target ~40 Hz" in prompt
    assert "'muddy': Target ~300 Hz" in prompt


def test_build_system_prompt_incorporates_acoustic_guidance():
    sys_prompt = build_system_prompt(
        answer_mode="mix_diagnosis",
        route="production",
        query="The vocal track is sounding harsh and sibilant.",
    )
    assert "Acoustic Translation Guidance:" in sys_prompt
    assert "'harsh': Target ~3500 Hz" in sys_prompt
    assert "'sibilant': Target ~7000 Hz" in sys_prompt
