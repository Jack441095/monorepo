"""Deterministic token generators.

Canonical source: tokens/nite_design_tokens.json
Outputs (derived artifacts, always regenerable):
  generated/cpp/NiteDesignTokens.h   — constexpr C++ data for JUCE-facing code
  generated/web/nite-tokens.css      — CSS custom properties
  generated/web/nite-tokens.ts       — TypeScript token object

Regeneration is deterministic: same input -> byte-identical output.
No network access required. Run: python3 tools/generate_tokens.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from token_validator import validate, resolve_all, load_tokens  # noqa: E402

TOKENS_PATH = ROOT / "tokens" / "nite_design_tokens.json"
CPP_OUT = ROOT / "generated" / "cpp" / "NiteDesignTokens.h"
CSS_OUT = ROOT / "generated" / "web" / "nite-tokens.css"
TS_OUT = ROOT / "generated" / "web" / "nite-tokens.ts"

GENERATED_BANNER = (
    "GENERATED FILE — derived from tokens/nite_design_tokens.json. DO NOT EDIT BY HAND.\n"
    "Regenerate with: python3 tools/generate_tokens.py\n"
)

# Ordered colour token names for stable output (frozen snapshot order).
COLOUR_ORDER = [
    "nite.color.surface.base",
    "nite.color.surface.raised",
    "nite.color.surface.overlay",
    "nite.color.surface.inset",
    "nite.color.surface.hover",
    "nite.color.elevation.modal",
    "nite.color.border.hairline.subtle",
    "nite.color.border.hairline.strong",
    "nite.color.text.primary",
    "nite.color.text.secondary",
    "nite.color.text.tertiary",
    "nite.color.text.disabled",
    "nite.color.text.inverse",
    "nite.color.interactive.base",
    "nite.color.interactive.bright",
    "nite.color.interactive.dim",
    "nite.color.interactive.ink",
    "nite.color.semantic.playing",
    "nite.color.semantic.success",
    "nite.color.semantic.warning",
    "nite.color.semantic.error",
    "nite.color.semantic.destructive",
    "nite.color.semantic.favorite",
    "nite.color.semantic.unknown",
    "nite.color.semantic.disabled",
    "nite.state.playing",
    "nite.state.success",
    "nite.state.warning",
    "nite.state.error",
    "nite.state.favorite",
    "nite.state.unknown",
    "nite.state.disabled",
    "nite.interactive.default",
    "nite.interactive.hover",
    "nite.interactive.selected",
    "nite.text.onAccent",
    "nite.slo.category.kick",
    "nite.slo.category.snare",
    "nite.slo.category.clap",
    "nite.slo.category.hihat",
    "nite.slo.category.percussion",
    "nite.slo.category.bass",
    "nite.slo.category.synth",
    "nite.slo.category.vocal",
    "nite.slo.category.unknown",
    "nite.kenn.severity.high",
    "nite.kenn.severity.medium",
    "nite.kenn.severity.low",
]

DIMENSION_ORDER = [
    "nite.space.xs", "nite.space.s", "nite.space.m", "nite.space.l", "nite.space.xl", "nite.space.xxl",
    "nite.radius.s", "nite.radius.m", "nite.radius.l",
    "nite.stroke.hairline", "nite.stroke.icon", "nite.stroke.emphasis", "nite.stroke.heavy",
    "nite.comp.row.height", "nite.comp.map.point.size", "nite.comp.type.minSizePx",
]

DURATION_ORDER = [
    "nite.motion.fast.duration", "nite.motion.standard.duration",
    "nite.motion.slow.duration", "nite.motion.pulse.duration",
    "nite.comp.tooltip.delayMs",
]

OPACITY_ORDER = [
    "nite.opacity.dimmedFocusMode", "nite.opacity.proposalUncertain",
    "nite.opacity.similarityEdgeMax", "nite.opacity.softFill", "nite.opacity.vizFillMax",
]


def _hex_to_rgba(hex_value: str, alpha: float | None = None) -> tuple[int, int, int, float]:
    h = hex_value.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r, g, b, alpha if alpha is not None else 1.0


def _token_entry(tokens: dict, name: str) -> dict | None:
    layers = tokens["layers"]
    short = name[5:]  # strip "nite."
    for layer in ("global", "semantic", "productAliases", "component"):
        layer_data = layers.get(layer, {})
        # direct hit
        if short in layer_data and isinstance(layer_data[short], dict):
            return layer_data[short]
        # nested under global (e.g. color.surface.base)
        node: dict = layer_data
        for part in short.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if isinstance(node, dict):
            return node
    return None


def _resolved(tokens: dict, name: str) -> tuple[str, float | None]:
    """Return (hex, alpha) for a token, following aliases."""
    resolved = resolve_all(tokens)
    hex_val = resolved.get(name, "")
    if not hex_val:
        raise KeyError(f"unresolved colour token: {name}")
    entry = _token_entry(tokens, name) or {}
    return hex_val, entry.get("alpha")


def _cpp_identifier(name: str) -> str:
    ident = name.replace("nite.", "").replace(".", "_")
    # camelCase segments -> snake_case boundaries kept simple; tokens already snake-ish
    return ident


def generate_cpp(tokens: dict) -> str:
    meta = tokens["meta"]
    lines: list[str] = []
    lines.append("// " + GENERATED_BANNER.replace("\n", "\n// ").rstrip())
    lines.append("#pragma once")
    lines.append("//")
    lines.append(f"// NITE DSP Design System {meta['version']} — {meta['direction']}")
    lines.append(f"// Frozen: {meta['freezeDate']}. Change control: DESIGN_SYSTEM_V1 §21.")
    lines.append("//")
    lines.append("// Compile-time constants. No allocation; safe for paint paths.")
    lines.append("")
    lines.append("#include <cstdint>")
    lines.append("")
    lines.append("namespace nite::design {")
    lines.append("")
    lines.append("struct Version { static constexpr const char* kString = \"%s\"; };" % meta["version"])
    lines.append("")
    lines.append("struct Rgba {")
    lines.append("    std::uint8_t r, g, b;")
    lines.append("    float a;")
    lines.append("};")
    lines.append("")
    lines.append("namespace colour {")
    for name in COLOUR_ORDER:
        try:
            hex_val, alpha = _resolved(tokens, name)
        except KeyError:
            continue  # unresolved tokens are skipped here; validator reports them
        r, g, b, a = _hex_to_rgba(hex_val, alpha)
        ident = _cpp_identifier(name)
        lines.append(
            f"inline constexpr Rgba k_{ident} {{ {r:#04x}, {g:#04x}, {b:#04x}, {a:.2f}f }}; "
            f"// {hex_val}"
        )
    lines.append("}  // namespace colour")
    lines.append("")
    lines.append("namespace dimension {")
    for name in DIMENSION_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        ident = _cpp_identifier(name)
        val = entry["value"]
        lines.append(f"inline constexpr float k_{ident} = {float(val):.6f}f;  // px")
    lines.append("}  // namespace dimension")
    lines.append("")
    lines.append("namespace duration {")
    for name in DURATION_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        ident = _cpp_identifier(name)
        lines.append(f"inline constexpr int k_{ident} = {entry['value']};  // ms")
    lines.append("}  // namespace duration")
    lines.append("")
    lines.append("namespace opacity {")
    for name in OPACITY_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        ident = _cpp_identifier(name)
        lines.append(f"inline constexpr float k_{ident} = {entry['value']:.2f}f;")
    lines.append("}  // namespace opacity")
    lines.append("")
    lines.append("namespace motion {")
    easing = _token_entry(tokens, "nite.motion.easing") or {}
    lines.append(f'inline constexpr const char* k_easing = "{easing.get("css", "")}";')
    lines.append("}  // namespace motion")
    lines.append("")
    lines.append("}  // namespace nite::design")
    lines.append("")
    return "\n".join(lines)


def generate_css(tokens: dict) -> str:
    meta = tokens["meta"]
    lines: list[str] = []
    lines.append("/* " + GENERATED_BANNER.replace("\n", "\n * ").rstrip() + " */")
    lines.append(f"/* NITE DSP Design System {meta['version']} — {meta['direction']} */")
    lines.append("")
    lines.append(":root {")
    for name in COLOUR_ORDER:
        try:
            hex_val, alpha = _resolved(tokens, name)
        except KeyError:
            continue
        var = "--" + name.replace(".", "-")
        if alpha is not None:
            r, g, b, _ = _hex_to_rgba(hex_val)
            lines.append(f"  {var}: rgba({r}, {g}, {b}, {alpha});  /* {hex_val} @{alpha} */")
        else:
            lines.append(f"  {var}: {hex_val};")
    lines.append("")
    for name in DIMENSION_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        var = "--" + name.replace(".", "-")
        lines.append(f"  {var}: {entry['value']}px;")
    lines.append("")
    for name in DURATION_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        var = "--" + name.replace(".", "-")
        lines.append(f"  {var}: {entry['value']}ms;")
    lines.append("")
    for name in OPACITY_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        var = "--" + name.replace(".", "-")
        lines.append(f"  {var}: {entry['value']};")
    lines.append("")
    easing = _token_entry(tokens, "nite.motion.easing") or {}
    lines.append(f"  --motion-easing: {easing.get('css', '')};")
    lines.append("}")
    lines.append("")
    lines.append("@media (prefers-reduced-motion: reduce) {")
    lines.append("  :root {")
    lines.append("    /* DS §12: transforms -> instant + opacity; no bounce/parallax/entrance */")
    lines.append("    --motion-fast-duration: 0ms;")
    lines.append("    --motion-standard-duration: 0ms;")
    lines.append("    --motion-slow-duration: 0ms;")
    lines.append("    --motion-pulse-duration: 0ms;")
    lines.append("  }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def generate_ts(tokens: dict) -> str:
    meta = tokens["meta"]
    resolved = resolve_all(tokens)
    lines: list[str] = []
    lines.append("// " + GENERATED_BANNER.rstrip())
    lines.append(f"// NITE DSP Design System {meta['version']} — {meta['direction']}")
    lines.append("")
    lines.append("export const NITE_DESIGN_SYSTEM_VERSION = '%s' as const;" % meta["version"])
    lines.append("")
    lines.append("export const color = {")
    for name in COLOUR_ORDER:
        hex_val = resolved.get(name, "")
        if not hex_val:
            continue
        key = name.replace("nite.", "").replace(".", "_")
        lines.append(f"  {key}: '{hex_val}',")
    lines.append("} as const;")
    lines.append("")
    lines.append("export const dimension = {")
    for name in DIMENSION_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        key = name.replace("nite.", "").replace(".", "_")
        lines.append(f"  {key}: {entry['value']},")
    lines.append("} as const;")
    lines.append("")
    lines.append("export const duration = {")
    for name in DURATION_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        key = name.replace("nite.", "").replace(".", "_")
        lines.append(f"  {key}: {entry['value']},")
    lines.append("} as const;")
    lines.append("")
    lines.append("export const opacity = {")
    for name in OPACITY_ORDER:
        entry = _token_entry(tokens, name)
        if not entry:
            continue
        key = name.replace("nite.", "").replace(".", "_")
        lines.append(f"  {key}: {entry['value']},")
    lines.append("} as const;")
    lines.append("")
    lines.append("export const motion = {")
    easing = _token_entry(tokens, "nite.motion.easing") or {}
    lines.append(f"  easing: '{easing.get('css', '')}',")
    lines.append("} as const;")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    tokens = load_tokens(TOKENS_PATH)
    result = validate(tokens)
    if not result.ok:
        print("TOKEN VALIDATION FAILED — refusing to generate:", file=sys.stderr)
        for issue in result.issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    CPP_OUT.parent.mkdir(parents=True, exist_ok=True)
    CSS_OUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUT.parent.mkdir(parents=True, exist_ok=True)

    CPP_OUT.write_text(generate_cpp(tokens), encoding="utf-8")
    CSS_OUT.write_text(generate_css(tokens), encoding="utf-8")
    TS_OUT.write_text(generate_ts(tokens), encoding="utf-8")

    print(f"generated: {CPP_OUT.relative_to(ROOT)}")
    print(f"generated: {CSS_OUT.relative_to(ROOT)}")
    print(f"generated: {TS_OUT.relative_to(ROOT)}")
    print("TOKEN VALIDATION: PASS — generation deterministic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
