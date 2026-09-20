#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

JSON_PATH="${1:-artifacts/datasets/live_melody/primary/emotion_diagnostics.json}"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

python3 - "$JSON_PATH" <<'PY'
import json, os, sys

p = sys.argv[1]
if not os.path.isfile(p):
    print(f"missing: {p}")
    sys.exit(2)

d = json.load(open(p, "r", encoding="utf-8"))
print("json:", p)
print("path:", d.get("path"))
print("rows_with_melody:", d.get("rows_with_melody"))
em = d.get("emotions", {}) or {}
print("emotion_count:", len(em))
print("")

for name in ["neutral", "realization", "embarrassment", "gratitude", "desire", "grief", "admiration", "annoyance", "confusion", "pride", "amusement", "optimism"]:
    m = em.get(name)
    if not m:
        continue
    warn = ", ".join(m.get("warnings", [])) if m.get("warnings") else "ok"
    print(
        f"{name:15s}"
        f" rows={int(m.get('rows',0)):4d}"
        f" short={float(m.get('short_duration_rate',0.0)):.3f}"
        f" long={float(m.get('long_duration_rate',0.0)):.3f}"
        f" static_run={int(m.get('static_run_max',0) or 0)}"
        f" warn={warn}"
    )
PY

