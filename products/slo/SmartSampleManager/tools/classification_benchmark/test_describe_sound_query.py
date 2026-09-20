import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("describe_sound_query.py")
SPEC = importlib.util.spec_from_file_location("describe_sound_query", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_parser_resolves_known_terms_and_preserves_unknowns():
    query = MODULE.parse_query("dark transient percussion loop spaceship")
    assert query["filters"] == {"max_centroid": 2500.0, "tag": "transient_dense", "form": "possibly_loop"}
    assert "spaceship" in query["unmatched_terms"]
    assert "dark" in query["resolved_terms"]


def test_search_never_turns_text_into_a_label():
    payload = {"collections": {"suggest": [{
        "path": "/p.wav", "predicted_class": "Percussion Loop",
        "review_evidence": {"facets": {
            "form_hint": "possibly_loop", "spectral_centroid_hz": 1800,
            "heuristic_tags": ["transient_dense"],
        }},
    }]}}
    result = MODULE.search(payload, "dark transient percussion loop invented", limit=10)
    assert result["n_matched"] == 1
    assert result["safety"]["text_created_labels"] is False
    assert "invented" in result["query"]["unmatched_terms"]
