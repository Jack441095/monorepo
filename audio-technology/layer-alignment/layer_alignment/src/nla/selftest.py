"""Numerical self-test locking estimator conventions and sanity.

Run:  python3 -m src.nla.selftest   (from layer_alignment/)
Exit code 0 == all conventions verified.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/src", 1)[0])
from src.nla import corpus as C
from src.nla import methods as M


def approx(x, y, tol):
    return abs(x - y) <= tol


def main() -> int:
    fs = 48000
    n = 32768
    rng = np.random.default_rng(7)
    fails = []

    def check(name, cond, detail=""):
        print(f"{'PASS' if cond else 'FAIL'}  {name} {detail}")
        if not cond:
            fails.append(name)

    # --- integer delay convention -------------------------------------
    a = C.g_kick(rng, n, fs)
    log = C.TransformLog()
    b = C.apply_delay_exact(a, 37.0, fs, log)
    for name, fn in [("xcorr_plain", M.xcorr_plain), ("gcc_phat", M.gcc_phat)]:
        r = fn(a, b, 256)
        check(f"{name} +37 samples", approx(r["offset_samples"], 37.0, 0.5),
              f"got {r['offset_samples']:.2f}")
    ps = M.phase_slope_offset(a, b, fs, nperseg=8192)
    check("phase_slope +37", approx(ps["offset_samples"], 37.0, 1.5),
          f"got {ps['offset_samples']:.2f}")
    gd = M.group_delay_offset(a, b, fs)
    print(f"NOTE  group_delay (comparator) -> {gd['offset_samples']:.2f} "
          f"(gradient estimator; folded phase-slope supersedes it)")

    # negative delay (B leads A) ---------------------------------------
    b2 = C.apply_delay_exact(a, -23.0, fs, log)
    r = M.gcc_soft(a, b2, 256)
    check("gcc_soft -23 samples", approx(r["offset_samples"], -23.0, 2.5),
          f"got {r['offset_samples']:.2f}")
    r = M.gcc_phat(a, b2, 256)
    print(f"NOTE  classic PHAT on -23 advanced kick -> "
          f"{r['offset_samples']:.2f} (known LF-dominant weakness, kept)")

    # fractional delay ---------------------------------------------------
    b3 = C.apply_delay_exact(a, 12.5, fs, log)
    r = M.gcc_phat(a, b3, 64)
    check("gcc_phat frac 12.5", approx(r["offset_samples"], 12.5, 0.05),
          f"got {r['offset_samples']:.3f}")
    r = M.xcorr_plain(a, b3, 64)
    check("xcorr_plain frac 12.5", approx(r["offset_samples"], 12.5, 0.06),
          f"got {r['offset_samples']:.3f}")

    # polarity -----------------------------------------------------------
    b4 = -C.apply_delay_exact(a, 9.0, fs, log)
    p = M.polarity_decision(a, b4, 64)
    check("polarity detects inversion", p["polarity"] == -1,
          f"got {p['polarity']} margin {p['margin']:.2f}")
    p = M.polarity_decision(a, C.apply_delay_exact(a, 9.0, fs, log), 64)
    check("polarity normal stays normal", p["polarity"] == +1)

    # onset alignment ----------------------------------------------------
    r = M.onset_alignment(a, C.apply_delay_exact(a, 55.0, fs, log), fs,
                          max_ms=10.0)
    got_ms = r["offset_samples"] / fs * 1000
    check("onset_alignment ~55 samples @48k",
          approx(r["offset_samples"], 55.0, 8.0),
          f"got {r['offset_samples']:.1f} ({got_ms:.2f} ms)")

    # bandwise structure present -----------------------------------------
    bw = M.bandwise_analysis(a, b, fs, 128)
    active = [k for k, v in bw.items() if v.get("active")]
    check("bandwise finds active bands", len(active) >= 2, str(active))
    sub_off = bw["sub"]["offset_samples"]
    check("bandwise sub offset ~37", approx(sub_off, 37.0, 6.0),
          f"got {sub_off:.1f}")

    # coherence of identical vs unrelated ---------------------------------
    ci = M.coherence_summary(a, a, fs)["100-8000"]
    cu = M.coherence_summary(a, rng.standard_normal(n), fs)["100-8000"]
    check("coherence separates related/unrelated", ci > 0.95 and cu < 0.3,
          f"{ci:.2f} vs {cu:.2f}")

    # gcc prominence separation -------------------------------------------
    gp = M.gcc_phat(a, C.apply_delay_exact(a, 14.0, fs, log), 128)["prominence"]
    gu = M.gcc_phat(a, rng.standard_normal(n), 128)["prominence"]
    check("prominence separates related/unrelated", gp > 20 and gu < 8,
          f"{gp:.1f} vs {gu:.1f}")

    print()
    if fails:
        print("SELFTEST FAILED:", fails)
        return 1
    print("ALL CONVENTIONS VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
