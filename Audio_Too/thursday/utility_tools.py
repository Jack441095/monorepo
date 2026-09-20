"""Siri-style everyday utility tools: calculator, unit conversion, timers,
weather, time/timezone, and date math.

2026-08-07 (Jack: "make her more like Siri"): general-knowledge chat is handled
by widening thursday/brain.py's chat_only prompt, but a small local LLM doing
mental arithmetic is unreliable (live-verified: "what's 47 times 12" got back
a description of the task, not "564"). These are deterministic/offline where
possible (calculator, conversion, timers, date math) so they never depend on
model quality, and isolated to their own module for the same reason
scheduling.py's reminder logic is split from its thin registry handler wrapper.
"""

from __future__ import annotations

import ast
import json
import operator
import re
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from thursday.atomic_io import atomic_write
from thursday.runtime_paths import DATA_DIR

TIMERS_FILE = DATA_DIR / "timers.json"


# ─── Calculator ────────────────────────────────────────────────────────────

# Restricted AST evaluator: only arithmetic on numbers, never arbitrary code
# (unlike a bare eval()). No names, no calls, no subscripts, no attributes.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}

_WORD_OPERATORS = [
    (r"\bplus\b", "+"),
    (r"\bminus\b", "-"),
    (r"\btimes\b", "*"),
    (r"\bmultiplied\s+by\b", "*"),
    (r"\bdivided\s+by\b", "/"),
    (r"\bover\b", "/"),
    (r"\bx\b", "*"),
    (r"\bto\s+the\s+power\s+of\b", "**"),
    (r"\bsquared\b", "**2"),
    (r"\bcubed\b", "**3"),
]


class CalculatorError(ValueError):
    pass


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_ast(node.operand))
    raise CalculatorError("Unsupported expression")


def _normalize_expression(text: str) -> str:
    """Turn natural phrasing ("47 times 12", "10 squared") into a bare
    arithmetic expression a restricted evaluator can parse."""
    expr = text.lower()
    # Strip common leading question phrasing so it doesn't leak into the expr.
    expr = re.sub(r"^(?:what'?s|what is|calculate|compute)\s+", "", expr).strip()
    expr = expr.rstrip("?. ")
    for pattern, replacement in _WORD_OPERATORS:
        expr = re.sub(pattern, replacement, expr)
    # "N percent of M" -> "(N/100)*M"
    expr = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:percent|%)\s+of\s+(\d+(?:\.\d+)?)",
        r"(\1/100)*\2",
        expr,
    )
    m = re.match(r"square\s+root\s+of\s+(\d+(?:\.\d+)?)", expr)
    if m:
        expr = f"{m.group(1)}**0.5"
    return expr


def calculate(text: str) -> tuple[float | None, str | None]:
    """Evaluate an arithmetic expression from natural text.

    Returns (result, error) — exactly one is None.
    """
    expr = _normalize_expression(text)
    if not re.fullmatch(r"[\d\s()+\-*/.%]*", expr) or not re.search(r"\d", expr):
        return None, "I couldn't find a calculation in that."
    try:
        tree = ast.parse(expr, mode="eval")
        result = _eval_ast(tree.body)
    except (SyntaxError, CalculatorError, ZeroDivisionError, TypeError):
        return None, "I couldn't work that out — try something like 'what's 47 times 12'."
    return result, None


def format_calc_result(result: float) -> str:
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"That's {result:,}."


# ─── Unit conversion ────────────────────────────────────────────────────────

# (unit -> base_unit, factor) per dimension. Conversions go unit -> base -> unit.
_LENGTH = {
    "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001, "millimetre": 0.001, "millimetres": 0.001,
    "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01, "centimetre": 0.01, "centimetres": 0.01,
    "m": 1.0, "meter": 1.0, "meters": 1.0, "metre": 1.0, "metres": 1.0,
    "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0, "kilometre": 1000.0, "kilometres": 1000.0,
    "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
    "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
}
_MASS = {
    "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "oz": 28.349523125, "ounce": 28.349523125, "ounces": 28.349523125,
    "lb": 453.59237, "lbs": 453.59237, "pound": 453.59237, "pounds": 453.59237,
    "stone": 6350.29318, "stones": 6350.29318,
}
_VOLUME = {
    "ml": 0.001, "milliliter": 0.001, "milliliters": 0.001, "millilitre": 0.001, "millilitres": 0.001,
    "l": 1.0, "liter": 1.0, "liters": 1.0, "litre": 1.0, "litres": 1.0,
    "gal": 3.785411784, "gallon": 3.785411784, "gallons": 3.785411784,
    "qt": 0.946352946, "quart": 0.946352946, "quarts": 0.946352946,
    "pt": 0.473176473, "pint": 0.473176473, "pints": 0.473176473,
    "cup": 0.2365882365, "cups": 0.2365882365,
    "floz": 0.0295735295625, "fl oz": 0.0295735295625,
}
_TEMPERATURE_UNITS = {
    "c": "c", "celsius": "c", "centigrade": "c",
    "f": "f", "fahrenheit": "f",
    "k": "k", "kelvin": "k",
}
_DIMENSIONS = [_LENGTH, _MASS, _VOLUME]


def _dimension_for(unit: str) -> dict | None:
    for table in _DIMENSIONS:
        if unit in table:
            return table
    return None


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    # Normalize to Celsius first, then to the target.
    if from_unit == "f":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "k":
        celsius = value - 273.15
    else:
        celsius = value
    if to_unit == "f":
        return celsius * 9 / 5 + 32
    if to_unit == "k":
        return celsius + 273.15
    return celsius


def convert_units(value: float, from_unit: str, to_unit: str) -> tuple[float | None, str | None]:
    """Convert value from from_unit to to_unit. Returns (result, error)."""
    from_unit = from_unit.strip().lower().rstrip(".")
    to_unit = to_unit.strip().lower().rstrip(".")

    if from_unit in _TEMPERATURE_UNITS and to_unit in _TEMPERATURE_UNITS:
        return _convert_temperature(value, _TEMPERATURE_UNITS[from_unit], _TEMPERATURE_UNITS[to_unit]), None

    from_table = _dimension_for(from_unit)
    to_table = _dimension_for(to_unit)
    if from_table is None or to_table is None:
        return None, f"I don't know the unit '{from_unit if from_table is None else to_unit}'."
    if from_table is not to_table:
        return None, f"'{from_unit}' and '{to_unit}' aren't the same kind of unit."

    base = value * from_table[from_unit]
    return base / to_table[to_unit], None


_CONVERT_PATTERN = re.compile(
    r"\bconvert\s+(-?\d+(?:\.\d+)?)\s*([a-zA-Z°]+)\s+(?:to|into)\s+([a-zA-Z°]+)\b"
)
_HOW_MANY_PATTERN = re.compile(
    r"\bhow\s+many\s+([a-zA-Z°]+)\s+(?:in|is|are)\s+(-?\d+(?:\.\d+)?)\s*([a-zA-Z°]+)\b"
)
_BARE_CONVERT_PATTERN = re.compile(
    r"\b(-?\d+(?:\.\d+)?)\s*([a-zA-Z°]+)\s+(?:to|in)\s+([a-zA-Z°]+)\b"
)


def parse_conversion_request(text: str) -> tuple[float, str, str] | None:
    """Extract (value, from_unit, to_unit) from natural phrasing, or None."""
    text_lower = text.lower()
    m = _CONVERT_PATTERN.search(text_lower)
    if m:
        return float(m.group(1)), m.group(2), m.group(3)
    m = _HOW_MANY_PATTERN.search(text_lower)
    if m:
        # "how many miles in 5 km" -> value=5, from=km, to=miles
        return float(m.group(2)), m.group(3), m.group(1)
    m = _BARE_CONVERT_PATTERN.search(text_lower)
    if m:
        return float(m.group(1)), m.group(2), m.group(3)
    return None


# ─── Timers ─────────────────────────────────────────────────────────────────


def _load_timers() -> list[dict]:
    if TIMERS_FILE.exists():
        try:
            return json.loads(TIMERS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_timers(timers: list[dict]) -> None:
    try:
        atomic_write(TIMERS_FILE, json.dumps(timers, indent=2))
    except OSError:
        pass


_DURATION_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(hour|hr|minute|min|second|sec)s?\b"
)


def parse_duration_seconds(text: str) -> float | None:
    """Sum every "N minutes"/"N hours"/"N seconds" phrase found in text."""
    total = 0.0
    found = False
    for value, unit in _DURATION_PATTERN.findall(text.lower()):
        found = True
        seconds_per_unit = {"hour": 3600, "hr": 3600, "minute": 60, "min": 60, "second": 1, "sec": 1}[unit]
        total += float(value) * seconds_per_unit
    return total if found else None


def start_timer(text: str, label: str = "") -> tuple[dict | None, str | None]:
    seconds = parse_duration_seconds(text)
    if not seconds:
        return None, "How long should the timer be? Try 'set a timer for 10 minutes'."
    timer = {
        "id": str(uuid.uuid4())[:8],
        "label": label or "Timer",
        "created_at": time.time(),
        "duration_seconds": seconds,
        "ends_at": time.time() + seconds,
        "cancelled": False,
    }
    timers = _load_timers()
    timers.append(timer)
    _save_timers(timers)
    return timer, None


def _active_timers() -> list[dict]:
    return [t for t in _load_timers() if not t.get("cancelled")]


def list_timers() -> list[dict]:
    """Active (non-cancelled) timers, each annotated with remaining_seconds."""
    now = time.time()
    result = []
    for t in _active_timers():
        remaining = t["ends_at"] - now
        result.append({**t, "remaining_seconds": remaining, "done": remaining <= 0})
    return result


def cancel_timer(timer_id: str = "") -> str:
    timers = _load_timers()
    active = [t for t in timers if not t.get("cancelled")]
    if not active:
        return "No active timers to cancel."
    target = None
    if timer_id:
        target = next((t for t in active if t["id"].startswith(timer_id)), None)
        if target is None:
            return f"No active timer matching '{timer_id}'."
    else:
        target = max(active, key=lambda t: t["created_at"])
    target["cancelled"] = True
    _save_timers(timers)
    return f"Cancelled: {target.get('label', 'Timer')} ({target['id']})."


def format_duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


# ─── Weather (Open-Meteo — free, no API key required) ──────────────────────

_WEATHER_CODES = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "light freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "light snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}


class WeatherError(RuntimeError):
    pass


def _geocode(location: str) -> tuple[float, float, str]:
    import httpx

    resp = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1},
        timeout=8.0,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        raise WeatherError(f"I couldn't find a place called '{location}'.")
    r = results[0]
    display = r.get("name", location)
    if r.get("admin1"):
        display += f", {r['admin1']}"
    if r.get("country"):
        display += f", {r['country']}"
    return r["latitude"], r["longitude"], display


def get_weather(location: str) -> dict:
    """Fetch current conditions for a place name via Open-Meteo (no API key).

    Returns a dict with ok/error, or ok/location/temperature_c/condition/wind_kph.
    Raises no exceptions -- network/parse failures come back as {"ok": False, "error": ...}.
    """
    import httpx

    try:
        lat, lon, display = _geocode(location)
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=8.0,
        )
        resp.raise_for_status()
        current = resp.json().get("current") or {}
        code = current.get("weather_code")
        return {
            "ok": True,
            "location": display,
            "temperature_c": current.get("temperature_2m"),
            "wind_kph": current.get("wind_speed_10m"),
            "condition": _WEATHER_CODES.get(code, "unknown conditions"),
        }
    except WeatherError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Weather lookup failed: {e}"}


def extract_location(text: str) -> str:
    """Pull a place name out of "weather in X" / "weather for X" phrasing."""
    m = re.search(r"\bweather\s+(?:in|for|at)\s+(.+?)[\?\.!]*$", text.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"\bin\s+(.+?)[\?\.!]*$", text.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


# ─── Time / timezone ─────────────────────────────────────────────────────────


def get_current_time(location: str = "") -> tuple[str | None, str | None]:
    """Current time, local or for a named place (via Open-Meteo's timezone
    lookup, reusing the same free geocoding call weather already uses).

    Returns (formatted_string, error) — exactly one is None.
    """
    if not location:
        now = datetime.now()
        return now.strftime("%A, %B %d — %I:%M %p").replace(" 0", " "), None

    try:
        import httpx

        lat, lon, display = _geocode(location)
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current": "temperature_2m", "timezone": "auto"},
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()
        tz_name = data.get("timezone")
        if not tz_name:
            return None, f"Couldn't determine the timezone for {display}."
        now = datetime.now(ZoneInfo(tz_name))
        formatted = now.strftime("%A, %B %d — %I:%M %p").replace(" 0", " ")
        return f"{formatted} in {display} ({tz_name})", None
    except WeatherError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Time lookup failed: {e}"


def extract_time_location(text: str) -> str:
    """Pull a place name out of "what time is it in X" phrasing."""
    m = re.search(r"\btime\s+(?:is\s+it\s+)?(?:in|at|for)\s+(.+?)[\?\.!]*$", text.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


# ─── Date math ────────────────────────────────────────────────────────────────

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def answer_date_query(text: str) -> str | None:
    """Answer "what day is it in N days", "what's the date", "how many days
    until <weekday>". Returns None if the text doesn't match a date question
    (caller should treat that as "not handled")."""
    text_lower = text.lower().strip()
    today = datetime.now().date()

    if re.search(r"\bwhat(?:'s|s|\s+is)\s+(?:the\s+)?date\b", text_lower) or re.fullmatch(
        r"what day is it[\?\.!]*", text_lower
    ):
        return f"Today is {today.strftime('%A, %B %d, %Y')}."

    m = re.search(r"\bin\s+(\d+)\s*(day|week|month)s?\b", text_lower)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "day":
            target = today + timedelta(days=n)
        elif unit == "week":
            target = today + timedelta(weeks=n)
        else:  # month — calendar-aware, not just 30 days
            month_index = today.month - 1 + n
            year = today.year + month_index // 12
            month = month_index % 12 + 1
            day = min(today.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                                   31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
            target = today.replace(year=year, month=month, day=day)
        return f"That'll be {target.strftime('%A, %B %d, %Y')}."

    m = re.search(r"\bhow\s+many\s+days\s+(?:until|till|to)\s+(\w+)\b", text_lower)
    if m:
        target_word = m.group(1)
        if target_word in _WEEKDAYS:
            target_idx = _WEEKDAYS.index(target_word)
            days_ahead = (target_idx - today.weekday()) % 7
            days_ahead = days_ahead or 7  # "until monday" said on a monday means next monday
            target = today + timedelta(days=days_ahead)
            return f"{days_ahead} day{'s' if days_ahead != 1 else ''} — that's {target.strftime('%A, %B %d')}."
        return None

    return None
