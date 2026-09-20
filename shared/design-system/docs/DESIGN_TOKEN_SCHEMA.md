# NITE DSP — Design Token Schema

**Canonical file:** `tokens/nite_design_tokens.json` · **Schema:** `nite-design-tokens-1.0`

## Structure

```jsonc
{
  "$schema": "nite-design-tokens-1.0",
  "meta":    { "version", "frozen", "freezeDate", "canonicalSpec", "changeControl" },
  "layers": {
    "global":         { "<dotted.token>": TokenEntry },   // frozen identity
    "semantic":       { "<token>": { "aliasOf": "nite.<global-token>" } },
    "productAliases": { "<token>": { "aliasOf": "nite.* | raw:#RRGGBB", ...metadata } },
    "component":      { "<token>": TokenEntry },
    "accentBudget":   { "<context>": { "minPct", "maxPct", "notes" } }
  }
}
```

## TokenEntry types

| type      | fields                                   | example |
|-----------|------------------------------------------|---------|
| `color`     | `value` (#RRGGBB), optional `alpha`, `contrastOnBase`, `redundantEncoding[]`, `spec` | `color.interactive.base` |
| `dimension` | `value` (px), `unit`                     | `space.m = 12` |
| `duration`  | `value` (ms int), `use`                  | `motion.fast.duration = 120` |
| `opacity`   | `value` ∈ (0,1]                          | `opacity.dimmedFocusMode = .15` |
| `fontFamily`| `stack[]`                                | `type.family.primary` |
| `flag`      | `value` bool                             | `type.numerals.tabular` |
| `easing`    | `css`, `name`                            | `motion.easing` |
| `style`     | `stroke`, `dashPattern[]`, `tag`, `handles`, `opacity` | `ai.proposal` |
| `policy`    | `rule`                                   | `motion.reducedMotionPolicy` |

## Alias rules

- Semantic tokens **must** define `aliasOf` pointing at an existing global token.
- Product aliases may target global tokens or `raw:#RRGGBB` (category palette only, per DS §6 extension rule).
- Cycles are rejected. Dangling targets are rejected.
- Category hexes must never equal a reserved semantic hue.

## Validation rules enforced (`tools/token_validator.py`)

duplicate keys · malformed hex · missing/dangling/circular aliases · numeric ranges (opacity/duration/dimension) · required SLO categories (9) · required semantic states (8) · accent-budget sanity · typography role completeness · **frozen colour snapshot drift** (any change to the 33 frozen values fails unless intentional per DS §21) · R-CVD-1 family/shape mapping · category-vs-semantic hue collision · version metadata consistency.

## Regeneration

```
python3 tools/generate_tokens.py
```

Fails closed on validation errors; otherwise rewrites `generated/cpp/NiteDesignTokens.h`, `generated/web/nite-tokens.css`, `generated/web/nite-tokens.ts` deterministically.
