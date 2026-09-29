"""What Live itself says a parameter can do, and a check of our notes against it.

The facts come from two places: the profiles in core/device_units.py (each confirmed by a read/write/readback probe on
real Live) and the evidence files that tooling/scripts/measure_device_parameters.py writes from Live's own display
strings. A note that gives a number outside a measured range is wrong or out of date, and the measurement wins
(see core/source_tiers.py).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from kenn.core import device_units

DEFAULT_MEASURED_DIR = Path(__file__).resolve().parents[4] / "tooling" / "data" / "measured_devices"
_CONTINUOUS = {"linear", "log", "table", "table_descending"}
_UNITS = {"db": "db", "hz": "hz", "khz": "hz", "ms": "ms", "%": "%", "percent": "%"}
_UNIT_SCALE = {"khz": 1000.0}
# Words that start another parameter's number; a figure that follows one of these isn't the parameter we're checking.
_OTHER_CONTEXT = re.compile(
    r"\b(?:attack|release|ratio|knee|ceiling|makeup|gain|drive|frequency|freq|resonance|width|output|input|"
    r"threshold|dry|wet|feedback|time|rate|depth|amount|mix)\b", re.I)
_CLAIM = re.compile(r"(?<![\w.])(?P<value>[-−+]?\d+(?:\.\d+)?)\s*(?P<unit>khz|hz|db|ms|%|percent)(?![A-Za-z])", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Fact:
    device: str
    parameter: str
    unit: str
    low: float
    high: float
    source: str


def facts_from_profiles() -> list[Fact]:
    facts = []
    for profile in device_units.EVIDENCE_BACKED_PROFILES:
        unit = _UNITS.get(device_units.normalize_unit(profile.display_unit).lower())
        if unit is None:
            continue
        facts.append(Fact(profile.device_name, profile.parameter_name, unit,
                          min(profile.display_min, profile.display_max), max(profile.display_min, profile.display_max),
                          f"device_units:{profile.device_name}.{profile.parameter_name}"))
    return facts


def facts_from_evidence(directory: Path) -> list[Fact]:
    facts = []
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        device = str(evidence.get("device") or "")
        for parameter in evidence.get("parameters") or []:
            unit = _UNITS.get(str(parameter.get("unit") or "").lower())
            if not device or unit is None or parameter.get("mapping") not in _CONTINUOUS:
                continue
            try:
                low, high = float(parameter["display_min"]), float(parameter["display_max"])
            except (KeyError, TypeError, ValueError):
                continue
            facts.append(Fact(device, str(parameter.get("name") or ""), unit, min(low, high), max(low, high),
                              f"{path.name}:{device}.{parameter.get('name')}"))
    return facts


def load_facts(directory: Path | None = None) -> list[Fact]:
    """Profiles first, then measured evidence; a later measurement of the same parameter replaces the earlier."""
    directory = directory or Path(os.environ.get("KENN_MEASURED_DEVICES_DIR", str(DEFAULT_MEASURED_DIR))).expanduser()
    merged: dict[tuple[str, str, str], Fact] = {}
    for fact in [*facts_from_profiles(), *facts_from_evidence(directory)]:
        merged[(fact.device.casefold(), fact.parameter.casefold(), fact.unit)] = fact
    return list(merged.values())


def _name_pattern(name: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    return re.compile(r"\b" + r"[\s/_-]*".join(words) + r"\b", re.I)


def check_note(text: str, title: str, facts: Iterable[Fact]) -> list[dict[str, Any]]:
    """Numbers a note gives for a measured parameter that Live's own range rules out.

    A device counts as the note's subject when its name is in the title or in the sentence itself. Each figure is
    tied to the nearest parameter named before it in the sentence, and skipped if another parameter's word sits
    between them or the unit isn't that parameter's unit ("threshold ... 4:1", "attack 10 ms and threshold -20 dB").
    """
    findings: list[dict[str, Any]] = []
    for sentence in _SENTENCE.split(text):
        for fact in facts:
            if not (_name_pattern(fact.device).search(title) or _name_pattern(fact.device).search(sentence)):
                continue
            named = _name_pattern(fact.parameter)
            for mention in named.finditer(sentence):
                for claim in _CLAIM.finditer(sentence, mention.end()):
                    between = sentence[mention.end():claim.start()]
                    if len(between) > 60 or _OTHER_CONTEXT.search(between):
                        break
                    unit = _UNITS[claim.group("unit").lower()]
                    if unit != fact.unit:
                        continue
                    value = float(claim.group("value").replace("−", "-")) * _UNIT_SCALE.get(claim.group("unit").lower(), 1.0)
                    if fact.low - 1e-9 <= value <= fact.high + 1e-9:
                        continue
                    findings.append({"device": fact.device, "parameter": fact.parameter, "claimed": value, "unit": fact.unit,
                                     "measured_low": fact.low, "measured_high": fact.high, "source": fact.source,
                                     "sentence": sentence.strip()[:240]})
                    break
    seen = set()
    return [f for f in findings if not ((key := (f["device"], f["parameter"], f["claimed"])) in seen or seen.add(key))]
