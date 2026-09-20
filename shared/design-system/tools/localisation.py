"""NITE DSP localisation runtime foundation (DS-I08 / DS-I09).

Implements the frozen LOCALISATION_ARCHITECTURE_V1 principles:
  - stable language-neutral keys (never displayed English text as ID)
  - fallback locale resolution with missing-key diagnostics
  - runtime locale change notification
  - thread-safe reads, no UI blocking assumptions
  - ICU-style plural/interpolation hooks ({count, plural, ...} minimal support)
  - locale-aware formatting preserving technical units (Hz/kHz/dB/LUFS/ms/BPM)

No SLO/KENN UI strings are migrated here; this is the reusable layer only.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Callable

FALLBACK_LOCALE = "en"

_PLURAL_RE = re.compile(
    r"\{(\w+),\s*plural,\s*(.*?)\}\s*$", re.DOTALL
)
_SELECT_CASE_RE = re.compile(r"(\w+)\s*\{([^{}]*)\}")
_INTERP_RE = re.compile(r"\{(\w+)\}")


class MissingKeyError(KeyError):
    """Raised/diagnosed when a key is absent from locale AND fallback."""

    def __init__(self, key: str, locale: str):
        self.key = key
        self.locale = locale
        super().__init__(f"missing resource key '{key}' for locale '{locale}' (and fallback)")


def _flatten(obj: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for k, v in obj.items():
        name = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten(v, name))
        else:
            flat[name] = str(v)
    return flat


def load_bundle(path: str | Path) -> dict[str, str]:
    """Load a resource bundle into a flat key->string map."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    meta = data.pop("$meta", {})
    flat = _flatten(data)
    # English base bundle must never be empty — it IS the contract.
    if meta.get("isFallbackLocale") and not flat:
        raise ValueError(f"fallback bundle {path} is empty")
    return flat


def format_plural(pattern: str, params: dict) -> str:
    """Minimal ICU-style plural: '{count, plural, one {# sample} other {# samples}}'."""
    m = _PLURAL_RE.search(pattern)
    if not m:
        return _interpolate(pattern, params)
    var, body = m.group(1), m.group(2)
    count = params.get(var, 0)
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 0
    cases = dict(_SELECT_CASE_RE.findall(body))
    if n == 1 and "one" in cases:
        chosen = cases["one"]
    elif "other" in cases:
        chosen = cases["other"]
    else:
        chosen = next(iter(cases.values()), "")
    chosen = chosen.replace("#", str(n)).strip()
    return _interpolate(chosen, params)


def _interpolate(text: str, params: dict) -> str:
    def repl(m: re.Match) -> str:
        return str(params.get(m.group(1), m.group(0)))

    return _INTERP_RE.sub(repl, text)


class LocalisationManager:
    """Thread-safe runtime localisation with fallback + change notification.

    Usage:
        loc = LocalisationManager(Path("localisation"))
        loc.get("action.play")                      -> "Play"
        loc.set_locale("de")                        -> notifies subscribers
        loc.format("common.results.count", count=3) -> "3 samples"
    """

    def __init__(self, bundles_dir: str | Path, fallback_locale: str = FALLBACK_LOCALE):
        self._dir = Path(bundles_dir)
        self._fallback_locale = fallback_locale
        self._lock = threading.RLock()
        self._bundles: dict[str, dict[str, str]] = {}
        self._current = fallback_locale
        self._listeners: list[Callable[[str], None]] = []
        self._missing_diagnostics: list[tuple[str, str]] = []
        self.load_locale(fallback_locale)

    # -- loading ---------------------------------------------------------------

    def load_locale(self, locale: str) -> None:
        path = self._dir / f"strings_{locale}.json"
        bundle = load_bundle(path) if path.exists() else {}
        with self._lock:
            self._bundles[locale] = bundle

    def available_locales(self) -> list[str]:
        return sorted(p.stem.replace("strings_", "") for p in self._dir.glob("strings_*.json"))

    # -- lookup ------------------------------------------------------------------

    @property
    def current_locale(self) -> str:
        with self._lock:
            return self._current

    @property
    def fallback_locale(self) -> str:
        return self._fallback_locale

    def get(self, key: str, locale: str | None = None) -> str:
        """Resolve a stable key. Falls back to the fallback locale; records diagnostics."""
        with self._lock:
            loc = locale or self._current
            bundle = self._bundles.get(loc, {})
            if key in bundle:
                return bundle[key]
            fb = self._bundles.get(self._fallback_locale, {})
            if key in fb:
                self._missing_diagnostics.append((loc, key))
                return fb[key]
            # Key absent everywhere: record diagnostic before raising so callers
            # that catch MissingKeyError still get a diagnostics trail.
            self._missing_diagnostics.append((loc, key))
            raise MissingKeyError(key, loc)

    def try_get(self, key: str, default: str = "") -> str:
        try:
            return self.get(key)
        except MissingKeyError:
            self._missing_diagnostics.append((self.current_locale, key))
            return default

    def missing_key_report(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._missing_diagnostics)

    # -- runtime switching ---------------------------------------------------------

    def set_locale(self, locale: str) -> bool:
        """Switch locale at runtime. Returns True if a known bundle was switched to.

        Callers (UI layers) subscribe via on_locale_changed to run their re-layout
        pass (LOCALISATION_ARCHITECTURE risk R4).
        """
        with self._lock:
            if locale not in self._bundles:
                path = self._dir / f"strings_{locale}.json"
                if not path.exists():
                    return False
                self._bundles[locale] = load_bundle(path)
            if locale == self._current:
                return True
            self._current = locale
        self._notify(locale)
        return True

    def on_locale_changed(self, listener: Callable[[str], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def _notify(self, locale: str) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            fn(locale)

    # -- formatting ---------------------------------------------------------------

    def format(self, key: str, **params) -> str:
        raw = self.get(key)
        if "plural" in raw:
            return format_plural(raw, params)
        return _interpolate(raw, params)


# ---------------------------------------------------------------------------------
# Locale formatters (task §19). Technical units stay conventional ALWAYS (OD-6).

TECHNICAL_UNITS = ("Hz", "kHz", "dB", "LUFS", "ms", "BPM")


def format_decimal(value: float, locale: str = "en", decimals: int = 1) -> str:
    """Narrative numbers follow locale separators. Technical readouts do NOT use this."""
    s = f"{value:.{decimals}f}"
    if locale in ("de", "es", "it", "pt", "fr"):
        s = s.replace(".", "X").replace(",", ".").replace("X", ",")
    return s


def format_technical(value: float, unit: str, decimals: int = 1) -> str:
    """Fixed tabular technical notation regardless of locale (OD-6): -9.4 LUFS."""
    if unit not in TECHNICAL_UNITS:
        raise ValueError(f"non-technical unit '{unit}' — use format_decimal for prose")
    return f"{value:.{decimals}f} {unit}"


def format_percent(value: float, locale: str = "en", decimals: int = 0) -> str:
    num = format_decimal(value * 100, locale="en", decimals=decimals)  # digits fixed first
    if locale == "fr":
        return f"{num} %"   # French spacing convention
    return f"{num}%"


def format_iso8601(timestamp_seconds: float) -> str:
    """Technical contexts use ISO 8601 always (LOCALISATION §7)."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------
# CJK / RTL policy data (task §21). Architecture metadata; rendering integration later.

CJK_FALLBACKS = {
    "ja": ["Hiragino Sans", "Yu Gothic"],
    "ko": ["Apple SD Gothic Neo", "Malgun Gothic"],
    "zh-Hans": ["PingFang SC", "Microsoft YaHei"],
}

RTL_LOCALES = {"ar", "he", "fa", "ur"}

# Audio-domain components that must NEVER mirror under RTL (LOCALISATION §10).
DO_NOT_MIRROR = [
    "waveform",
    "timeline",
    "spectrogram",
    "meter",
    "map_coordinates",
    "frequency_axis",      # low Hz stays left
    "bpm_value",
    "playhead_logic",
    "transport_glyphs",
]

# Components that DO mirror under RTL.
MIRRORS_UNDER_RTL = [
    "navigation_sidebar",
    "inspector_position",
    "toolbar_order",
    "list_rows",
    "text_alignment",
    "generic_progress_bar",
]


def is_rtl(locale: str) -> bool:
    return locale.split("-")[0] in RTL_LOCALES


def cjk_line_height_multiplier() -> float:
    """CJK runs +15–20% leading (LOCALISATION §9); mixed blocks take the larger value."""
    return 1.20


def text_expansion_budgets() -> dict[str, float]:
    """Representative expansion factors for layout testing (task §20, LOCALISATION §8)."""
    return {"de": 1.35, "fr": 1.30, "pt": 1.25, "es": 1.20, "ja": 0.85}
