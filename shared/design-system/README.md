# NITE DSP Design System — Implementation Foundation

Engineering foundation for **NITE DSP Design System 1.0 (EMBER — Warm Technical Minimalism)**.
Isolated workspace: no SLO / KENN / website production code is modified here.

## Quick start

```bash
# validate canonical tokens (frozen snapshot + structure rules)
python3 tools/token_validator.py

# regenerate C++/CSS/TS artifacts (deterministic; fails closed on validation errors)
python3 tools/generate_tokens.py

# run full test suite
python3 -m pytest tests/ -q

# compile-check the C++ adapter (no JUCE required)
clang++ -std=c++17 -Wall -Wextra -I. -Igenerated/cpp tmp/adapter_smoke_test.cpp -o tmp/adapter_smoke_test
```

## Layout

See `docs/DESIGN_SYSTEM_IMPLEMENTATION_ARCHITECTURE.md` for the full map.

| Path | Role |
|---|---|
| `tokens/nite_design_tokens.json` | Canonical token source (frozen values) |
| `tools/` | Validator, generators, localisation runtime, MAP shape grammar |
| `generated/` | Derived artifacts — never hand-edit |
| `cpp/` | JUCE-facing adapter + LookAndFeel foundation |
| `icons/` | Semantic SVG icon set (1.5px stroke, 16 grid) |
| `localisation/` | `strings_en.json` base bundle |
| `docs/` | Architecture, schema, runtime spec, component matrix, migration plans |

## Rules

1. The frozen spec (`../design_prototypes/ember/NITE_DSP_DESIGN_SYSTEM_V1.md`) is authoritative.
2. Hardcoded hex in product code = review failure; consume tokens only.
3. Frozen value changes require explicit version bump per DS §21 — validation enforces this.
4. No production migration starts from this repo without owner authorisation.
