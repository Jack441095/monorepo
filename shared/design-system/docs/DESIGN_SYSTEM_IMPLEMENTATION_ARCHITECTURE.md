# NITE DSP — Design System Implementation Architecture

**Status:** Implementation-preparation foundation for NITE DSP Design System 1.0 (EMBER).
**Scope:** Infrastructure only. No SLO / KENN / website production UI migrated.
**Canonical spec:** `../design_prototypes/ember/NITE_DSP_DESIGN_SYSTEM_V1.md` (frozen 2026-08-22)
**Localisation spec:** `../design_prototypes/ember/NITE_DSP_LOCALISATION_ARCHITECTURE_V1.md`
**Backlog mapping:** `../design_prototypes/ember/NITE_DSP_DESIGN_SYSTEM_IMPLEMENTATION_BACKLOG.md` (DS-I01…DS-I09 prepared; DS-I10…DS-I12 planned only)

---

## 1. Repository layout

```
design-system/
├── tokens/
│   └── nite_design_tokens.json        # CANONICAL SOURCE (DS-I01) — four-layer model
├── tools/
│   ├── token_validator.py             # drift prevention + structural validation
│   ├── generate_tokens.py             # deterministic C++/CSS/TS generation
│   ├── localisation.py                # runtime manager, formatters, CJK/RTL policy
│   └── map_shape_grammar.py           # R-CVD-1 geometry utilities + hit testing
├── generated/                         # DERIVED ARTIFACTS — never hand-edit
│   ├── cpp/NiteDesignTokens.h         # constexpr data, paint-path safe
│   └── web/{nite-tokens.css,nite-tokens.ts}
├── cpp/
│   ├── NiteDesignAdapter.h            # DS-I02 semantic accessors, ColourId registry
│   └── NiteLookAndFeelFoundation.h    # DS-I03 states, a11y helpers, motion policy
├── icons/nite_icons.svg.xml           # DS-I05 semantic icon set (1.5px stroke, 16 grid)
├── localisation/strings_en.json       # DS-I08 English base bundle (fallback locale)
└── tests/test_design_system.py        # 40 tests across all domains
```

## 2. Token pipeline (DS §15, task §30)

```
tokens/nite_design_tokens.json   (canonical, frozen values)
        │ validate (token_validator.py — frozen snapshot + structure rules)
        ▼
tools/generate_tokens.py         (refuses to generate on validation failure)
        ├─► generated/cpp/NiteDesignTokens.h     (constexpr Rgba/dimensions/durations)
        ├─► generated/web/nite-tokens.css        (custom properties + reduced-motion block)
        └─► generated/web/nite-tokens.ts         (typed const objects)
```

Regeneration is byte-deterministic (verified by test). No network access required.

## 3. Layer model

1. **GLOBAL** (`nite.color.*`, `nite.type.*`, `nite.space.*`, `nite.radius.*`, `nite.stroke.*`, `nite.motion.*`, `nite.opacity.*`, `nite.visualisation.*`) — frozen identity.
2. **SEMANTIC** (`nite.state.*`, `nite.interactive.*`) — aliases into global.
3. **PRODUCT ALIASES** (`nite.slo.category.*`, `nite.kenn.severity.*`) — map to global or pre-approved category hexes; never fork identity.
4. **COMPONENT** (`nite.comp.*`) — row height 27, MAP point 7, tooltip delay 250ms, etc.

Unresolved values are represented explicitly (e.g. `ai.accepted` has no hue by design) rather than guessed.

## 4. JUCE integration path (DS-I02/I03)

- `NiteDesignAdapter.h`: enum-driven semantic accessors (`ColourRole`, `SloCategory`, `TypeRole`), documented ColourId numeric bands (base 0x0001xxxx / SLO 0x0002xxxx / KENN 0x0003xxxx), MAP family shape enums, icon ID constants.
- `NiteLookAndFeelFoundation.h`: composable state resolution (`ComponentState` → `StateVisual` with mandatory redundant encoding), WCAG contrast helper, reduced-motion preference (atomic, RT-safe reads).
- Products subclass the shared LookAndFeel and override **alias layers only**. Verified compiling standalone with clang++ `-std=c++17 -Wall -Wextra`; JUCE-gated code sits behind `NITE_DESIGN_JUCE_AVAILABLE`.

## 5. Semantic states (DS-I06)

Twelve component states resolve to fill/stroke/width/dash/glyph/opacity. Redundant encoding is enforced: playing=▶, favorite=★, warning=▲+text chip, error=✕, unknown=dashed hollow, AI proposal=dashed copper+"provisional", accepted=solid authoritative (no special hue). Disabled ≠ unknown is preserved structurally.

## 6. MAP shape grammar (R-CVD-1)

● drums · ■ bass · ▲ synth · ○ vocal — default-on at all zoom levels, sub-categories inherit family shape, unknown = dashed hollow. Pure-Python geometry module provides vertices, hit-testing, distinctness proof; mirrored as C++ enums in the adapter.

## 7. Localisation (DS-I08/I09)

Stable keys (`action.play`, `category.vocal`, …) are the contract; English copy is reference only. Runtime manager: fallback resolution, missing-key diagnostics, change notification for re-layout passes, thread-safe reads, ICU-style plurals. Technical units (Hz/kHz/dB/LUFS/ms/BPM) remain fixed across locales (OD-6). CJK fallback chains and RTL mirror/do-not-mirror policies encoded as data.

## 8. Tertiary text contrast — contradiction found, resolved in 1.0.1

The frozen 1.0.0 spec stated tertiary text `#6E675E` achieves "≥4.6:1" on base, but its measured WCAG 2.x relative-luminance contrast on `#0C0B09` was **3.53:1** (primary 16.13:1 ✓ vs "15", secondary 7.16:1 ✓ vs "7"). Tertiary text is used for readable metadata (DS §3.2 "contrast floor for readable metadata"; §11 grid labels at 9–10px), which is normal body-size text under WCAG 2.x AA → **SC 1.4.3 requires ≥4.5:1**; the large-text exception (3:1, SC 1.4.6) does not apply. The 1.0.0 value therefore failed both the spec's own floor and AA.

Resolved in **1.0.1** (sanctioned accessibility correction per DS §21 change control): tertiary is now `#827B71`, a pure-lightness lift (+0.072 L) within the same warm-grey hue family (~34°) — measured **4.70:1** on base, meeting the spec's own 4.6 floor with margin. No other token changed. Full math and rationale in `docs/CHANGELOG.md`. The runtime floor check now validates against the AA threshold (≥4.5:1) so any regression fails loudly.

## 9. Performance notes (task §29)

Generated C++ is `inline constexpr` — no allocation, no lookup cost in paint paths. Reduced-motion flag is `std::atomic<bool>` with relaxed ordering. Localisation manager caches parsed bundles; string lookups are dict hits. SVG assets are static files intended for one-time parse at construction (never per-frame).

## 10. What this phase deliberately does NOT do

No SLO migration (DS-I10), no KENN migration (DS-I11), no website mapping execution (DS-I12), no production LookAndFeel swap, no font binaries committed, no plugin builds installed. Migration plans live in `PRODUCT_MIGRATION_PLAN.md`.
