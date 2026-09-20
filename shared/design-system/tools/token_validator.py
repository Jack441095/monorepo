"""NITE DSP design token validation.

Validates the canonical token source (tokens/nite_design_tokens.json) against
the frozen NITE DSP Design System 1.0 (EMBER). The frozen spec is authoritative;
these checks exist so the system cannot silently drift.

Change control per DESIGN_SYSTEM_V1 §21: any change to a frozen value must be
accompanied by explicit version metadata, or validation fails.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Frozen values from DESIGN_SYSTEM_V1 §3/§6 — the golden snapshot.
# Any deviation here is accidental drift unless meta.version was intentionally bumped.
FROZEN_COLOURS: dict[str, str] = {
    "nite.color.surface.base": "#0C0B09",
    "nite.color.surface.raised": "#14120F",
    "nite.color.surface.overlay": "#1C1915",
    "nite.color.surface.inset": "#080706",
    "nite.color.surface.hover": "#191612",
    "nite.color.elevation.modal": "#201C16",
    "nite.color.border.hairline.subtle": "#2A261F",
    "nite.color.border.hairline.strong": "#2A261F",
    "nite.color.text.primary": "#EDE8E0",
    "nite.color.text.secondary": "#A39B8F",
    "nite.color.text.tertiary": "#827B71",  # 1.0.1 accessibility correction (was #6E675E @ 3.53:1)
    "nite.color.text.disabled": "#4A453D",
    "nite.color.text.inverse": "#1A1207",
    "nite.color.interactive.base": "#E89B3C",
    "nite.color.interactive.bright": "#F7B955",
    "nite.color.interactive.dim": "#8A5F28",
    "nite.color.interactive.ink": "#1A1207",
    "nite.color.semantic.playing": "#7FB069",
    "nite.color.semantic.success": "#7FB069",
    "nite.color.semantic.warning": "#E5B84B",
    "nite.color.semantic.error": "#E5484D",
    "nite.color.semantic.destructive": "#E5484D",
    "nite.color.semantic.favorite": "#D9A75A",
    "nite.color.semantic.unknown": "#4A453D",
    "nite.color.semantic.disabled": "#4A453D",
    "nite.slo.category.kick": "#C96F4A",
    "nite.slo.category.snare": "#E3C567",
    "nite.slo.category.clap": "#D98BA6",
    "nite.slo.category.hihat": "#9FC2A5",
    "nite.slo.category.percussion": "#B98BD6",
    "nite.slo.category.bass": "#6E93B8",
    "nite.slo.category.synth": "#7FB0C4",
    "nite.slo.category.vocal": "#E0A96B",
}

REQUIRED_CATEGORIES = [
    "kick", "snare", "clap", "hihat", "percussion", "bass", "synth", "vocal", "unknown",
]

REQUIRED_STATES = [
    "playing", "success", "warning", "error", "destructive", "favorite", "unknown", "disabled",
]

REQUIRED_TYPE_ROLES = [
    "display", "heading", "section", "body", "control", "metadata", "caption", "numerical",
]

# R-CVD-1: MAP family shape coding default-on at ALL zoom levels (frozen).
MAP_FAMILY_SHAPES = {
    "drums": "circle",
    "bass": "square",
    "synth": "triangle",
    "vocal": "hollow-circle",
}

CATEGORY_TO_FAMILY = {
    "kick": "drums", "snare": "drums", "clap": "drums", "hihat": "drums", "percussion": "drums",
    "bass": "bass",
    "synth": "synth",
    "vocal": "vocal",
}


@dataclass
class ValidationIssue:
    code: str
    message: str
    token: str | None = None

    def __str__(self) -> str:  # pragma: no cover - display helper
        loc = f" [{self.token}]" if self.token else ""
        return f"{self.code}{loc}: {self.message}"


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def errors(self) -> list[ValidationIssue]:
        return self.issues


def _flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, val in obj.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            if "value" in val or "aliasOf" in val or "stack" in val or "css" in val:
                flat[name] = val
            else:
                flat.update(_flatten(val, name))
        else:
            flat[name] = val
    return flat


def load_tokens(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate(tokens: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    layers = tokens.get("layers", {})
    global_layer = layers.get("global", {})
    semantic_layer = layers.get("semantic", {})
    alias_layer = layers.get("productAliases", {})

    # Build fully-qualified namespaced view: nite.<layer-path>
    ns_global = {f"nite.{k}": v for k, v in _flatten(global_layer).items()}
    ns_semantic = {f"nite.{k}": v for k, v in semantic_layer.items()}
    ns_alias = {f"nite.{k}": v for k, v in alias_layer.items()}
    all_names = list(ns_global) + list(ns_semantic) + list(ns_alias)

    # 1. duplicate keys
    seen: set[str] = set()
    for name in all_names:
        if name in seen:
            result.issues.append(ValidationIssue("duplicate-key", f"duplicate token {name}", name))
        seen.add(name)

    # 2. malformed hex values
    def check_hex(name: str, entry: dict[str, Any]) -> None:
        for field_name in ("value", "stroke"):
            raw = entry.get(field_name)
            if isinstance(raw, str) and raw.startswith("#") and not HEX_RE.match(raw):
                result.issues.append(
                    ValidationIssue("malformed-hex", f"'{raw}' is not #RRGGBB", name)
                )

    for name, entry in {**ns_global, **ns_alias}.items():
        if isinstance(entry, dict):
            check_hex(name, entry)

    # 3. missing semantic aliases
    for name, entry in ns_semantic.items():
        if not isinstance(entry, dict) or "aliasOf" not in entry:
            result.issues.append(
                ValidationIssue("missing-alias", "semantic token must define aliasOf", name)
            )
            continue
        target = entry["aliasOf"]
        if target not in ns_global and target not in ns_alias:
            result.issues.append(
                ValidationIssue("dangling-alias", f"aliasOf target '{target}' not found", name)
            )

    # 4. circular aliases
    def resolve(name: str, chain: list[str]) -> list[str]:
        if name in chain:
            return chain + [name]
        entry = ns_semantic.get(name) or ns_alias.get(name)
        if not isinstance(entry, dict) or "aliasOf" not in entry:
            return chain
        return resolve(entry["aliasOf"], chain + [name])

    for layer_ns in (ns_semantic, ns_alias):
        for name, entry in layer_ns.items():
            if isinstance(entry, dict) and "aliasOf" in entry:
                chain = resolve(name, [])
                if len(chain) > 2 and chain[0] == chain[-1]:
                    result.issues.append(
                        ValidationIssue("circular-alias", " -> ".join(chain), name)
                    )

    # 5. invalid numeric ranges
    for name, entry in ns_global.items():
        if not isinstance(entry, dict):
            continue
        t = entry.get("type")
        val = entry.get("value")
        if t == "opacity":
            if not isinstance(val, (int, float)) or not (0.0 < val <= 1.0):
                result.issues.append(
                    ValidationIssue("invalid-range", f"opacity {val!r} outside (0, 1]", name)
                )
        elif t == "duration":
            if not isinstance(val, int) or val <= 0:
                result.issues.append(
                    ValidationIssue("invalid-range", f"duration {val!r} must be positive int ms", name)
                )
        elif t == "dimension":
            if not isinstance(val, (int, float)) or val <= 0:
                result.issues.append(
                    ValidationIssue("invalid-range", f"dimension {val!r} must be positive", name)
                )

    # 6. required category tokens (SLO palette frozen at freeze; DS §6)
    for cat in REQUIRED_CATEGORIES:
        key = f"nite.slo.category.{cat}"
        if key not in ns_alias:
            result.issues.append(ValidationIssue("missing-category", "required SLO category token absent", key))

    # 7. required state tokens (DS §3.4)
    for st in REQUIRED_STATES:
        key = f"nite.color.semantic.{st}"
        if key not in ns_global:
            result.issues.append(ValidationIssue("missing-state", "required semantic state token absent", key))

    # 7b. accent budget metadata sanity (DS §4)
    budgets = layers.get("accentBudget", {})
    for ctx, budget in budgets.items():
        lo, hi = budget.get("minPct"), budget.get("maxPct")
        if lo is not None and hi is not None and lo > hi:
            result.issues.append(
                ValidationIssue("invalid-budget", f"minPct {lo} > maxPct {hi}", ctx)
            )

    # 8. typography roles completeness (DS §7)
    type_tokens = [k for k in ns_global if k.startswith("nite.type.")]
    has_family = any(".family." in k for k in type_tokens)
    has_numerals = any("numerals.tabular" in k for k in type_tokens)
    if not has_family:
        result.issues.append(ValidationIssue("incomplete-typography", "no font family tokens defined"))
    if not has_numerals:
        result.issues.append(ValidationIssue("incomplete-typography", "tabular numerals flag missing"))

    # 9. frozen colour snapshot — accidental drift detection (DS §21 change control)
    resolved = resolve_all(tokens)
    for name, expected in FROZEN_COLOURS.items():
        actual = resolved.get(name)
        if actual is None:
            result.issues.append(ValidationIssue("missing-frozen-token", "frozen token absent", name))
        elif actual.upper() != expected.upper():
            result.issues.append(
                ValidationIssue(
                    "frozen-drift",
                    f"frozen value changed: expected {expected}, found {actual}. "
                    "Requires explicit version bump per DS §21.",
                    name,
                )
            )

    # 10. R-CVD-1: MAP shape grammar must be present and default-on
    for cat, family in CATEGORY_TO_FAMILY.items():
        entry = ns_alias.get(f"nite.slo.category.{cat}")
        if isinstance(entry, dict):
            if entry.get("family") != family:
                result.issues.append(
                    ValidationIssue(
                        "map-shape-mapping",
                        f"category '{cat}' must belong to family '{family}' (R-CVD-1)",
                        f"nite.slo.category.{cat}",
                    )
                )
            expected_shape = MAP_FAMILY_SHAPES.get(family)
            if expected_shape and entry.get("shape") != expected_shape:
                result.issues.append(
                    ValidationIssue(
                        "map-shape-mapping",
                        f"category '{cat}' shape must be '{expected_shape}' (R-CVD-1)",
                        f"nite.slo.category.{cat}",
                    )
                )

    # 11. category colours must never reuse semantic hues (DS §6 extension rule)
    semantic_hues = {
        resolved[k].upper()
        for k in (
            "nite.color.interactive.base",
            "nite.color.semantic.playing",
            "nite.color.semantic.warning",
            "nite.color.semantic.error",
            "nite.color.semantic.favorite",
        )
        if resolved.get(k)
    }
    for cat in REQUIRED_CATEGORIES[:-1]:  # unknown intentionally aliases semantic.unknown
        val = resolved.get(f"nite.slo.category.{cat}")
        if val and val.upper() in semantic_hues:
            result.issues.append(
                ValidationIssue(
                    "category-reuses-semantic-hue",
                    "category colour collides with a reserved semantic hue (DS §6)",
                    f"nite.slo.category.{cat}",
                )
            )

    # 12. version metadata present and consistent with frozen status
    meta = tokens.get("meta", {})
    if not meta.get("version"):
        result.issues.append(ValidationIssue("missing-version", "meta.version required"))
    if meta.get("version", "").startswith("1.") and not meta.get("frozen"):
        result.issues.append(
            ValidationIssue("version-metadata", "frozen flag must be true while version is 1.x")
        )

    return result


def resolve_all(tokens: dict[str, Any]) -> dict[str, str]:
    """Resolve every colour-ish token to its final hex value ('' when unresolved)."""
    layers = tokens.get("layers", {})
    ns_global = {f"nite.{k}": v for k, v in _flatten(layers.get("global", {})).items()}
    ns_semantic = {f"nite.{k}": v for k, v in layers.get("semantic", {}).items()}
    ns_alias = {f"nite.{k}": v for k, v in layers.get("productAliases", {}).items()}
    lookup = {**ns_global, **ns_semantic, **ns_alias}
    resolved: dict[str, str] = {}

    def resolve_value(name: str, depth: int = 0) -> str:
        if depth > 16:
            return ""
        entry = lookup.get(name)
        if entry is None:
            return ""
        if isinstance(entry, str):
            return entry
        if not isinstance(entry, dict):
            return ""
        if "aliasOf" in entry:
            target = entry["aliasOf"]
            if isinstance(target, str) and target.startswith("raw:#"):
                return target[4:]
            return resolve_value(target, depth + 1)
        if "stroke" in entry and isinstance(entry["stroke"], str) and entry["stroke"].startswith("#"):
            return entry["stroke"]
        val = entry.get("value")
        if isinstance(val, str) and val.startswith("#"):
            return val
        return ""

    for name in lookup:
        resolved[name] = resolve_value(name)
    return resolved


def validate_file(path: str | Path) -> ValidationResult:
    return validate(load_tokens(path))


if __name__ == "__main__":  # pragma: no cover
    import sys

    token_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent.parent / "tokens" / "nite_design_tokens.json"
    res = validate_file(token_path)
    for issue in res.issues:
        print(issue)
    print("TOKEN VALIDATION:", "PASS" if res.ok else f"FAIL ({len(res.issues)} issues)")
    sys.exit(0 if res.ok else 1)
