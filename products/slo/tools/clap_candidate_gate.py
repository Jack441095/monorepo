"""CLAP-music+DSP candidate promotion gate (task C, post-beta).

Enforces SLO_ENCODER_RESEARCH_DECISION_2026-09-15's 7 promotion gates
before the CLAP candidate may replace the frozen Beta-1 PANNs+DSP path:
 1. vendor/pack-grouped blind evaluation (no row-stratified leakage)
 2. no material class regression + CIs for low-support classes
 3. Python <-> C++ exported-model numerical parity
 4. signed Release measurements (size, cold start, latency, RSS, CPU, host)
 5. redistribution-license approval
 6. OOD/Unknown calibration within false-confident-error limits
 7. immutable candidate + rollback plan (no in-place replacement)

Usage:
    python3 clap_candidate_gate.py --results results.json
    python3 clap_candidate_gate.py --checklist   # print gate status template

results.json schema:
{
  "vendor_grouped": true,
  "per_class": {"Kick": {"f1_base": 0.90, "f1_cand": 0.91, "support": 400}, ...},
  "max_regression_pp": 1.0,
  "parity_max_abs_err": 1e-5,
  "release_measurements_signed": true,
  "license_approved": true,
  "ood_false_confident_rate": 0.01,
  "ood_false_confident_limit": 0.02,
  "rollback_plan": true
}
Exit 0 = all gates pass, 1 = blocked (reasons printed).
"""
from __future__ import annotations

import argparse
import json
import sys

GATES = [
    "vendor_grouped",
    "no_regression",
    "parity",
    "release_measurements",
    "license",
    "ood",
    "rollback",
]


def evaluate(results: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not results.get("vendor_grouped") is True:
        failures.append("gate1 vendor/pack-grouped blind eval missing "
                        "(row-stratified splits leak same-pack duplicates)")
    per_class = results.get("per_class", {})
    limit_pp = float(results.get("max_regression_pp", 1.0))
    regressions = [
        f"{cls} {v['f1_base'] * 100:.1f}->{v['f1_cand'] * 100:.1f}"
        for cls, v in per_class.items()
        if (v["f1_base"] - v["f1_cand"]) * 100 > limit_pp
    ]
    if regressions:
        failures.append(f"gate2 class regressions > {limit_pp}pp: "
                        + "; ".join(regressions))
    low_support = [c for c, v in per_class.items() if v.get("support", 0) < 40]
    if low_support and "ci_reported" not in results:
        failures.append(f"gate2 low-support classes need CIs, not point "
                        f"estimates: {', '.join(low_support)}")
    if float(results.get("parity_max_abs_err", 1.0)) > 1e-5:
        failures.append("gate3 Python<->C++ parity max abs err exceeds 1e-5")
    if not results.get("release_measurements_signed"):
        failures.append("gate4 signed Release measurements missing "
                        "(size, cold start, latency, RSS, CPU, host)")
    if not results.get("license_approved"):
        failures.append("gate5 redistribution-license approval missing")
    if float(results.get("ood_false_confident_rate", 1.0)) > float(
            results.get("ood_false_confident_limit", 0.02)):
        failures.append("gate6 OOD false-confident rate over limit")
    if not results.get("rollback_plan"):
        failures.append("gate7 immutable candidate + rollback plan missing")
    return (not failures, failures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="")
    ap.add_argument("--checklist", action="store_true")
    args = ap.parse_args()
    if args.checklist:
        print("CLAP candidate promotion gates (all must pass):")
        for i, gate in enumerate(GATES, 1):
            print(f"  gate{i} {gate}: PENDING")
        return 0
    if not args.results:
        print("usage: clap_candidate_gate.py --results results.json", file=sys.stderr)
        return 2
    results = json.loads(open(args.results).read())
    ok, failures = evaluate(results)
    if ok:
        print("CLAP candidate: ALL GATES PASS")
        return 0
    print("CLAP candidate: BLOCKED")
    for failure in failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
