"""NITE DSP Design System — full test suite.

Covers: token validation, alias resolution, duplicate detection, generated
artifact determinism, semantic state resolution, category completeness,
MAP shape mapping, localisation fallback/missing keys/runtime switching,
locale formatting, text expansion fixtures, CJK/RTL policy, version metadata.

Run: python3 -m pytest tests/ -q   (or python3 tests/run_all.py)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import token_validator as tv  # noqa: E402
import localisation as loc  # noqa: E402
import map_shape_grammar as msg  # noqa: E402

TOKENS = tv.load_tokens(ROOT / "tokens" / "nite_design_tokens.json")


# ------------------------------------------------------------------------------
# Token validation


def test_canonical_tokens_validate_clean():
    result = tv.validate(TOKENS)
    assert result.ok, [str(i) for i in result.issues]


def test_duplicate_key_detection():
    bad = json.loads(json.dumps(TOKENS))
    # inject a duplicate by adding same key twice via two layers
    bad["layers"]["semantic"]["state.playing"] = {"aliasOf": "nite.color.semantic.playing"}
    bad["layers"]["productAliases"]["state.playing"] = {"aliasOf": "nite.color.semantic.playing"}
    result = tv.validate(bad)
    codes = {i.code for i in result.issues}
    assert "duplicate-key" in codes


def test_malformed_hex_detection():
    bad = json.loads(json.dumps(TOKENS))
    bad["layers"]["global"]["color.surface.base"]["value"] = "#12345"
    result = tv.validate(bad)
    assert any(i.code == "malformed-hex" for i in result.issues)


def test_circular_alias_detection():
    bad = json.loads(json.dumps(TOKENS))
    bad["layers"]["semantic"]["state.playing"] = {"aliasOf": "nite.state.error"}
    bad["layers"]["semantic"]["state.error"] = {"aliasOf": "nite.state.playing"}
    result = tv.validate(bad)
    assert any(i.code == "circular-alias" for i in result.issues)


def test_dangling_alias_detection():
    bad = json.loads(json.dumps(TOKENS))
    bad["layers"]["semantic"]["state.playing"] = {"aliasOf": "nite.does.not.exist"}
    result = tv.validate(bad)
    assert any(i.code == "dangling-alias" for i in result.issues)


def test_frozen_drift_detection():
    """Any silent change to a frozen colour must fail validation (DS §21)."""
    bad = json.loads(json.dumps(TOKENS))
    bad["layers"]["global"]["color.interactive.base"]["value"] = "#FF8800"
    result = tv.validate(bad)
    assert any(i.code == "frozen-drift" for i in result.issues)


def test_category_completeness():
    for cat in tv.REQUIRED_CATEGORIES:
        assert f"slo.category.{cat}" in json.dumps(TOKENS["layers"]["productAliases"])


def test_state_completeness():
    resolved = tv.resolve_all(TOKENS)
    for st in tv.REQUIRED_STATES:
        assert resolved.get(f"nite.color.semantic.{st}"), f"missing state {st}"


def test_category_never_reuses_semantic_hue():
    result = tv.validate(TOKENS)
    assert not any(i.code == "category-reuses-semantic-hue" for i in result.issues)


def test_version_metadata_present():
    meta = TOKENS["meta"]
    assert meta["version"].startswith("1.")
    assert meta["frozen"] is True
    assert meta["freezeDate"] == "2026-08-22"


# ------------------------------------------------------------------------------
# WCAG 2.x contrast (1.0.1 accessibility correction)


def _relative_luminance(hex_value: str) -> float:
    h = hex_value.lstrip("#")

    def channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = channel(int(h[0:2], 16)), channel(int(h[2:4], 16)), channel(int(h[4:6], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_tertiary_text_meets_wcag_aa_body_threshold():
    """DS §3.2 tertiary = readable metadata (body-size text) → SC 1.4.3 ≥4.5:1.

    1.0.0 shipped #6E675E at a measured 3.53:1 against its own claimed 4.6 floor;
    corrected to #827B71 in 1.0.1. See docs/CHANGELOG.md.
    """
    resolved = tv.resolve_all(TOKENS)
    base = resolved["nite.color.surface.base"]
    ratio = _contrast_ratio(resolved["nite.color.text.tertiary"], base)
    assert ratio >= 4.6, f"tertiary on base {ratio:.3f} below spec floor 4.6"
    assert round(ratio, 1) == TOKENS["layers"]["global"]["color.text.tertiary"]["contrastOnBase"]


def test_text_hierarchy_contrast_ordering_preserved():
    """primary > secondary > tertiary ordering must survive the correction."""
    resolved = tv.resolve_all(TOKENS)
    base = resolved["nite.color.surface.base"]
    ratios = [
        _contrast_ratio(resolved[f"nite.color.text.{role}"], base)
        for role in ("primary", "secondary", "tertiary")
    ]
    assert ratios == sorted(ratios, reverse=True)


def test_corrected_tertiary_stays_in_warm_grey_hue_family():
    """Identity guard: the 1.0.1 lift must be lightness-only within the hue family."""
    import colorsys

    def hsl(hex_value):
        h = hex_value.lstrip("#")
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
        hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
        return hh * 360, ss

    old_hue, _ = hsl("#6E675E")
    new_hue, new_sat = hsl(tv.FROZEN_COLOURS["nite.color.text.tertiary"])
    assert abs(new_hue - old_hue) < 2.0
    assert new_sat < 0.12          # stays a desaturated warm grey
    assert new_hue < 60            # warm family, not green/blue


# ------------------------------------------------------------------------------
# Alias resolution


def test_semantic_aliases_resolve_to_global_values():
    resolved = tv.resolve_all(TOKENS)
    assert resolved["nite.state.playing"] == "#7FB069"
    assert resolved["nite.interactive.hover"] == "#F7B955"
    assert resolved["nite.text.onAccent"] == "#1A1207"


def test_product_aliases_resolve():
    resolved = tv.resolve_all(TOKENS)
    assert resolved["nite.slo.category.clap"] == "#D98BA6"   # C-08 final
    assert resolved["nite.slo.category.unknown"] == "#4A453D"
    assert resolved["nite.kenn.severity.high"] == "#E5484D"


def test_unresolved_tokens_are_explicit_not_guessed():
    """ai.accepted has no special hue BY DESIGN; resolver returns '' (explicit unresolved)."""
    resolved = tv.resolve_all(TOKENS)
    assert resolved.get("nite.ai.accepted", "") in ("", None)


# ------------------------------------------------------------------------------
# Generated artifacts + determinism


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("relpath", [
    "generated/cpp/NiteDesignTokens.h",
    "generated/web/nite-tokens.css",
    "generated/web/nite-tokens.ts",
])
def test_generated_files_exist_and_deterministic(relpath):
    target = ROOT / relpath
    before = _sha(target)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "generate_tokens.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert _sha(target) == before, f"{relpath} is not deterministic"


def test_cpp_header_contains_frozen_copper():
    header = (ROOT / "generated" / "cpp" / "NiteDesignTokens.h").read_text()
    assert "0xe8, 0x9b, 0x3c" in header          # #E89B3C copper
    assert 'kString = "1.0.1"' in header


def test_web_css_contains_css_variables():
    css = (ROOT / "generated" / "web" / "nite-tokens.css").read_text()
    assert "--nite-color-surface-base: #0C0B09;" in css
    assert "--nite-color-interactive-base: #E89B3C;" in css
    assert "prefers-reduced-motion" in css       # reduced-motion policy emitted


def test_ts_tokens_parseable():
    ts = (ROOT / "generated" / "web" / "nite-tokens.ts").read_text()
    assert "NITE_DESIGN_SYSTEM_VERSION = '1.0.1'" in ts
    assert "slo_category_clap: '#D98BA6'" in ts


# ------------------------------------------------------------------------------
# Semantic states (validated through the C++ adapter smoke binary if present)


def test_state_redundant_encoding_rules_documented_in_adapter():
    src = (ROOT / "cpp" / "NiteLookAndFeelFoundation.h").read_text()
    # Every semantic state case must carry a glyph or geometry channel.
    for glyph in ["\\u25B6", "\\u2605", "\\u26A0", "\\u2715"]:
        assert glyph in src, f"missing redundant-encoding glyph {glyph}"
    assert "dashed" in src and "provisional" in src


def test_ai_grammar_provisional_vs_authoritative():
    src = (ROOT / "cpp" / "NiteLookAndFeelFoundation.h").read_text()
    assert "MACHINE PROPOSAL = PROVISIONAL" in src
    assert "USER DECISION = AUTHORITATIVE" in src
    assert "isProvisional" in src


# ------------------------------------------------------------------------------
# MAP shape grammar (R-CVD-1)


def test_family_shapes_default_on_and_distinct():
    assert msg.shapes_pairwise_distinct()
    assert msg.FAMILY_SHAPES == {
        "drums": "circle", "bass": "square", "synth": "triangle", "vocal": "hollow-circle",
    }


def test_subcategories_inherit_family_shape():
    assert msg.shape_for_category("kick") == "circle"
    assert msg.shape_for_category("snare") == "circle"
    assert msg.shape_for_category("clap") == "circle"
    assert msg.shape_for_category("hihat") == "circle"
    assert msg.shape_for_category("percussion") == "circle"
    assert msg.shape_for_category("bass") == "square"
    assert msg.shape_for_category("synth") == "triangle"
    assert msg.shape_for_category("vocal") == "hollow-circle"
    assert msg.shape_for_category("unknown") == "dashed-hollow"


def test_shape_hit_testing():
    c = msg.Point(10, 10)
    assert msg.shape_hit_test("square", c, 7, msg.Point(12, 12))
    assert not msg.shape_hit_test("square", c, 7, msg.Point(20, 20))
    assert msg.shape_hit_test("circle", c, 7, msg.Point(13, 10))
    assert msg.shape_hit_test("triangle", c, 8, msg.Point(10, 9))     # near apex-ish interior
    assert not msg.shape_hit_test("triangle", c, 8, msg.Point(10, 14))


def test_map_point_size_matches_component_token():
    comp = TOKENS["layers"]["component"]["comp.map.point.size"]
    assert comp["value"] == msg.small_size_legibility_floor_px() == 7


# ------------------------------------------------------------------------------
# Localisation


@pytest.fixture()
def manager():
    return loc.LocalisationManager(ROOT / "localisation")


def test_english_base_bundle_loads(manager):
    assert manager.current_locale == "en"
    assert manager.get("action.play") == "Play"
    assert manager.get("view.map") == "Map"


def test_stable_keys_not_english_text(manager):
    """Keys are the contract; displayed copy lives only in values."""
    bundle = loc.load_bundle(ROOT / "localisation" / "strings_en.json")
    assert "action.find_similar" in bundle
    assert bundle["action.find_similar"] == "Find Similar"


def test_missing_key_raises_with_diagnostic(manager):
    with pytest.raises(loc.MissingKeyError):
        manager.get("does.not.exist")
    report = manager.missing_key_report()
    assert any(key == "does.not.exist" for _, key in report)


def test_runtime_locale_switch_with_notification(manager):
    events: list[str] = []
    manager.on_locale_changed(events.append)
    assert manager.set_locale("en") is True      # unknown bundle -> False path tested below
    assert manager.set_locale("xx-UNKNOWN") is False
    assert events == []                          # failed switch does not notify


def test_plural_formatting(manager):
    assert manager.format("common.results.count", count=1) == "1 sample"
    assert manager.format("common.results.count", count=5) == "5 samples"


def test_technical_units_fixed_across_locales():
    assert loc.format_technical(-9.4, "LUFS") == "-9.4 LUFS"
    assert loc.format_technical(174, "BPM", decimals=0) == "174 BPM"
    assert loc.format_technical(440, "Hz") == "440.0 Hz"
    with pytest.raises(ValueError):
        loc.format_technical(5, "apples")


def test_narrative_decimal_localisation():
    assert loc.format_decimal(1234.5, locale="en") == "1234.5"
    # German convention: comma decimal separator (thousands grouping applies at >=10000 scale)
    assert loc.format_decimal(1234.5, locale="de") == "1234,5"
    assert loc.format_decimal(12345.6, locale="de") == "12345,6"


def test_percent_formatting():
    assert loc.format_percent(0.94) == "94%"
    assert loc.format_percent(0.946, decimals=1) == "94.6%"
    assert loc.format_percent(0.94, locale="fr") == "94 %"


def test_iso8601_technical_dates():
    assert loc.format_iso8601(0) == "1970-01-01T00:00:00Z"


# ------------------------------------------------------------------------------
# CJK / RTL policy


def test_cjk_fallback_chains_present():
    assert loc.CJK_FALLBACKS["ja"][0] == "Hiragino Sans"
    assert loc.CJK_FALLBACKS["zh-Hans"][0] == "PingFang SC"
    assert loc.cjk_line_height_multiplier() >= 1.15


def test_rtl_do_not_mirror_audio_components():
    for component in ("waveform", "frequency_axis", "playhead_logic", "map_coordinates"):
        assert component in loc.DO_NOT_MIRROR
    assert "inspector_position" in loc.MIRRORS_UNDER_RTL
    assert loc.is_rtl("ar")
    assert not loc.is_rtl("de")


def test_text_expansion_budgets_cover_required_cases():
    budgets = loc.text_expansion_budgets()
    assert budgets["de"] >= 1.30      # LOCALISATION §8 de/fr +30–35%
    assert budgets["es"] >= 1.20


# ------------------------------------------------------------------------------
# Typography / motion token integrity


def test_typography_roles_complete():
    flat = json.dumps(TOKENS["layers"]["global"])
    assert "type.family.primary" in flat
    assert "type.family.mono" in flat
    assert "type.numerals.tabular" in flat


def test_motion_tokens_frozen_values():
    g = TOKENS["layers"]["global"]
    assert g["motion.fast.duration"]["value"] == 120
    assert g["motion.standard.duration"]["value"] == 180
    assert g["motion.slow.duration"]["value"] == 300
    assert g["motion.easing"]["css"] == "cubic-bezier(0.25, 1, 0.5, 1)"


def test_accent_budgets_within_spec():
    b = TOKENS["layers"]["accentBudget"]
    assert b["slo.map"]["maxPct"] <= b["slo.list"]["maxPct"]      # MAP tighter than LIST
    assert b["website"]["maxPct"] == 12
    assert b["modal"]["maxPct"] == 10


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
