from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("label_free_domain_router.py")
SPEC = importlib.util.spec_from_file_location("label_free_domain_router", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_domain_bank_covers_open_world_routes():
    assert {"music_sample", "speech_voice", "environment_sfx", "animal_bioacoustic",
            "mechanical_industrial", "ambience_field", "unknown_or_mixture"} <= set(MODULE.DOMAIN_PROMPTS)
    assert all(isinstance(prompts, list) and prompts for prompts in MODULE.DOMAIN_PROMPTS.values())


def test_domain_row_is_explicitly_a_route_not_a_label():
    class FakeRunner:
        @staticmethod
        def _row(*args, **kwargs):
            return {
                "path": str(args[0]), "semantic_label": None,
                "zero_shot_suggestion": "speech_voice", "alternatives": [],
                "semantic_score": 0.4, "margin": 0.1, "status": "review",
            }
    row = MODULE._row(Path("/tmp/example.wav"), ["speech_voice"], np.array([0.4]),
                      1, 0.15, 0.03, None, 0.67, runner_module=FakeRunner())
    assert row["domain_suggestion"] == "speech_voice"
    assert row["domain_score"] == 0.4
    assert row["domain_margin"] == 0.1
    assert row["semantic_label"] is None
    assert row["calibration"] == "uncalibrated_domain_prompt_similarity"


def test_custom_prompt_bank_is_loaded_and_trimmed(tmp_path: Path):
    prompts = tmp_path / "domain_prompts.json"
    prompts.write_text(json.dumps({"music_sample": [" a producer drum hit ", "sample"]}),
                       encoding="utf-8")
    assert MODULE._prompt_bank(prompts) == {
        "music_sample": ["a producer drum hit", "sample"]
    }


def test_custom_prompt_bank_rejects_empty_domain(tmp_path: Path):
    prompts = tmp_path / "bad.json"
    prompts.write_text(json.dumps({"music_sample": []}), encoding="utf-8")
    try:
        MODULE._prompt_bank(prompts)
    except ValueError as exc:
        assert "prompt list" in str(exc)
    else:
        raise AssertionError("empty custom prompt bank was accepted")
