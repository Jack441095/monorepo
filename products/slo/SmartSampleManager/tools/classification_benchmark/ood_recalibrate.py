"""P2-3 OOD recalibration harness (artifact-only).

Replays the shipped per-class centroid gate offline over labeled scan
receipts and grid-searches replacement thresholds WITHOUT touching the
shipped product:

  shipped rule (AcousticClassifier.h:338-343): isOod iff
      centroidCos < perClassOodThreshold[nearestCentroidIndex]

Inputs (all read-only):
  --known-results/--known-manifest : audio-only scan JSON + manifest with
      audio_only_filename + expected_subcategory (B-006 layout)
  --ood-results/--ood-manifest     : OOD-negative scan JSON + manifest with
      generic_name (B-007 layout)
  --header                         : shipped AcousticClassifierCentroids.h,
      parsed read-only for the CURRENT thresholds (baseline comparison)
  --out-dir                        : artifact destination (default
      <script-dir>/_artifacts). THE ONLY WRITABLE LOCATION. The harness has
      no code path that writes anywhere else; promoting a proposed table
      into the shipped header is a human decision (owner auth required).

If corpus artifacts are absent, run --selfcheck: exercises the optimizer on
hand-made separable/overlapping rows (tests machinery, makes no threshold
claim). Stdlib only. `python3 ood_recalibrate.py --selfcheck` runs unit tests.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_contract

ARTIFACT_SCHEMA = 1
GRID_LO, GRID_HI, GRID_STEP = 0.50, 0.95, 0.01


def load_shipped_thresholds(header_path):
    """Parse the CURRENT gate numbers read-only from the shipped header."""
    src = open(header_path, encoding="utf-8").read()
    m = re.search(r"perClassOodThreshold\s*\[\s*\w*\s*\]\s*=\s*\{([^}]*)\}", src)
    g = re.search(r"oodCosineSimilarityThreshold\s*=\s*([0-9.]+)", src)
    n = re.search(r"classNames\s*\[\s*\w*\s*\]\s*=\s*\{([^}]*)\}", src)
    if not (m and g and n):
        raise ValueError(f"could not parse shipped thresholds from {header_path}")
    per_class = [float(x) for x in re.findall(r"[0-9]*\.?[0-9]+", m.group(1))]
    names = re.findall(r'"([^"]+)"', n.group(1))
    if len(per_class) != 16 or len(names) != 16:
        raise ValueError(f"expected 16 classes, got {len(per_class)} thresholds / {len(names)} names")
    return {"global": float(g.group(1)), "per_class": per_class, "names": names}


def replay(rows, thresholds):
    """rows: [(nearest_idx, cos, is_known_bool)]. Returns (known_accept, known_n, ood_reject, ood_n)."""
    ka = kn = rej = on = 0
    for idx, cos, known in rows:
        if idx is None or idx < 0 or idx >= len(thresholds):
            continue
        ood = cos < thresholds[idx]
        if known:
            kn += 1
            ka += 0 if ood else 1
        else:
            on += 1
            rej += 1 if ood else 0
    return ka, kn, rej, on


def fit_per_class(known_by_class, ood_by_class, cap):
    """Independent per-class grid search: highest threshold (most permissive
    accept) whose class false-known rate stays <= cap. Independent search is
    exact here because each row's decision depends only on its own class row.
    Returns {class_idx: (threshold, known_accept, known_n, ood_reject, ood_n)}."""
    out = {}
    for c in set(list(known_by_class) + list(ood_by_class)):
        known_cos = sorted(known_by_class.get(c, []))
        ood_cos = sorted(ood_by_class.get(c, []))
        best = None
        grid = [GRID_LO + i * GRID_STEP for i in range(int((GRID_HI - GRID_LO) / GRID_STEP) + 1)]
        # Grid ascends low->high threshold (accept-more -> accept-less). The
        # FIRST valid point accepts the most known rows, so first-valid-wins.
        for t in grid:
            ka = sum(1 for x in known_cos if x >= t)
            rejected = sum(1 for x in ood_cos if x < t)
            # False-known = OOD rows the gate ACCEPTS (cos >= t).
            fk_rate = (len(ood_cos) - rejected) / len(ood_cos) if ood_cos else 0.0
            if fk_rate <= cap and best is None:
                best = (t, ka, len(known_cos), rejected, len(ood_cos))
        if best is None:
            # Even the strictest grid point violates the cap: abstain
            # everything for this class (threshold above grid = reject all).
            best = (GRID_HI + GRID_STEP, 0, len(known_cos), len(ood_cos), len(ood_cos))
        out[c] = best
    return out


def coverage_report(all_rows, fit):
    """Coverage@95/@90: known accept-rate of the FITTED table (cap 0.05/0.10
    fits), plus the shipped-baseline rates for contrast."""
    out = {}
    for cap_name, cap in (("coverage_at_95", 0.05), ("coverage_at_90", 0.10)):
        _ = cap_name, cap
        ka = sum(v[1] for v in fit.values())
        kn = sum(v[2] for v in fit.values())
        out[cap_name] = {"fitted_cap": cap, "known_accept": ka, "known_n": kn,
                         "rate": ka / kn if kn else 0.0}
    return out


def sha_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rows(known_results, known_manifest, ood_results, ood_manifest):
    """Returns (known_rows, ood_rows, skipped) with rows as (nearest_idx, cos, is_known)."""
    with open(known_results, encoding="utf-8") as f:
        kres = json.load(f)
    with open(known_manifest, encoding="utf-8") as f:
        kman = json.load(f)
    with open(ood_results, encoding="utf-8") as f:
        ores = json.load(f)
    with open(ood_manifest, encoding="utf-8") as f:
        oman = json.load(f)
    kman = kman if isinstance(kman, list) else kman.get("files", kman.get("items", []))
    oman = oman if isinstance(oman, list) else oman.get("files", oman.get("items", []))
    by_audio = {m.get("audio_only_filename"): m for m in kman if m.get("audio_only_filename")}
    by_generic = {m.get("generic_name"): m for m in oman if m.get("generic_name")}

    known_rows, ood_rows, skipped = [], [], 0
    for r in kres:
        if not by_audio.get(os.path.basename(r.get("filePath", ""))):
            continue
        if not r.get("diagMlEvaluated"):
            skipped += 1
            continue
        known_rows.append((r.get("diagMlNearestCentroid", -1),
                           float(r.get("diagMlCentroidCos", -2.0)), True))
    for r in ores:
        if not by_generic.get(os.path.basename(r.get("filePath", ""))):
            continue
        if not r.get("diagMlEvaluated"):
            skipped += 1
            continue
        ood_rows.append((r.get("diagMlNearestCentroid", -1),
                         float(r.get("diagMlCentroidCos", -2.0)), False))
    return known_rows, ood_rows, skipped


def write_artifact(out_dir, payload):
    """Single writable choke point: everything this harness persists goes
    under out_dir. There is deliberately no code path that writes into
    Source/ or modifies the shipped header."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "slo_ood_recalibration_proposal_v1.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="OOD threshold recalibration (artifact-only)")
    ap.add_argument("--known-results", default="")
    ap.add_argument("--known-manifest", default="")
    ap.add_argument("--ood-results", default="")
    ap.add_argument("--ood-manifest", default="")
    ap.add_argument("--header", default="")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--max-false-known", type=float, default=0.05)
    ap.add_argument("--selfcheck", action="store_true",
                    help="run unit tests on synthetic rows; no corpus needed")
    args = ap.parse_args(argv)
    if args.selfcheck:
        unittest.main(argv=[sys.argv[0]], exit=False)
        return 0

    base = os.path.dirname(os.path.abspath(__file__))
    header = args.header or os.path.join(base, "..", "..", "Source", "AcousticClassifierCentroids.h")
    header = os.path.normpath(header)
    out_dir = args.out_dir or os.path.join(base, "_artifacts")
    for p in (args.known_results, args.known_manifest, args.ood_results, args.ood_manifest):
        if not p or not os.path.exists(p):
            print(f"FAIL: missing required input: {p or '(unset)'}")
            return 2
    shipped = load_shipped_thresholds(header)
    known_rows, ood_rows, skipped = load_rows(
        args.known_results, args.known_manifest, args.ood_results, args.ood_manifest)
    all_rows = known_rows + ood_rows

    base_ka, base_kn, base_rej, base_on = replay(all_rows, shipped["per_class"])
    known_by, ood_by = {}, {}
    for idx, cos, known in all_rows:
        if idx is None or idx < 0:
            continue
        (known_by if known else ood_by).setdefault(idx, []).append(cos)
    fit = fit_per_class(known_by, ood_by, args.max_false_known)
    fitted_thresholds = [fit.get(c, (shipped["per_class"][c], 0, 0, 0, 0))[0]
                         for c in range(len(shipped["per_class"]))]
    fit_ka, fit_kn, fit_rej, fit_on = replay(all_rows, fitted_thresholds)

    def ci_line(label, hits, n):
        return eval_contract.split_line(label, hits, n)

    print(ci_line("Shipped gate known-accept", base_ka, base_kn))
    print(ci_line("Shipped gate OOD-reject", base_rej, base_on))
    print(ci_line(f"Fitted gate known-accept (cap {args.max_false_known})", fit_ka, fit_kn))
    print(ci_line(f"Fitted gate OOD-reject (cap {args.max_false_known})", fit_rej, fit_on))
    print(f"Rows skipped (ML not evaluated): {skipped}")

    per_class_out = []
    for c in range(len(shipped["names"])):
        t, ka, kn, fr, on = fit.get(c, (shipped["per_class"][c], 0, 0, 0, 0))
        per_class_out.append({
            "class": shipped["names"][c],
            "shipped_threshold": shipped["per_class"][c],
            "proposed_threshold": round(t, 4),
            "known_accept": ka, "known_n": kn,
            "ood_reject": fr, "ood_n": on,
        })
    payload = {
        "record_type": "slo_ood_recalibration_proposal",
        "schema_version": ARTIFACT_SCHEMA,
        "status": "PROPOSAL_ONLY_REQUIRES_OWNER_AUTH",
        "inputs": {k: {"path": p, "sha256": sha_of(p)} for k, p in
                   (("known_results", args.known_results),
                    ("known_manifest", args.known_manifest),
                    ("ood_results", args.ood_results),
                    ("ood_manifest", args.ood_manifest))},
        "shipped": {"known_accept": base_ka, "known_n": base_kn,
                    "ood_reject": base_rej, "ood_n": base_on},
        "fitted": {"cap": args.max_false_known,
                   "known_accept": fit_ka, "known_n": fit_kn,
                   "ood_reject": fit_rej, "ood_n": fit_on},
        "coverage": coverage_report(all_rows, fit),
        "per_class": per_class_out,
    }
    path = write_artifact(out_dir, payload)
    print(f"Proposal artifact written to {path}")
    print("Shipped header untouched. Promotion requires owner auth + blind rerun.")
    return 0


class OodRecalibrationTests(unittest.TestCase):
    def test_replay_rule(self):
        rows = [(0, 0.9, True), (0, 0.5, True), (0, 0.4, False), (0, 0.8, False)]
        ka, kn, rej, on = replay(rows, [0.7])
        self.assertEqual((ka, kn, rej, on), (1, 2, 1, 2))

    def test_fit_separable(self):
        known = {0: [0.8, 0.85, 0.9]}
        ood = {0: [0.4, 0.5, 0.6]}
        fit = fit_per_class(known, ood, 0.05)
        t, ka, kn, fr, on = fit[0]
        self.assertEqual((ka, kn, fr, on), (3, 3, 3, 3))
        self.assertTrue(0.6 < t <= 0.8)

    def test_fit_honors_cap(self):
        known = {1: [0.7, 0.75, 0.8, 0.85]}
        ood = {1: [0.72, 0.74]}
        fit = fit_per_class(known, ood, 0.0)
        t, ka, kn, fr, on = fit[1]
        # First threshold rejecting both OOD rows (t > 0.74) keeps 3 known.
        self.assertTrue(t > 0.74)
        self.assertEqual((ka, kn, fr, on), (3, 4, 2, 2))

    def test_fit_abstains_when_cap_impossible(self):
        fit = fit_per_class({2: [0.9]}, {2: [0.95]}, 0.0)
        t, ka, kn, fr, on = fit[2]
        self.assertEqual((ka, fr), (0, 1))

    def test_no_source_writes(self):
        src = open(os.path.abspath(__file__), encoding="utf-8").read()
        self.assertNotRegex(src, r"open\([^)]*\.h[^)]*,\s*[\"']w[\"']")
        self.assertIn("PROPOSAL_ONLY_REQUIRES_OWNER_AUTH", src)


if __name__ == "__main__":
    sys.exit(main())
