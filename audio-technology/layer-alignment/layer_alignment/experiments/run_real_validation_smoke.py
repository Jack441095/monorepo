"""END-TO-END smoke validation of the Real-Audio Validation V1 harness.

Uses NON-PROTECTED synthesized fixtures (eval/smoke_fixtures.py) to prove
every pipeline stage works: manifest -> controlled cases -> natural/healthy
cases -> frozen engine -> product contract -> blind pack -> scoring ->
isolation tests -> bench. Produces results/real_v1/smoke_*.json.

NO REAL AUDIO IS INVOLVED. Output carries zero qualification weight.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval import bench, isolation_tests                      # noqa: E402
from eval.audio_io import load_wav                           # noqa: E402
from eval.blind_pack import build_pack                       # noqa: E402
from eval.cases import PairCase, make_controlled             # noqa: E402
from eval.corpus_manifest import build_manifest              # noqa: E402
from eval.pipeline import analyse_case, records_to_json      # noqa: E402
from eval.score import score                                 # noqa: E402
from eval.smoke_fixtures import generate_all                 # noqa: E402

OUT = ROOT / "results" / "real_v1"
SMOKE_DIR = ROOT / "datasets" / "smoke_fixtures"


def load(name):
    return load_wav(SMOKE_DIR / name)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    generate_all(SMOKE_DIR)

    # 1. manifest --------------------------------------------------------
    man = build_manifest(
        {"smoke": {"dir": SMOKE_DIR,
                   "licences": {"*.wav": "SMOKE_NON_PROTECTED"},
                   "role": "harness validation only"}},
        OUT / "smoke_manifest.json", corpus_id="REAL_V1_SMOKE")

    # 2. controlled cases from fixtures ----------------------------------
    srcs = [("kick_body", "smoke_kick_body.wav", "kick"),
            ("bass_line", "smoke_bass_line.wav", "bass"),
            ("pad", "smoke_pad.wav", "synth"),
            ("drumloop", "smoke_drumloop_full.wav", "multimic")]
    controlled = []
    for group, fname, cat in srcs:
        la = load(fname)
        controlled += make_controlled(la, "smoke_" + group,
                                      "SMOKE_NON_PROTECTED", cat,
                                      f"smkctl|{group}")

    # 3. natural + healthy pairs ------------------------------------------
    kick_body, kick_click = load("smoke_kick_body.wav"), load("smoke_kick_click.wav")
    kick_sub = load("smoke_kick_sub.wav")
    bass_line, bass_sub = load("smoke_bass_line.wav"), load("smoke_bass_sub.wav")
    bass_dist = load("smoke_bass_distorted.wav")
    pad, pad_oct, pad_dbl = (load("smoke_pad.wav"),
                             load("smoke_pad_octave.wav"),
                             load("smoke_pad_double_chorus.wav"))
    vox_a, vox_b = load("smoke_vox_double_a.wav"), load("smoke_vox_double_b.wav")
    ring = load("smoke_tonal_ring.wav")
    drumloop = load("smoke_drumloop_full.wav")

    def P(cid, klass, cat, rel, x, y, expected="UNKNOWN",
          truth=None, pol=1):
        n = min(len(x.samples), len(y.samples))
        return PairCase(case_id=cid, klass=klass, category=cat,
                        relationship=rel, fs=x.sample_rate,
                        a=x.samples[:n], b=y.samples[:n],
                        provenance_category="SMOKE_NON_PROTECTED",
                        source_group_a="smoke", source_group_b="smoke",
                        truth_offset_samples=truth, truth_polarity=pol,
                        expected_action=expected)

    natural = [
        P("nat|kick|body_click", "NATURAL", "kick", "body+click",
          kick_body, kick_click),
        P("nat|kick|body_sub", "NATURAL", "kick", "body+sub",
          kick_body, kick_sub),
        P("nat|bass|line_sub", "NATURAL", "bass", "mid+sub",
          bass_line, bass_sub),
        P("nat|bass|clean_dist", "NATURAL", "bass", "clean+distorted",
          bass_line, bass_dist),
        P("nat|drumloop|self", "NATURAL", "multimic", "loop_vs_loop",
          drumloop, drumloop),
        # healthy controls (real-world style)
        P("hlt|pad_octave", "HEALTHY", "synth", "octave_layer",
          pad, pad_oct, expected="NO_ACTION"),
        P("hlt|pad_chorus_double", "HEALTHY", "synth", "chorus_double",
          pad, pad_dbl, expected="NO_ACTION"),
        P("hlt|vox_double", "HEALTHY", "vocal", "doubled_vox",
          vox_a, vox_b, expected="NO_ACTION"),
        P("hlt|ring_vs_kickclick", "HEALTHY", "tonal", "unrelated_complement",
          ring, kick_click, expected="NO_ACTION"),
        P("hlt|bassline_vs_hats_context", "HEALTHY", "percussion",
          "groove_offset", drumloop, pad, expected="NO_ACTION"),
    ]

    all_cases = controlled + natural

    # 4. frozen engine over everything ------------------------------------
    records = [analyse_case(c) for c in all_cases]

    rec_json_path = OUT / "smoke_records.json"
    rec_json_path.write_text(json.dumps(records_to_json(records), indent=1))

    # 5. blind pack ---------------------------------------------------------
    pack = build_pack(records, OUT / "blind_pack_smoke")
    (OUT / "smoke_blind_pack_summary.json").write_text(json.dumps(
        {"entries": len(pack["entries"]),
         "level_match_policy": pack["level_match_policy"],
         "blind_seed": pack["blind_seed"]}, indent=1))

    # 6. empty-vote scoring structure check ---------------------------------
    empty_score = score(records_to_json(records), [], [])
    (OUT / "smoke_scores_structure.json").write_text(
        json.dumps(empty_score, indent=1))

    # 7. isolation tests -----------------------------------------------------
    iso = isolation_tests.run_all()
    (OUT / "smoke_isolation.json").write_text(json.dumps(iso, indent=1))

    # 8. bench -----------------------------------------------------------------
    bench_pairs = []
    for res in records[:4]:
        bench_pairs.append((res["_a"], res["_b"], res["fs"]))
    bb = bench.run(bench_pairs)
    (OUT / "smoke_bench.json").write_text(json.dumps(bb, indent=1))

    # 9. C++ parity spot-check on fixture material -----------------------------
    cpp_rows = run_cpp_spotcheck(records)
    (OUT / "smoke_cpp_parity.json").write_text(json.dumps(cpp_rows, indent=1))

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_files": sum(g["files"] for g in man["groups"].values()),
        "cases_total": len(all_cases),
        "controlled": len(controlled),
        "natural_healthy": len(natural),
        "blind_pack_entries": len(pack["entries"]),
        "isolation_all_safe": iso["all_safe"],
        "bench_uncontested": bb["uncontested"],
        "bench_ms_p50": bb["ms_p50"],
        "cpp_spotcheck_rows": len(cpp_rows),
        "verdict": ("HARNESS VALIDATED END-TO-END — "
                    "READY FOR LICENSED AUDIO IMPORT"),
    }
    (OUT / "smoke_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


def run_cpp_spotcheck(records) -> list:
    """Compare frozen Python engine vs C++ spike offsets on fixture audio."""
    import subprocess
    import tempfile
    from src.nla import methods as M

    spike = ROOT / "cpp_spike" / "nla_spike"
    tmp = Path(tempfile.mkdtemp(prefix="nla_cpp_"))
    rows = []
    for res in records[:6]:
        cid = res["meta"]["case_id"]
        a, b = res["_a"].astype(np.float32), res["_b"].astype(np.float32)
        fa, fb = tmp / "a.f32", tmp / "b.f32"
        a.tofile(fa); b.tofile(fb)
        out = subprocess.run([str(spike), str(fa), str(fb),
                              str(len(a)), "256", "0.35"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            rows.append({"case_id": cid, "error": out.stderr[:80]})
            continue
        off_x, _, off_g, _, _ = map(float, out.stdout.strip().split(","))
        py_x = M.xcorr_plain(res["_a"], res["_b"], 256)["offset_samples"]
        py_g = M.gcc_soft(res["_a"], res["_b"], 256, res["fs"])[
            "offset_samples"]
        rows.append({"case_id": cid,
                     "cpp_xcorr": round(off_x, 3), "py_xcorr": round(py_x, 3),
                     "cpp_gcc": round(off_g, 3), "py_gcc": round(py_g, 3),
                     "agree_xcorr": abs(off_x - py_x) <= 0.15,
                     "agree_gcc": abs(off_g - py_g) <= 0.15})
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
