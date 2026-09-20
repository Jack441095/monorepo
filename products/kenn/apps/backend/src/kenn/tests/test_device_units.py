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

