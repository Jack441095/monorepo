from data.arrangement_curves import (
    arrangement_role_fx_return_mult,
    arrangement_role_velocity_ride_mult,
)


def test_arrangement_role_fx_return_mult_neutral():
    assert arrangement_role_fx_return_mult("") == 1.0
    assert arrangement_role_fx_return_mult("unknown_section") == 1.0


def test_arrangement_role_fx_return_mult_chorus_wider():
    c = arrangement_role_fx_return_mult("b")
    v = arrangement_role_fx_return_mult("a")
    assert c > v


def test_arrangement_role_fx_return_mult_strength_zero():
    assert arrangement_role_fx_return_mult("b", strength=0.0) == 1.0


def test_arrangement_role_velocity_ride_chorus_louder_than_verse():
    c = arrangement_role_velocity_ride_mult("b")
    v = arrangement_role_velocity_ride_mult("a")
    assert c > v


def test_pre_chorus_last_bar_swell():
    base = arrangement_role_velocity_ride_mult("pre_chorus", pre_chorus_last_bar=False)
    up = arrangement_role_velocity_ride_mult("pre_chorus", pre_chorus_last_bar=True)
    assert up > base


def test_pre_chorus_swell_ignored_outside_pre_chorus():
    a0 = arrangement_role_velocity_ride_mult("a", pre_chorus_last_bar=True)
    a1 = arrangement_role_velocity_ride_mult("a", pre_chorus_last_bar=False)
    assert a0 == a1
