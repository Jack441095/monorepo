import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("filter_definition_cards.py")
SPEC = importlib.util.spec_from_file_location("filter_definition_cards", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_filters_native_card_and_preserves_unknowns():
    payload = {"cards": [
        {"path": "/a.wav", "source": {"analysis_duration_seconds": 2.0},
         "temporal": {"form_hint": "possibly_loop", "onset_density_per_second": 4.0},
         "spectrum": {"low_band_energy_ratio": 0.7}, "heuristic_tags": ["dark"]},
        {"path": "/b.wav", "source": {}, "temporal": {}, "spectrum": {}},
    ]}
    result = MODULE.filter_records(payload, {"form": "possibly_loop", "min_low_band": 0.5})
    assert result["n_input"] == 2
    assert result["n_matched"] == 1
    assert result["results"][0]["path"] == "/a.wav"
    assert result["safety"]["unknown_values_filled"] is False


def test_filters_review_collections_by_action_and_flattened_facet():
    payload = {"collections": {"suggest": [{
        "path": "/s.wav", "review_evidence": {"facets": {
            "form_hint": "possibly_one_shot", "duration_seconds": 0.5,
            "heuristic_tags": ["transient_dense"],
        }},
    }]}}
    result = MODULE.filter_records(payload, {"action": "suggest", "tag": "transient_dense", "max_duration": 1.0})
    assert result["n_matched"] == 1


def test_missing_numeric_facet_does_not_match():
    result = MODULE.filter_records({"cards": [{"path": "/x.wav"}]}, {"min_pitch": 100.0})
    assert result["n_matched"] == 0
