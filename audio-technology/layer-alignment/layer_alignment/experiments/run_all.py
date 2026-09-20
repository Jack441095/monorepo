"""Run all experiment families; JSON results to results/.

Usage: python3 experiments/run_all.py [family ...]
Families: offset_sweep subsample polarity phase_filters band_dispersion
          transient kick snare bass parallel samplerate healthy adversarial
          bakeoff performance
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import signal as sps


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.nla import corpus as C          # noqa: E402
from src.nla import methods as M         # noqa: E402
from src.nla import interaction as I     # noqa: E402
from src.nla import decision as D        # noqa: E402
from src.nla import scenarios as S       # noqa: E402

RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

EPS = 1e-12

KINDS = ["impulse", "sine", "multisine", "noise", "bandnoise", "kick",
         "snare_body", "snare_noise", "bass_transient", "bass_sustained",
         "synth_transient"]


def save(name: str, payload) -> Path:
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps(payload, indent=1))
    print(f"saved {p}")
    return p


# ---------------------------------------------------------------- helpers

def est_errors(a, b, fs, truth, max_lag=256):
    """Offset error per estimator (signed estimate - truth)."""
    out = {}
    out["xcorr_plain"] = M.xcorr_plain(a, b, min(max_lag, 512))["offset_samples"]
    out["gcc_phat"] = M.gcc_phat(a, b, max_lag, fs)["offset_samples"]
    out["gcc_soft"] = M.gcc_soft(a, b, max_lag, fs)["offset_samples"]
    out["phase_slope"] = M.phase_slope_offset(a, b, fs)["offset_samples"]
    out["group_delay"] = M.group_delay_offset(a, b, fs)["offset_samples"]
    return {k: float(v - truth) for k, v in out.items()}


def mae_stats(errs):
    e = np.asarray(errs, dtype=float)
    return {"n": int(e.size), "mae": float(np.mean(np.abs(e))),
            "median_ae": float(np.median(np.abs(e))),
            "p95_ae": float(np.percentile(np.abs(e), 95)),
            "bias": float(np.mean(e)),
            "within_0.5": float(np.mean(np.abs(e) <= 0.5)),
            "within_2": float(np.mean(np.abs(e) <= 2.0))}


# ---------------------------------------------------------- 1. offset sweep

def exp_offset_sweep():
    fs, n = 48000, 32768
    offsets = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256,
               -1, -2, -4, -8, -16, -32, -64, -128, -256]
    rows = []
    for kind in KINDS:
        for off in offsets:
            for snr in (None, 20.0, 6.0):
                cid = f"sw|{kind}|{off}|{snr}"
                case = S.simple_delay_case(kind, None, fs, n, cid, float(off),
                                           snr_db=snr)
                errs = est_errors(case.a, case.b, fs, float(off))
                rows.append({"case": cid, "kind": kind, "offset": off,
                             "snr_db": snr, **{f"err_{k}": v for k, v in errs.items()}})
    agg = {}
    for method in ("xcorr_plain", "gcc_phat", "gcc_soft", "phase_slope",
                   "group_delay"):
        per_kind = {}
        for kind in KINDS:
            errs = [r[f"err_{method}"] for r in rows if r["kind"] == kind]
            per_kind[kind] = mae_stats(errs)
        agg[method] = {
            "overall": mae_stats([r[f"err_{method}"] for r in rows]),
            "per_kind": per_kind,
            "by_abs_offset": {str(o): mae_stats(
                [r[f"err_{method}"] for r in rows if abs(r["offset"]) == o])
                for o in sorted({abs(x['offset']) for x in rows})},
            "by_snr": {str(s): mae_stats(
                [r[f"err_{method}"] for r in rows if r["snr_db"] == s])
                for s in (None, 20.0, 6.0)},
        }
    save("offset_sweep", {"rows": rows, "aggregate": agg})
    return agg


# ------------------------------------------------------------ 2. sub-sample

def exp_subsample():
    fs, n = 48000, 32768
    fracs = np.arange(-4.0, 4.01, 0.25)
    rows = []
    for kind in ("kick", "bass_transient", "multisine", "bandnoise",
                 "synth_transient", "snare_body"):
        for frac in fracs:
            cid = f"sub|{kind}|{frac}"
            case = S.simple_delay_case(kind, None, fs, n, cid, float(frac))
            errs = est_errors(case.a, case.b, fs, float(frac), max_lag=64)
            # parabolic-interpolated plain xcorr is inside xcorr_plain already;
            # add pure integer-rounded baseline:
            errs_int = errs["xcorr_plain"]
            rows.append({"case": cid, "kind": kind, "frac": float(frac),
                         "err_xcorr_parabolic": errs_int,
                         "err_gcc_phat": errs["gcc_phat"],
                         "err_gcc_soft": errs["gcc_soft"],
                         "err_phase_slope": errs["phase_slope"]})
    methods = ("xcorr_parabolic", "gcc_phat", "gcc_soft", "phase_slope")
    agg = {m: mae_stats([r[f"err_{m}"] for r in rows]) for m in methods}
    save("subsample", {"rows": rows, "aggregate": agg})
    return agg


# --------------------------------------------------------------- 3. polarity

def exp_polarity():
    fs, n = 48000, 32768
    variants = [
        ("identical", lambda rng, n, fs: (C.SIGNAL_GENERATORS["kick"](rng, n, fs), None)),
        ("partial", None),
        ("filtered", None),
        ("distorted", None),
        ("diff_envelope", None),
    ]
    rows = []
    kinds = ("kick", "snare_body", "bass_transient", "multisine",
             "synth_transient")
    for kind in kinds:
        for v in ("identical", "partial", "filtered", "distorted",
                  "diff_envelope"):
            for flip in (1, -1):
                for rep in range(3):
                    cid = f"pol|{kind}|{v}|{flip}|{rep}"
                    rng = np.random.default_rng(C.case_seed(cid))
                    log = C.TransformLog()
                    a = C.SIGNAL_GENERATORS[kind](rng, n, fs)
                    b = a.copy()
                    if v == "identical":
                        pass
                    elif v == "partial":
                        nz = C.g_bandnoise(rng, n, fs)
                        b = 0.7 * a + 0.5 * nz / np.max(np.abs(nz))
                    elif v == "filtered":
                        rng2 = np.random.default_rng(C.case_seed(cid + "|f"))
                        b = C.apply_minphase_eq(b, fs, rng2, log)
                    elif v == "distorted":
                        b = C.apply_distortion(b, 4.0, log)
                    elif v == "diff_envelope":
                        t = np.arange(n) / fs
                        env = np.exp(-t / 0.02) + 0.3 * np.exp(-t / 0.15)
                        b = a * env / np.max(env)
                    d = float(rng.integers(3, 30))
                    b = C.apply_delay_exact(b, d, fs, log)
                    b = C.apply_polarity(b, flip == -1, log)
                    pol = M.polarity_decision(a, b, 128)
                    correct = pol["polarity"] == flip
                    rows.append({"case": cid, "kind": kind, "variant": v,
                                 "flip": flip, "correct": bool(correct),
                                 "margin": pol["margin"],
                                 "err_offset": pol["offset_samples"] - d})
    acc = {}
    for v in ("identical", "partial", "filtered", "distorted",
              "diff_envelope"):
        sel = [r for r in rows if r["variant"] == v]
        acc[v] = {"accuracy": float(np.mean([r["correct"] for r in sel])),
                  "n": len(sel)}
    overall = float(np.mean([r["correct"] for r in rows]))
    save("polarity", {"rows": rows, "accuracy_by_variant": acc,
                      "accuracy_overall": overall})
    return {"overall": overall, "by_variant": acc}


# ------------------------------------------- 4. frequency-dependent phase

def _residual_cancellation(a, b_aligned, fs):
    """How much cancellation is still available after alignment."""
    inter = I.band_interactions(a, b_aligned, fs)
    return inter


def exp_phase_filters():
    fs, n = 48000, 32768
    modes = ["minphase_eq", "allpass", "lr4_crossover", "linear_phase_eq",
             "mic_tf"]
    rows = []
    for kind in ("kick", "bass_transient", "multisine", "bass_sustained",
                 "synth_transient"):
        for mode in modes:
            for rep in range(4):
                cid = f"phf|{kind}|{mode}|{rep}"
                case = S.filtered_phase_case(kind, fs, n, cid, mode)
                a, b = case.a, case.b
                # window must cover processing-embedded latency
                feat = D.analyze_pair(a, b, fs,
                                      max_lag=max(256, int(abs(
                                          case.spec.truth_offset_samples)) +
                                          64))
                d_hat = feat["estimates"]["gcc_soft"]

                def sum_gain(x, y):
                    e_ind = float(np.sum(x ** 2) + np.sum(y ** 2)) + EPS
                    return float(10 * np.log10(
                        float(np.sum((x + y) ** 2)) / e_ind + EPS))

                g_before = sum_gain(a, b)
                y_delay = I.apply_alignment(b, d_hat, fs)
                g_after_delay = sum_gain(a, y_delay)
                # ideal per-bin phase-conjugate correction (upper bound):
                # force B's spectrum into A's phase, preserving |B|
                nfft = 1 << int(np.ceil(np.log2(n)))
                A_ = np.fft.rfft(a, nfft)
                B_ = np.fft.rfft(b, nfft)
                R = A_ * np.conj(B_)
                B_corr = B_ * R / (np.abs(R) + EPS)
                b_ideal = np.fft.irfft(B_corr, nfft)[:n]
                g_after_ideal = sum_gain(a, b_ideal)
                bands = M.bandwise_analysis(a, b, fs, 128)
                band_off = {k: v.get("offset_samples")
                            for k, v in bands.items() if v.get("active")}
                spread = (max(band_off.values()) - min(band_off.values())
                          if len(band_off) >= 2 else 0.0)
                rows.append({
                    "case": cid, "kind": kind, "mode": mode,
                    "truth_extra_delay": case.spec.truth_offset_samples,
                    "d_hat": d_hat,
                    "sum_gain_before_db": g_before,
                    "sum_gain_after_bestdelay_db": g_after_delay,
                    "sum_gain_after_ideal_complex_db": g_after_ideal,
                    "delay_only_recovery_pct": float(
                        100 * (g_after_delay - g_before) /
                        (g_after_ideal - g_before + EPS)),
                    "band_offset_spread_samples": float(spread),
                    "band_offsets": band_off,
                    "coh_60_8k": feat["coh_60_8k"],
                })
    agg = {}
    for mode in modes:
        sel = [r for r in rows if r["mode"] == mode]
        agg[mode] = {
            "mean_delay_only_recovery_pct": float(np.mean(
                [r["delay_only_recovery_pct"] for r in sel])),
            "mean_band_offset_spread": float(np.mean(
                [r["band_offset_spread_samples"] for r in sel])),
            "mean_sum_gain_before": float(np.mean(
                [r["sum_gain_before_db"] for r in sel])),
            "mean_sum_gain_after_delay": float(np.mean(
                [r["sum_gain_after_bestdelay_db"] for r in sel])),
            "mean_sum_gain_ideal": float(np.mean(
                [r["sum_gain_after_ideal_complex_db"] for r in sel])),
        }
    save("phase_filters", {"rows": rows, "aggregate": agg})
    return agg


# --------------------------------------------------- 5. bandwise dispersion

def exp_band_dispersion():
    """Demonstrate band-dependent offsets under dispersive filters."""
    fs, n = 48000, 32768
    rows = []
    for mode in ("allpass", "lr4_crossover", "minphase_eq", "mic_tf"):
        for rep in range(6):
            cid = f"bd|{mode}|{rep}"
            rng = np.random.default_rng(C.case_seed(cid))
            kind = str(rng.choice(["kick", "bass_transient", "multisine"]))
            base = S.simple_delay_case(kind, None, fs, n, cid + "|base", 12.0)
            case = S.filtered_phase_case(kind, fs, n, cid, mode, delay_samples=12.0)
            bands = M.bandwise_analysis(case.a, case.b, fs, 200)
            offs = {k: v["offset_samples"] for k, v in bands.items()
                    if v.get("active")}
            rows.append({"case": cid, "mode": mode, "kind": kind,
                         "truth": 12.0,
                         "global_gcc": M.gcc_soft(case.a, case.b, 200)[
                             "offset_samples"],
                         "band_offsets": offs,
                         "spread": float(max(offs.values()) -
                                         min(offs.values()))
                         if len(offs) >= 2 else 0.0})
    agg = {}
    for mode in ("allpass", "lr4_crossover", "minphase_eq", "mic_tf"):
        sel = [r for r in rows if r["mode"] == mode]
        agg[mode] = {
            "mean_spread": float(np.mean([r["spread"] for r in sel])),
            "max_spread": float(np.max([r["spread"] for r in sel])),
        }
    save("band_dispersion", {"rows": rows, "aggregate": agg})
    return agg


# ------------------------------------------------------- 6. transient align

def exp_transient():
    fs, n = 48000, 32768
    rows = []
    for kind in ("kick", "snare_body", "snare_noise", "bass_transient",
                 "synth_transient"):
        for off in (0, 8, 21, 55, 120, -34):
            for rep in range(3):
                cid = f"tr|{kind}|{off}|{rep}"
                case = S.simple_delay_case(kind, None, fs, n, cid, float(off))
                xc = M.xcorr_plain(case.a, case.b, 256)["offset_samples"]
                on = M.onset_alignment(case.a, case.b, fs, max_ms=10.0)
                flux_a = M.spectral_flux_onsets(case.a, fs)
                flux_b = M.spectral_flux_onsets(case.b, fs)
                first_diff = (int(flux_b[0]) - int(flux_a[0])
                              if len(flux_a) and len(flux_b) else None)
                rows.append({"case": cid, "kind": kind, "truth": float(off),
                             "err_xcorr": xc - off,
                             "err_onset_env": on["offset_samples"] - off,
                             "err_first_flux_onset":
                                 (first_diff - off) if first_diff is not None
                                 else None})
    def stats(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return mae_stats(vals)
    agg = {"xcorr": stats("err_xcorr"),
           "onset_envelope": stats("err_onset_env"),
           "first_flux_onset": stats("err_first_flux_onset")}
    save("transient", {"rows": rows, "aggregate": agg})
    return agg


# --------------------------------------------------------- 7. kick layers

def exp_kick_layers():
    fs, n = 48000, 32768
    rows = []
    grid = [(0, 0, 0), (14, 14, 14), (-23, -23, -23), (37, 37, 37),
            (0, 14, -14), (23, 0, -23), (64, 64, 64)]
    for overlap in (True, False):
      for polarities in ((1, 1, 1), (-1, 1, 1), (1, -1, 1), (-1, -1, -1)):
        for offs in grid:
            for pitch in ((1.0, 1.0, 1.0), (0.9, 1.15, 1.0)):
                for envs in ((1.0, 1.0, 1.0), (1.5, 0.7, 1.0)):
                    cid = f"kick|{overlap}|{polarities}|{offs}|{pitch}|{envs}"
                    case = S.kick_layer_stack(fs, n, cid, offs, polarities,
                                              pitch, envs, overlap=overlap)
                    full_truth = case.a + case.b
                    rec = D.recommend(D.analyze_pair(case.a, case.b, fs, 128),
                                      case.a, case.b, fs, do_search=True,
                                      max_lag=96)
                    best = rec["suggestions"][0] if rec["suggestions"] else None
                    row = {
                        "case": cid, "overlap": overlap,
                        "truth_composite_offset": offs[1],
                        "action": rec["action"],
                        "peak_before": float(np.max(np.abs(full_truth))),
                        "low_energy_before": I.low_energy_db(full_truth, fs),
                        "interaction_sub_before":
                            I.band_interactions(case.a, case.b, fs)["sub"],
                        "crest_before": I.summary_metrics(case.a,
                                                          case.b)["crest"],
                    }
                    if best and best.get("type") == "SEARCHED":
                        y = I.apply_alignment(case.b, best["delay_samples"],
                                              fs, best["polarity"])
                        after = case.a + y
                        row.update({
                            "rec_delay": best["delay_samples"],
                            "rec_pol": best["polarity"],
                            "improvement_db": best["improvement_db"],
                            "peak_after": float(np.max(np.abs(after))),
                            "low_energy_after": I.low_energy_db(after, fs),
                            "interaction_sub_after":
                                I.band_interactions(case.a, y, fs)["sub"],
                        })
                    rows.append(row)
    save("kick_layers", {"rows": rows})
    return {"n": len(rows)}


# -------------------------------------------------------- 8. snare layers

def exp_snare_layers():
    fs, n = 48000, 32768
    rows = []
    layer_sets = ["body+noise", "body+clap", "body+room", "noise+room",
                  "body+noise+clap"]
    for ls in layer_sets:
        for off_body in (0, 18, -31):
            for off_noise in (0, 44, -12):
                for rep in range(2):
                    cid = f"snr|{ls}|{off_body}|{off_noise}|{rep}"
                    rng = np.random.default_rng(C.case_seed(cid))
                    log = C.TransformLog()
                    body = C.g_snare_body(rng, n, fs)
                    noise = C.g_snare_noise(rng, n, fs)
                    clap = C.g_snare_body(rng, n, fs) * \
                        np.exp(-np.arange(n) / (0.03 * fs))
                    room = sps.sosfilt(sps.butter(2, 4000, btype="low",
                                                  fs=fs, output="sos"),
                                       C.g_snare_noise(rng, n, fs)) * 0.5
                    room *= np.exp(-np.arange(n) / (0.12 * fs))

                    def prep(sig, d):
                        s = C.apply_delay_exact(sig, d, fs, log)
                        return s / (np.max(np.abs(s)) + 1e-12)

                    body_d = prep(body, off_body)
                    parts = {"body": body_d}
                    b_parts = []
                    if "noise" in ls:
                        noise_d = prep(noise, off_noise)
                        parts["noise"] = noise_d
                        b_parts.append(0.7 * noise_d)
                    if "clap" in ls:
                        clap_d = prep(clap, off_noise // 2)
                        parts["clap"] = clap_d
                        b_parts.append(0.8 * clap_d)
                    if "room" in ls:
                        room_d = prep(room, -off_noise)
                        parts["room"] = room_d
                        b_parts.append(0.6 * room_d)
                    a = body_d
                    b = np.sum(b_parts, axis=0) if b_parts else body_d
                    b /= np.max(np.abs(b)) + 1e-12
                    feat = D.analyze_pair(a, b, fs, 128)
                    cls = D.classify(feat)
                    rec = D.recommend(feat, a, b, fs, cls, do_search=True,
                                      max_lag=96)
                    rows.append({
                        "case": cid, "layer_set": ls,
                        "off_body": off_body, "off_noise": off_noise,
                        "label": cls["label"], "confidence": cls["confidence"],
                        "action": rec["action"],
                        "reason": rec.get("reason"),
                        "coh": feat["coh_60_8k"],
                    })
    # false-recommendation rate when body is aligned and decorrelated
    # layers dominate the composite (should often be NO ACTION)
    healthy = [r for r in rows if r["off_body"] == 0]
    agg = {
        "healthy_no_action_rate": float(np.mean(
            [r["action"] == "NO_ACTION" for r in healthy])) if healthy else None,
        "label_counts": {l: sum(1 for r in rows if r["label"] == l)
                         for l in ("RELATED", "UNRELATED", "AMBIGUOUS")},
    }
    save("snare_layers", {"rows": rows, "aggregate": agg})
    return agg


# --------------------------------------------------------- 9. bass layers

def exp_bass_layers():
    fs, n = 48000, 32768
    rows = []
    combos = [("sub_mid", (0,)), ("clean_dist", (0,)),
              ("parallel_sat", (0,)), ("parcomp", (0,)),
              ("sub_mid", (24,)), ("clean_dist", (-17,))]
    for name, offs in combos:
        for off in offs:
            for rep in range(4):
                cid = f"bass|{name}|{off}|{rep}"
                rng = np.random.default_rng(C.case_seed(cid))
                log = C.TransformLog()
                sub = C.g_bass_sustained(rng, n, fs) if "sub" in name or True \
                    else None
                if name == "sub_mid":
                    mid = C.g_bass_transient(rng, n, fs)
                    a = sub / (np.max(np.abs(sub)) + 1e-12)
                    mid = C.apply_delay_exact(mid, off, fs, log)
                    mid += 0.3 * C.g_multisine(rng, n, fs)
                    b = mid / (np.max(np.abs(mid)) + 1e-12)
                    truth = float(off)
                elif name == "clean_dist":
                    a = C.g_bass_sustained(rng, n, fs)
                    dist = C.apply_distortion(a.copy(), 5.0, log)
                    dist = C.apply_delay_exact(dist, off, fs, log)
                    b = dist / (np.max(np.abs(dist)) + 1e-12)
                    truth = float(off)
                elif name == "parallel_sat":
                    a = C.g_bass_transient(rng, n, fs)
                    wet = C.apply_distortion(a, 8.0, log) * 0.5
                    b = (a * 0.6 + wet)
                    b = b / (np.max(np.abs(b)) + 1e-12)
                    truth = 0.0
                else:  # parcomp
                    a = C.g_bass_transient(rng, n, fs)
                    win = int(0.005 * fs)
                    env = np.sqrt(np.convolve(a ** 2, np.ones(win) / win,
                                              mode="same"))
                    g = np.where(env > 0.05, (0.05 / (env + 1e-9)) ** 0.75, 1)
                    comp = np.tanh(3 * a * g) * 1.8
                    b = (a + comp)
                    b = b / (np.max(np.abs(b)) + 1e-12)
                    truth = 0.0
                feat = D.analyze_pair(a, b, fs, 128)
                cls = D.classify(feat)
                rec = D.recommend(feat, a, b, fs, cls, do_search=True,
                                  max_lag=96)
                inter = I.band_interactions(a, b, fs)
                rows.append({
                    "case": cid, "combo": name, "truth_offset": truth,
                    "label": cls["label"], "action": rec["action"],
                    "conf": cls["confidence"],
                    "sub_interaction_db": inter["sub"],
                    "est_d": feat["estimates"]["gcc_soft"],
                    "err": feat["estimates"]["gcc_soft"] - truth,
                    "suggestion": rec["suggestions"][0] if rec["suggestions"]
                    else None,
                })
    agg = {}
    for name in ("sub_mid", "clean_dist", "parallel_sat", "parcomp"):
        sel = [r for r in rows if r["combo"] == name]
        errs = [abs(r["err"]) for r in sel if abs(r["truth_offset"]) > 0.5]
        agg[name] = {
            "mae_when_action_expected": float(np.mean(errs)) if errs else None,
            "no_action_rate": float(np.mean(
                [r["action"] == "NO_ACTION" for r in sel])),
            "mean_sub_interaction_db": float(np.mean(
                [r["sub_interaction_db"] for r in sel])),
        }
    save("bass_layers", {"rows": rows, "aggregate": agg})
    return agg


# -------------------------------------------------- 10. parallel processing

def exp_parallel():
    fs, n = 48000, 32768
    rows = []
    latencies = [0, 16, 32, 48, 64, 129]
    for mode in ("compressed", "saturated", "filtered", "multiband",
                 "oversampled"):
        for lat in latencies:
            for rep in range(3):
                cid = f"par|{mode}|{lat}|{rep}"
                case = S.parallel_processing_case(fs, n, cid, mode, float(lat))
                errs = est_errors(case.a, case.b, fs, float(lat))
                rows.append({"case": cid, "mode": mode, "latency": lat,
                             **{f"err_{k}": v for k, v in errs.items()}})
    agg = {}
    for mode in ("compressed", "saturated", "filtered", "multiband",
                 "oversampled"):
        sel = [r for r in rows if r["mode"] == mode]
        agg[mode] = {m: mae_stats([r[f"err_{m}"] for r in sel])
                     for m in ("xcorr_plain", "gcc_soft", "phase_slope")}
    save("parallel", {"rows": rows, "aggregate": agg})
    return agg


# ----------------------------------------------------- 11. sample-rate matrix

def exp_samplerate():
    n_dict = {44100: 30000, 48000: 32768, 88200: 60000, 96000: 65536}
    rows = []
    for fs in (44100, 48000, 88200, 96000):
        n = n_dict[fs]
        for ms in (0.0, 0.29, 1.0, 2.9):
            target_samples = ms * fs / 1000.0
            for rep in range(3):
                cid = f"sr|{fs}|{ms}|{rep}"
                case = S.simple_delay_case("kick", None, fs, n, cid,
                                           target_samples)
                errs_ms = {k: v / fs * 1000 for k, v in
                           est_errors(case.a, case.b, fs,
                                      target_samples).items()}
                rows.append({"case": cid, "fs": fs, "ms": ms,
                             "target_samples": target_samples,
                             **{f"ms_err_{k}": v for k, v in errs_ms.items()}})
    agg = {}
    for fs in (44100, 48000, 88200, 96000):
        sel = [r for r in rows if r["fs"] == fs]
        agg[str(fs)] = {m: mae_stats([r[f"ms_err_{m}"] for r in sel])
                        for m in ("xcorr_plain", "gcc_soft", "phase_slope")}
    save("samplerate", {"rows": rows, "aggregate": agg})
    return agg


# ------------------------------------------------------ 12. healthy controls

def exp_healthy():
    fs, n = 48000, 32768
    rows = []

    def record(cid, family, a, b, expect="NO_ACTION"):
        feat = D.analyze_pair(a, b, fs, 128)
        cls = D.classify(feat)
        rec = D.recommend(feat, a, b, fs, cls, do_search=True, max_lag=96)
        rows.append({"case": cid, "family": family, "expect": expect,
                     "label": cls["label"], "action": rec["action"],
                     "confidence": cls["confidence"],
                     "coh": feat["coh_60_8k"],
                     "prom": feat["prominence_soft"],
                     "recommended": rec["suggestions"][0] if
                     rec["suggestions"] else None})

    # 1 different instruments
    pairs = [("kick", "snare_body"), ("kick", "bass_sustained"),
             ("multisine", "noise"), ("synth_transient", "kick"),
             ("bandnoise", "bass_transient"), ("snare_noise", "sine")]
    for ka, kb in pairs:
        for rep in range(20):
            cid = f"h1|{ka}|{kb}|{rep}"
            rng = np.random.default_rng(C.case_seed(cid))
            a = C.SIGNAL_GENERATORS[ka](rng, n, fs)
            b = C.SIGNAL_GENERATORS[kb](rng, n, fs)
            a /= np.max(np.abs(a)); b /= np.max(np.abs(b))
            record(cid, "different_instruments", a, b)

    # 1b same instrument, level-mismatched and filtered (engineer already
    # aligned them by ear) — must remain NO ACTION
    for rep in range(16):
        cid = f"h1b|level|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        kind = str(rng.choice(["kick", "bass_transient", "synth_transient"]))
        a = C.SIGNAL_GENERATORS[kind](rng, n, fs)
        log2 = C.TransformLog()
        rng2 = np.random.default_rng(C.case_seed(cid + "|x"))
        b = a.copy()
        b = C.apply_gain(b / (np.max(np.abs(b)) + 1e-12),
                         float(rng.uniform(-8, 8)), log2)
        b = C.apply_minphase_eq(b, fs, rng2, log2)
        record(cid, "same_source_level_filtered", a, b)

    # 2 decorrelated stereo-like layers (same spectrum, independent noise)
    for rep in range(30):
        cid = f"h2|decorr|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        sos = sps_butter_band(fs)
        a = sps.sosfiltfilt(sos, rng.standard_normal(n))
        b = sps.sosfiltfilt(sos, rng.standard_normal(n))
        a /= np.max(np.abs(a)); b /= np.max(np.abs(b))
        record(cid, "decorrelated_same_spectrum", a, b)

    # 3 transient + sustain split of same source
    for rep in range(16):
        cid = f"h3|split|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        full = C.g_kick(rng, n, fs)
        t = np.arange(n) / fs
        attack = full * np.minimum(t / 0.004, 1.0) - \
            full * np.maximum((t - 0.06) / 0.01, 0).clip(0, 1)
        sustain = full - attack
        a = attack / (np.max(np.abs(attack)) + 1e-12)
        b = sustain / (np.max(np.abs(sustain)) + 1e-12)
        record(cid, "transient_plus_sustain", a, b)

    # 4 different-pitch layers
    for rep in range(16):
        cid = f"h4|pitch|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        f0 = rng.uniform(50, 70)
        t = np.arange(n) / fs
        a = np.sin(2 * np.pi * f0 * t) * np.exp(-t / .1)
        b = np.sin(2 * np.pi * f0 * rng.uniform(1.4, 2.1) * t) * \
            np.exp(-t / .1)
        a /= np.max(np.abs(a)); b /= np.max(np.abs(b))
        record(cid, "different_pitch", a, b)

    # 5 wide texture + mono core
    for rep in range(16):
        cid = f"h5|wide|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        core = C.g_kick(rng, n, fs)
        wide = C.g_bandnoise(rng, n, fs)
        a = core
        b = 0.5 * wide / (np.max(np.abs(wide)) + 1e-12) + \
            0.35 * core / (np.max(np.abs(core)) + 1e-12)
        b /= np.max(np.abs(b)) + 1e-12
        record(cid, "wide_texture_mono_core", a, b)

    # 6 deliberately offset percussion that still grooves (musical offset)
    for rep in range(16):
        cid = f"h6|groove|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        case = S.kick_layer_stack(fs, n, cid,
                                  offsets=(0, 90, 45),
                                  polarities=(1, 1, 1),
                                  overlap=False)
        record(cid, "deliberately_offset_percussion", case.a, case.b)

    total = len(rows)
    fp = [r for r in rows if r["expect"] == "NO_ACTION" and
          r["action"] not in ("NO_ACTION",)]
    agg = {
        "n_cases": total,
        "no_action_accuracy": float(np.mean(
            [r["action"] == "NO_ACTION" for r in rows])),
        "false_recommendation_rate": float(len(fp) / total),
        "by_family": {},
        "false_cases": [{"case": r["case"], "family": r["family"],
                         "action": r["action"],
                         "suggestion": r["recommended"]} for r in fp],
    }
    fams = sorted({r["family"] for r in rows})
    for fam in fams:
        sel = [r for r in rows if r["family"] == fam]
        agg["by_family"][fam] = {
            "n": len(sel),
            "no_action_rate": float(np.mean(
                [r["action"] == "NO_ACTION" for r in sel])),
        }
    save("healthy_controls", {"rows": rows, "aggregate": agg})
    return agg


def sps_butter_band(fs, lo=100, hi=8000):
    from scipy import signal as sps
    return sps.butter(4, [lo, hi], btype="band", fs=fs, output="sos")


# ------------------------------------------------------------ 13. adversarial

def exp_adversarial():
    fs, n = 48000, 32768
    rows = []
    t = np.arange(n) / fs

    def analyze_case(cid, family, a, b, truth=None, expect_action=None):
        feat = D.analyze_pair(a, b, fs, 256)
        cls = D.classify(feat)
        est = feat["estimates"]
        row = {"case": cid, "family": family, "label": cls["label"],
               "conf": cls["confidence"],
               "est_xcorr": est["xcorr_plain"],
               "est_gcc": est["gcc_soft"],
               "est_pslope": est["phase_slope"],
               "prom": feat["prominence_soft"], "coh": feat["coh_60_8k"]}
        if truth is not None:
            row["truth"] = truth
            row["err_gcc"] = est["gcc_soft"] - truth
        if expect_action is not None:
            rec = D.recommend(feat, a, b, fs, cls)
            row["expected"] = expect_action
            row["action"] = rec["action"]
        rows.append(row)

    # periodic sine ambiguity: delay = half period looks like many options
    for f0 in (110.0, 220.0):
        period = fs / f0
        for rep in range(4):
            cid = f"adv|sine_amb|{f0}|{rep}"
            rng = np.random.default_rng(C.case_seed(cid))
            x = np.sin(2 * np.pi * f0 * t + rng.uniform(0, 6.28))
            d_true = period * (0.13 + 0.05 * rep)
            y = C.apply_delay_exact(x, d_true, fs, C.TransformLog())
            analyze_case(cid, f"sine_ambiguity_{f0}Hz", x, y, truth=d_true)

    # octave-related tones
    for rep in range(4):
        cid = f"adv|octave|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        x = np.sin(2 * np.pi * 55 * t)
        y = np.sin(2 * np.pi * 110 * t + rng.uniform(0, 6.28))
        analyze_case(cid, "octave_tones", x, y, expect_action="NO_ACTION")

    # comb-filtered copy
    for d_comb in (31, 77):
        for rep in range(3):
            cid = f"adv|comb|{d_comb}|{rep}"
            rng = np.random.default_rng(C.case_seed(cid))
            x = C.g_kick(rng, n, fs)
            y = x + 0.9 * C.apply_delay_exact(x, float(d_comb), fs,
                                              C.TransformLog())
            y /= np.max(np.abs(y)) + 1e-12
            analyze_case(cid, f"comb_filtered_{d_comb}", x, y, truth=0.0)

    # multiple transient peaks
    for gap in (2400, 7200):
        for rep in range(3):
            cid = f"adv|multi|{gap}|{rep}"
            rng = np.random.default_rng(C.case_seed(cid))
            k1 = C.g_kick(rng, n, fs)
            k2 = C.g_kick(rng, n, fs)
            a = k1 + 0.8 * np.roll(k2, gap)
            b = C.apply_delay_exact(k1, 33.0, fs, C.TransformLog()) + \
                0.8 * np.roll(k2, gap)
            analyze_case(cid, f"two_kicks_gap{gap}", a, b, truth=33.0)

    # reversed envelope (same spectrum-ish, wrong transient direction)
    for rep in range(3):
        cid = f"adv|rev|{rep}"
        rng = np.random.default_rng(C.case_seed(cid))
        x = C.g_snare_noise(rng, n, fs)
        y = x[::-1].copy()
        analyze_case(cid, "reversed_envelope", x, y)

    # heavy clipping on B
    for drive in (10.0, 40.0):
        for rep in range(3):
            cid = f"adv|clip|{drive}|{rep}"
            rng = np.random.default_rng(C.case_seed(cid))
            x = C.g_kick(rng, n, fs)
            d = 21.0 + rep
            y = np.tanh(drive * C.apply_delay_exact(
                x, d, fs, C.TransformLog())) / np.tanh(drive)
            analyze_case(cid, f"clipped_drive{int(drive)}", x, y, truth=d)

    agg = {}
    for fam in sorted({r["family"] for r in rows}):
        sel = [r for r in rows if r["family"] == fam]
        entry = {"n": len(sel)}
        if "err_gcc" in sel[0]:
            errs = [abs(r["err_gcc"]) for r in sel if "err_gcc" in r]
            entry["gcc_mae"] = float(np.mean(errs))
        if sel[0].get("expected") == "NO_ACTION":
            entry["abstain_rate"] = float(np.mean(
                [r["action"] == "NO_ACTION" for r in sel]))
        agg[fam] = entry
    save("adversarial", {"rows": rows, "aggregate": agg})
    return agg


# ---------------------------------------------------------------- 14. bakeoff

def exp_bakeoff():
    """Aggregate across saved result files."""
    def load(name):
        p = RESULTS / f"{name}.json"
        return json.loads(p.read_text()) if p.exists() else None

    summary = {}
    os_ = load("offset_sweep")
    if os_:
        summary["offset_sweep_overall_mae"] = {
            k: v["overall"]["mae"] for k, v in os_["aggregate"].items()}
    ss = load("subsample")
    if ss:
        summary["subsample_mae"] = ss["aggregate"]
    pl = load("polarity")
    if pl:
        summary["polarity_accuracy"] = pl["accuracy_overall"]
    pf = load("phase_filters")
    if pf:
        summary["phase_filter_recovery"] = {
            k: v["mean_delay_only_recovery_pct"] for k, v in pf["aggregate"].items()}
    hc = load("healthy_controls")
    if hc:
        summary["healthy_false_rec_rate"] = hc["aggregate"]["false_recommendation_rate"]
        summary["healthy_no_action_acc"] = hc["aggregate"]["no_action_accuracy"]
    sr = load("samplerate")
    if sr:
        summary["samplerate_ms_mae_gccsoft"] = {
            k: v["gcc_soft"]["mae"] for k, v in sr["aggregate"].items()}
    pa = load("parallel")
    if pa:
        summary["parallel_latency_mae_gccsoft"] = {
            k: v["gcc_soft"]["mae"] for k, v in pa["aggregate"].items()}
    tr = load("transient")
    if tr:
        summary["transient_align_mae"] = tr["aggregate"]
    ad = load("adversarial")
    if ad:
        summary["adversarial"] = ad["aggregate"]
    save("bakeoff_summary", summary)
    return summary


# -------------------------------------------------------------- 15. perf

def exp_performance():
    fs = 48000
    rng = np.random.default_rng(99)
    out = {}
    for n in (4096, 16384, 65536):
        a = C.g_kick(rng, n, fs)
        b = C.apply_delay_exact(a, 14.0, fs, C.TransformLog())
        timings = {}
        reps = 20 if n <= 16384 else 8
        for nm, fn in (
            ("xcorr_plain", lambda: M.xcorr_plain(a, b, 256)),
            ("gcc_phat", lambda: M.gcc_phat(a, b, 256)),
            ("gcc_soft", lambda: M.gcc_soft(a, b, 256)),
            ("phase_slope", lambda: M.phase_slope_offset(a, b, fs)),
            ("bandwise", lambda: M.bandwise_analysis(a, b, fs, 128)),
            ("analyze_pair", lambda: D.analyze_pair(a, b, fs, 128)),
        ):
            fn()  # warmup
            t0 = time.perf_counter()
            for _ in range(reps):
                fn()
            timings[nm] = (time.perf_counter() - t0) / reps * 1000.0
        out[str(n)] = {"ms_per_call": {k: round(v, 3) for k, v in
                                       timings.items()}}
    # fast_search cost
    a = C.g_kick(rng, 32768, fs)
    b = C.apply_delay_exact(a, 14.0, fs, C.TransformLog())
    t0 = time.perf_counter()
    I.fast_search(a, b, fs, 96)
    out["fast_search_n32768_maxlag96_ms"] = round(
        (time.perf_counter() - t0) * 1000.0, 1)
    save("performance", out)
    return out


FAMILIES = {
    "offset_sweep": exp_offset_sweep,
    "subsample": exp_subsample,
    "polarity": exp_polarity,
    "phase_filters": exp_phase_filters,
    "band_dispersion": exp_band_dispersion,
    "transient": exp_transient,
    "kick": exp_kick_layers,
    "snare": exp_snare_layers,
    "bass": exp_bass_layers,
    "parallel": exp_parallel,
    "samplerate": exp_samplerate,
    "healthy": exp_healthy,
    "adversarial": exp_adversarial,
    "bakeoff": exp_bakeoff,
    "performance": exp_performance,
}


def main(argv):
    fams = argv[1:] or list(FAMILIES)
    for f in fams:
        print(f"=== {f} ===", flush=True)
        t0 = time.perf_counter()
        FAMILIES[f]()
        print(f"    done in {time.perf_counter()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv)
