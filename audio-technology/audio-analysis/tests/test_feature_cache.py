"""Provenance and isolation tests for the bounded analysis-result cache."""

from __future__ import annotations

from audio_analysis.analysis_core.feature_cache import (
    analysis_cache_key,
    clear_analysis_cache,
    get_or_analyze,
)


def _call(payload: bytes, *, filename: str, goal: str = "premaster", light: bool = False, counter: dict) -> dict:
    return get_or_analyze(
        payload, filename=filename, mix_goal=goal, phon_level=60.0, light=light,
        include_bands=True,
        analyze=lambda: _analyzed(counter),
    )


def _analyzed(counter: dict) -> dict:
    counter["count"] = counter.get("count", 0) + 1
    return {"ok": True, "metrics": {"filename": "original.wav", "value": counter["count"]}}


def test_same_bytes_and_profile_reuse_analysis_but_preserve_callers_filename() -> None:
    clear_analysis_cache()
    counter: dict = {}
    first = _call(b"same audio", filename="first.wav", counter=counter)
    second = _call(b"same audio", filename="second.wav", counter=counter)

    assert counter["count"] == 1
    assert first["analysis_cache"]["hit"] is False
    assert second["analysis_cache"]["hit"] is True
    assert second["metrics"]["filename"] == "second.wav"


def test_profile_or_source_change_invalidates_cache_and_results_are_isolated() -> None:
    clear_analysis_cache()
    counter: dict = {}
    first = _call(b"audio A", filename="a.wav", counter=counter)
    first["metrics"]["value"] = 999
    changed_goal = _call(b"audio A", filename="a.wav", goal="club", counter=counter)
    changed_source = _call(b"audio B", filename="b.wav", counter=counter)
    original_profile_again = _call(b"audio A", filename="a.wav", counter=counter)

    assert counter["count"] == 3
    assert changed_goal["analysis_cache"]["hit"] is False
    assert changed_source["analysis_cache"]["hit"] is False
    assert original_profile_again["analysis_cache"]["hit"] is True
    assert original_profile_again["metrics"]["value"] == 1


def test_key_is_a_sha256_and_contains_all_output_affecting_options() -> None:
    full = analysis_cache_key(b"audio", mix_goal="premaster", phon_level=60.0, light=False, include_bands=True)
    light = analysis_cache_key(b"audio", mix_goal="premaster", phon_level=60.0, light=True, include_bands=True)
    no_bands = analysis_cache_key(b"audio", mix_goal="premaster", phon_level=60.0, light=True, include_bands=False)

    assert full[0].startswith("sha256:")
    assert len(full[0]) == 71
    assert len({full, light, no_bands}) == 3
