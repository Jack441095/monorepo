from __future__ import annotations

from kenn.core.mixdown_coach import build_mixdown_coach
from scripts.evaluate_mixdown_coach import CASES, evaluate_case


def test_reference_coach_prioritises_level_matching_then_low_mid_listening() -> None:
    coach = build_mixdown_coach({
        "reference_comparison": {
            "lufs_delta_db": 2.4,
            "comparison_basis": "40-band LTAS normalised around 1 kHz.",
            "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
            "ltas_40_band_deltas": [
                {"center_hz": 300.0, "delta_db": 5.0},
                {"center_hz": 340.0, "delta_db": 4.5},
                {"center_hz": 7000.0, "delta_db": -2.0},
            ],
        }
    })

    assert coach["status"] == "ready"
    assert coach["listening_checks"][0]["kind"] == "level_match"
    low_mid = next(check for check in coach["listening_checks"] if check["kind"] == "reference_ltas")
    assert low_mid["frequency_hz"] == 300.0
    assert "low-mid masking" in low_mid["action"]
    assert len(coach["listening_checks"]) <= 5
    assert coach["live_target_inference_allowed"] is False
    assert "pink-noise" in coach["limitations"][0]


def test_reference_coach_abstains_without_measured_tonal_difference() -> None:
    coach = build_mixdown_coach({"reference_comparison": {"largest_ltas_difference": {"center_hz": 300, "delta_db": 0.4}}})

    assert coach["status"] == "abstain"
    assert coach["listening_checks"] == []


def test_reference_coach_surfaces_pink_noise_shape_as_advisory() -> None:
    coach = build_mixdown_coach({
        "reference_comparison": {
            "pink_noise_reference": {
                "status": "complete",
                "curve": "-3 dB per octave pink-noise-style spectral baseline",
                "largest_deviation": {
                    "center_hz": 296.0,
                    "deviation_db": 5.1,
                },
            },
        },
    })

    assert coach["status"] == "ready"
    check = coach["listening_checks"][0]
    assert check["kind"] == "pink_noise_shape"
    assert check["frequency_hz"] == 296.0
    assert check["deviation_db"] == 5.1
    assert check["advisory_only"] is True
    assert "not a reason to EQ the master automatically" in check["action"]


def test_sealed_mixdown_coach_evaluation_cases_pass() -> None:
    rows = [evaluate_case(case) for case in CASES]

    assert len(rows) == 5
    assert all(row["passed"] for row in rows)
