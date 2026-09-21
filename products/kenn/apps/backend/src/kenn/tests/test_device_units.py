from pytest import approx

from kenn.core.device_units import display_to_raw, find_profile


def test_auto_filter_resonance_percent_mapping_is_evidence_backed() -> None:
    assert find_profile("Auto Filter", "Resonance", "%") is not None
    raw, error = display_to_raw(
        device_name="Auto Filter",
        parameter_name="Resonance",
        value=25.0,
        unit="percent",
    )
    assert error is None
    assert raw == approx(0.25)


def test_drum_buss_relative_percent_mapping_is_evidence_backed() -> None:
    raw, error = display_to_raw(
        device_name="Drum Buss",
        parameter_name="Drive",
        value=5.0,
        unit="%",
        relative=True,
    )
    assert error is None
    assert raw == approx(0.05)


def test_glue_attack_ms_mapping_uses_verified_discrete_steps() -> None:
    raw, error = display_to_raw(
        device_name="Glue Compressor",
        parameter_name="Attack",
        value=3.0,
        unit="ms",
    )
    assert error is None
    assert raw == approx(4.0)


def test_glue_ratio_mapping_uses_verified_discrete_steps() -> None:
    raw, error = display_to_raw(
        device_name="Glue Compressor",
        parameter_name="Ratio",
        value=4.0,
        unit=":1",
    )
    assert error is None
    assert raw == approx(1.0)


def test_glue_discrete_display_mapping_rejects_interpolated_values() -> None:
    raw, error = display_to_raw(
        device_name="Glue Compressor",
        parameter_name="Attack",
        value=2.0,
        unit="ms",
    )
    assert raw is None
    assert "verified steps" in str(error)


def test_unqualified_display_unit_stays_unmapped() -> None:
    raw, error = display_to_raw(
        device_name="Reverb",
        parameter_name="Decay Time",
        value=1.0,
        unit="ms",
    )
    assert raw is None
    assert error is not None


def test_roar_drive_db_and_drywet_mapping() -> None:
    assert find_profile("Roar", "Drive", "dB") is not None
    raw, error = display_to_raw(
        device_name="Roar",
        parameter_name="Drive",
        value=12.0,
        unit="dB",
    )
    assert error is None
    assert raw == approx(0.25)

    raw_dw, error_dw = display_to_raw(
        device_name="Roar",
        parameter_name="Dry/Wet",
        value=50.0,
        unit="%",
    )
    assert error_dw is None
    assert raw_dw == approx(0.50)


def test_compressor_threshold_table_matches_measured_live_points() -> None:
    assert find_profile("Compressor", "Threshold", "dB") is not None
    raw, error = display_to_raw(
        device_name="Compressor", parameter_name="Threshold",
        value=-18.0, unit="dB",
    )
    assert error is None
    assert raw == approx(0.4, abs=1e-9)
    raw_mid, error_mid = display_to_raw(
        device_name="Compressor", parameter_name="Threshold",
        value=-17.0, unit="decibels",
    )
    assert error_mid is None
    assert 0.4 < raw_mid < 0.45


def test_compressor_threshold_rejects_values_outside_measured_table() -> None:
    raw, error = display_to_raw(
        device_name="Compressor", parameter_name="Threshold",
        value=-70.0, unit="dB",
    )
    assert raw is None
    assert "outside the qualified range" in (error or "")


def test_auto_filter_frequency_log_mapping_matches_measured_live_points() -> None:
    assert find_profile("Auto Filter", "Frequency", "hz") is not None
    raw, error = display_to_raw(
        device_name="Auto Filter", parameter_name="Frequency",
        value=1000.0, unit="Hz",
    )
    assert error is None
    assert raw == approx(0.5663233347786729, rel=1e-6)
    raw_edge, error_edge = display_to_raw(
        device_name="Auto Filter", parameter_name="Frequency",
        value=20.0, unit="hertz",
    )
    assert error_edge is None
    assert raw_edge == approx(0.0, abs=1e-9)


def test_auto_filter_frequency_rejects_subsonic_requests() -> None:
    raw, error = display_to_raw(
        device_name="Auto Filter", parameter_name="Frequency",
        value=5.0, unit="hz",
    )
    assert raw is None
    assert "outside the qualified range" in (error or "")


def test_saturator_drive_db_mapping_is_linear_and_measured() -> None:
    assert find_profile("Saturator", "Drive", "dB") is not None
    raw, error = display_to_raw(
        device_name="Saturator", parameter_name="Drive",
        value=4.0, unit="dB",
    )
    assert error is None
    assert raw == approx(0.5555555555555556, rel=1e-9)
