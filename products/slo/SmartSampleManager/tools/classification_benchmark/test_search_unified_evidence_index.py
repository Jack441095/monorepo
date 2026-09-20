from __future__ import annotations

from search_unified_evidence_index import parse_query, search


def _record(path: str, label: str, family: str, form: str, confidence: float,
            measurements: dict | None = None, duplicate: str = "") -> dict:
    return {
        "record_type": "slo_audio_evidence_record",
        "content_id": "sha256:" + path.encode().hex().ljust(64, "0")[:64],
        "source_path": path,
        "identity": {"value": label, "confidence": confidence},
        "family": {"value": family},
        "form": {"value": form},
        "measurements": {
            name: {"value": value, "unit": "ratio", "method": "test", "valid": True}
            for name, value in (measurements or {}).items()
        },
        "metadata": {
            "aliases": [path],
            "prediction": {"label": label, "confidence": confidence, "action": "review"},
        },
        "duplicate_group": duplicate,
    }


def test_synonym_query_resolves_and_requires_all_terms():
    query = parse_query("BD dark")
    assert query["terms"] == ["kick", "dark"]
    records = [
        _record("/samples/Kick Dark.wav", "Kick", "Kick", "one-shot", .9),
        _record("/samples/Snare Dark.wav", "Snare", "Snare", "one-shot", .9),
    ]
    result = search(records, "BD dark")
    assert result["n_matched"] == 1
    assert result["results"][0]["identity"]["value"] == "Kick"


def test_factor_and_measurement_filters_preserve_unknowns():
    records = [
        _record("/samples/a.wav", "Kick", "Kick", "unknown", .9, {"fundamental_hz": 50}),
        _record("/samples/b.wav", "Drum Loop", "Drum", "loop", .8, {"fundamental_hz": 80}),
    ]
    result = search(records, family="Kick", form="one-shot", min_measurements={"fundamental_hz": 40})
    assert result["n_matched"] == 0
    result = search(records, family="Kick", min_measurements={"fundamental_hz": 40})
    assert result["n_matched"] == 1


def test_duplicate_filter_and_action_are_explicit():
    records = [
        _record("/samples/a.wav", "Kick", "Kick", "one-shot", .9, duplicate="exact:x"),
        _record("/samples/b.wav", "Kick", "Kick", "one-shot", .8),
    ]
    result = search(records, predicted_label="Kick", action="review", duplicate_only=True)
    assert result["n_matched"] == 1
    assert result["safety"]["rename_actions"] is False


def test_limit_and_empty_query_are_deterministic():
    records = [_record(f"/samples/{i}.wav", "Kick", "Kick", "one-shot", i / 10)
               for i in range(5)]
    result = search(records, limit=2)
    assert result["n_input"] == 5
    assert result["n_matched"] == 2
    assert result["results"][0]["identity"]["confidence"] == .4
