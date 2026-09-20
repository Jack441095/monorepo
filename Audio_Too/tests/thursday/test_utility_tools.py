"""Tests for the Siri-style utility tools: calculator, unit conversion,
timers, weather — and their intent classification + service wiring."""

from __future__ import annotations

import pytest

from thursday.intent import classify_intent
from thursday.registry.handlers import (
    _handle_calculator,
    _handle_current_time,
    _handle_date_query,
    _handle_set_default_location,
    _handle_timer,
    _handle_unit_conversion,
    _handle_weather,
)
from thursday.utility_tools import (
    answer_date_query,
    calculate,
    cancel_timer,
    convert_units,
    extract_time_location,
    format_calc_result,
    format_duration,
    get_current_time,
    get_weather,
    list_timers,
    parse_conversion_request,
    parse_duration_seconds,
    start_timer,
)


# ─── Calculator ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what's 47 times 12", 564),
        ("calculate 100 divided by 4", 25),
        ("15 percent of 200", 30),
        ("square root of 144", 12),
        ("10 squared", 100),
        ("100 minus 37", 63),
    ],
)
def test_calculate_arithmetic(text: str, expected: float) -> None:
    result, error = calculate(text)
    assert error is None
    assert result == expected


def test_calculate_rejects_non_arithmetic() -> None:
    result, error = calculate("what's the meaning of life")
    assert result is None
    assert error is not None


def test_calculate_rejects_division_by_zero() -> None:
    result, error = calculate("10 divided by 0")
    assert result is None
    assert error is not None


def test_calculate_cannot_execute_arbitrary_code() -> None:
    # The restricted AST evaluator must reject anything beyond number/BinOp/
    # UnaryOp — no names, calls, attributes, or subscripts.
    result, error = calculate("__import__('os').system('echo hi')")
    assert result is None
    assert error is not None


def test_format_calc_result_int_vs_float() -> None:
    assert format_calc_result(25.0) == "That's 25."
    assert format_calc_result(3.5) == "That's 3.5."


def test_handle_calculator_end_to_end() -> None:
    assert _handle_calculator("what's 47 times 12") == "That's 564."


# ─── Unit conversion ────────────────────────────────────────────────────────


def test_parse_conversion_request_variants() -> None:
    assert parse_conversion_request("convert 5 km to miles") == (5.0, "km", "miles")
    assert parse_conversion_request("how many miles in 5 km") == (5.0, "km", "miles")
    assert parse_conversion_request("30 celsius to fahrenheit") == (30.0, "celsius", "fahrenheit")


@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        (5, "km", "miles", pytest.approx(3.1069, abs=1e-3)),
        (10, "lbs", "kg", pytest.approx(4.5359, abs=1e-3)),
        (0, "celsius", "fahrenheit", 32),
        (100, "celsius", "fahrenheit", 212),
        (1, "gallon", "liters", pytest.approx(3.7854, abs=1e-3)),
    ],
)
def test_convert_units(value, from_unit, to_unit, expected) -> None:
    result, error = convert_units(value, from_unit, to_unit)
    assert error is None
    assert result == expected


def test_convert_units_rejects_mismatched_dimensions() -> None:
    result, error = convert_units(5, "km", "kg")
    assert result is None
    assert "same kind of unit" in error


def test_convert_units_rejects_unknown_unit() -> None:
    result, error = convert_units(5, "smoots", "km")
    assert result is None
    assert "smoots" in error


def test_handle_unit_conversion_end_to_end() -> None:
    assert _handle_unit_conversion("convert 5 km to miles") == "5 km is 3.1069 miles."


def test_handle_unit_conversion_no_match() -> None:
    result = _handle_unit_conversion("convert this project to a template")
    assert "convert" in result.lower()


# ─── Timers ─────────────────────────────────────────────────────────────────


def test_parse_duration_seconds() -> None:
    assert parse_duration_seconds("set a timer for 10 minutes") == 600.0
    assert parse_duration_seconds("timer for 1 hour and 30 minutes") == 5400.0
    assert parse_duration_seconds("90 seconds") == 90.0
    assert parse_duration_seconds("set a timer") is None


def test_format_duration() -> None:
    assert format_duration(90) == "1m 30s"
    assert format_duration(3661) == "1h 1m 1s"
    assert format_duration(0) == "0s"


def test_start_check_cancel_timer_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("thursday.utility_tools.TIMERS_FILE", tmp_path / "timers.json")

    timer, error = start_timer("set a timer for 10 minutes")
    assert error is None
    assert timer["duration_seconds"] == 600.0

    active = list_timers()
    assert len(active) == 1
    assert active[0]["id"] == timer["id"]
    assert not active[0]["done"]

    msg = cancel_timer(timer["id"])
    assert "Cancelled" in msg
    assert list_timers() == []


def test_cancel_timer_no_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("thursday.utility_tools.TIMERS_FILE", tmp_path / "timers.json")
    assert "No active timers" in cancel_timer()


def test_handle_timer_end_to_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("thursday.utility_tools.TIMERS_FILE", tmp_path / "timers.json")

    set_msg = _handle_timer("set a timer for 5 minutes")
    assert "Timer set for 5m" in set_msg

    check_msg = _handle_timer("how much time is left")
    assert "5m left" in check_msg

    cancel_msg = _handle_timer("cancel my timer")
    assert "Cancelled" in cancel_msg

    empty_msg = _handle_timer("how much time is left")
    assert "No active timers" in empty_msg


# ─── Weather ────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def test_get_weather_success(monkeypatch) -> None:
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if "geocoding" in url:
            return _FakeResponse({
                "results": [{"name": "London", "admin1": "England", "country": "United Kingdom",
                             "latitude": 51.5, "longitude": -0.12}]
            })
        return _FakeResponse({
            "current": {"temperature_2m": 18.0, "weather_code": 0, "wind_speed_10m": 5.0}
        })

    monkeypatch.setattr("httpx.get", fake_get)

    result = get_weather("London")
    assert result["ok"] is True
    assert result["location"] == "London, England, United Kingdom"
    assert result["temperature_c"] == 18.0
    assert result["condition"] == "clear sky"
    assert len(calls) == 2


def test_get_weather_unknown_location(monkeypatch) -> None:
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse({"results": []})

    monkeypatch.setattr("httpx.get", fake_get)

    result = get_weather("Nowhereville")
    assert result["ok"] is False
    assert "Nowhereville" in result["error"]


def test_get_weather_network_failure(monkeypatch) -> None:
    def fake_get(url, params=None, timeout=None):
        raise ConnectionError("no network")

    monkeypatch.setattr("httpx.get", fake_get)

    result = get_weather("London")
    assert result["ok"] is False
    assert "error" in result


def test_handle_weather_no_location() -> None:
    result = _handle_weather("what's the weather")
    assert "Which location" in result


def test_handle_weather_end_to_end(monkeypatch) -> None:
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _FakeResponse({
                "results": [{"name": "Tokyo", "admin1": "Tokyo", "country": "Japan",
                             "latitude": 35.6, "longitude": 139.7}]
            })
        return _FakeResponse({
            "current": {"temperature_2m": 28.0, "weather_code": 61, "wind_speed_10m": 6.0}
        })

    monkeypatch.setattr("httpx.get", fake_get)

    result = _handle_weather("is it raining in tokyo")
    assert "Tokyo" in result
    assert "light rain" in result


# ─── Intent classification ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        ("what's 47 times 12", "calculator"),
        ("calculate 15% of 200", "calculator"),
        ("square root of 144", "calculator"),
        ("convert 5 km to miles", "unit_conversion"),
        ("how many miles in 5 km", "unit_conversion"),
        ("set a timer for 10 minutes", "timer"),
        ("how much time is left", "timer"),
        ("cancel my timer", "timer"),
        ("what's the weather in london", "weather"),
        ("is it raining", "weather"),
        ("what's the forecast for tomorrow", "weather"),
    ],
)
def test_utility_intents_classify_correctly(text: str, expected_intent: str) -> None:
    assert classify_intent(text).name == expected_intent


# ─── Dummy-it pronoun-resolution regression ────────────────────────────────


def test_dummy_it_not_resolved_to_context_entity() -> None:
    from thursday.resolver import resolve_request

    context = {"current_client": "Jordan"}
    for text in ("is it working", "is it raining", "is it done", "is it possible to bounce stems"):
        resolved, _ = resolve_request(text, context)
        assert resolved == text, f"{text!r} should not have 'it' resolved to a context entity"


def test_real_it_referent_still_resolves() -> None:
    from thursday.resolver import resolve_request

    context = {"current_client": "Jordan"}
    resolved, entities = resolve_request("tell him about it", context)
    assert resolved == "tell Jordan about Jordan"
    assert entities["current_client"] == "Jordan"


# ─── Time / timezone ─────────────────────────────────────────────────────────


def test_get_current_time_local() -> None:
    formatted, error = get_current_time()
    assert error is None
    assert "," in formatted  # weekday, month day -- time


def test_get_current_time_for_location(monkeypatch) -> None:
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _FakeResponse({
                "results": [{"name": "Tokyo", "admin1": "Tokyo", "country": "Japan",
                             "latitude": 35.6, "longitude": 139.7}]
            })
        return _FakeResponse({"timezone": "Asia/Tokyo", "current": {"temperature_2m": 20.0}})

    monkeypatch.setattr("httpx.get", fake_get)

    formatted, error = get_current_time("Tokyo")
    assert error is None
    assert "Tokyo" in formatted
    assert "Asia/Tokyo" in formatted


def test_get_current_time_unknown_location(monkeypatch) -> None:
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse({"results": []})

    monkeypatch.setattr("httpx.get", fake_get)

    formatted, error = get_current_time("Nowhereville")
    assert formatted is None
    assert "Nowhereville" in error


def test_extract_time_location() -> None:
    assert extract_time_location("what time is it in Tokyo") == "Tokyo"
    assert extract_time_location("what time is it") == ""


def test_handle_current_time_end_to_end() -> None:
    result = _handle_current_time("what time is it")
    assert result and "error" not in result.lower()


# ─── Date math ────────────────────────────────────────────────────────────────


def test_answer_date_query_today() -> None:
    result = answer_date_query("what's the date")
    assert result is not None and "Today is" in result


def test_answer_date_query_in_n_days() -> None:
    from datetime import datetime, timedelta

    result = answer_date_query("what day is it in 10 days")
    expected = (datetime.now().date() + timedelta(days=10)).strftime("%A, %B %d, %Y")
    assert result == f"That'll be {expected}."


def test_answer_date_query_days_until_weekday() -> None:
    result = answer_date_query("how many days until friday")
    assert result is not None
    assert "day" in result


def test_answer_date_query_unrecognized_returns_none() -> None:
    assert answer_date_query("how do I sidechain the bass") is None


def test_handle_date_query_end_to_end() -> None:
    assert "Today is" in _handle_date_query("what's the date")


# ─── Default location ───────────────────────────────────────────────────────


def test_handle_set_default_location() -> None:
    result = _handle_set_default_location("my location is Nashville")
    assert "Nashville" in result

    from thursday.user_profile import get_preference
    assert get_preference("default_location") == "Nashville"


def test_handle_weather_uses_default_location_when_unset_in_query(monkeypatch) -> None:
    from thursday.user_profile import update_preference

    update_preference("default_location", "Berlin")

    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _FakeResponse({
                "results": [{"name": "Berlin", "admin1": "", "country": "Germany",
                             "latitude": 52.5, "longitude": 13.4}]
            })
        return _FakeResponse({
            "current": {"temperature_2m": 15.0, "weather_code": 3, "wind_speed_10m": 4.0}
        })

    monkeypatch.setattr("httpx.get", fake_get)

    result = _handle_weather("what's the weather")
    assert "Berlin" in result


def test_handle_weather_no_location_and_no_default() -> None:
    from thursday.user_profile import update_preference
    update_preference("default_location", "")

    result = _handle_weather("what's the weather")
    assert "Which location" in result


# ─── Intent classification (time/date/location) ─────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        ("what time is it", "current_time"),
        ("what time is it in Tokyo", "current_time"),
        ("what's the date", "date_query"),
        ("what day is it in 10 days", "date_query"),
        ("how many days until friday", "date_query"),
        ("my location is London", "set_default_location"),
        ("set my location to London", "set_default_location"),
    ],
)
def test_time_date_location_intents_classify_correctly(text: str, expected_intent: str) -> None:
    assert classify_intent(text).name == expected_intent


def test_ambiguous_im_in_phrasing_does_not_misroute_to_location(monkeypatch) -> None:
    # Regression: "i'm in X"/"i am in X" was tried as a set_default_location
    # trigger and dropped -- it matched ordinary sentences having nothing to
    # do with location ("i'm in the middle of a mix, can you wait").
    assert classify_intent("i'm in the middle of a mix, can you wait").name != "set_default_location"
    assert classify_intent("i am in the studio right now").name != "set_default_location"
