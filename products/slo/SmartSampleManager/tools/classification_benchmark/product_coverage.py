#!/usr/bin/env python3
"""
The number that actually decides whether SLO ships.

Every accuracy figure in this programme has been AUDIO-ONLY. Production does not
work that way: it fuses evidence, trusting the filename where the filename is
trustworthy and consulting audio only where it is not. Reporting audio-only
coverage as if it were the product understates the product -- and hides whether
the fusion loses precision at the seams.

This measures the end-to-end renamer: given a file, does SLO rename it, and is
that rename correct?

  coverage  = fraction of files the renamer ACTS on
  precision = fraction of those actions that are CORRECT

Both gates are fitted on TRAINING COLLECTIONS ONLY and applied unchanged to
held-out ones -- per-class filename precision and the audio confidence threshold
alike. Fitting either on the evaluation data would manufacture the result.

Arms:
  filename-only   act when the filename detector fires on a class whose
                  training-fold precision clears the target
  audio-only      act when centroid confidence clears the calibrated threshold
  fusion          filename where trusted, audio elsewhere (production's shape)
  fusion+agree    act only when both agree, or one is trusted and the other silent
"""
import os, csv, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import incumbent_receipt as ir, eval_corpus_v2 as ec, per_class_gating as pg
import name_detect as nd
from sklearn.model_selection import StratifiedGroupKFold

OUT = os.path.join(SD, "results_product_coverage.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--target", type=float, default=0.95)
    ap.add_argument("--calib-margin", type=float, default=0.03,
                    help="calibrate this far above target to absorb the "
                         "measured domain-shift shortfall")
    a = ap.parse_args()

    d = ec.load()
    keep = np.isin(d["y"], ec.DRUM10)
    X, y, g = d["X"][keep], d["y"][keep], d["vendor"][keep]
    paths = [p for p, k in zip(d["paths"], keep) if k]
    classes = ec.DRUM10
    fn = np.array([nd.detect(os.path.basename(p))[0] for p in paths], dtype=object)
    fn = np.array([c if c in classes else None for c in fn], dtype=object)
    print(f"{len(y)} files, {len(set(g))} collections")
    print(f"filename fires on {int(sum(c is not None for c in fn))} "
          f"({100*np.mean([c is not None for c in fn]):.1f}%)\n")

        # The detector's failures are mostly GRANULARITY, not error: it says
    # "Percussion" when the ear says "Percussion Loop" (family right, form
    # wrong), or generic "Loop" when the ear names the loop's family. Audio gets
    # temporal form right 88.8% of the time. So combine each source where it is
    # strong: filename for FAMILY, audio for FORM.
    from factorised_taxonomy import FAMILY, FORM
    fam_of = {c: FAMILY[c] for c in classes}
    form_of = {c: FORM[c] for c in classes}

    # multi-window DSP appended to the encoder embedding. Judged under the SAME
    # calibrated protocol as every other arm -- a threshold fitted on training
    # collections and applied unchanged to held-out ones -- because the in-sample
    # "best achievable coverage" number is optimistic and not what ships.
    import mw_features as mwf
    from sklearn.preprocessing import StandardScaler as _SS
    M, mmask = mwf.load_aligned(paths)
    have_mw = M is not None
    if have_mw and not mmask.all():
        # A handful of files fail DSP extraction. Drop them from EVERY arm so
        # all arms are compared on identical rows -- disabling the multi-window
        # comparison over one missing file would be worse, and keeping different
        # row sets per arm would make the comparison meaningless.
        n = int((~mmask).sum())
        print(f"dropping {n} file(s) with no multi-window features "
              f"(applied to all arms)")
        X, y, g = X[mmask], y[mmask], g[mmask]
        paths = [q for q, k in zip(paths, mmask) if k]
        fn = fn[mmask]
    if have_mw:
        Mz = _SS().fit_transform(M)
        Mz = Mz / (np.linalg.norm(Mz, axis=1, keepdims=True) + 1e-9)
        XM = np.hstack([X, Mz])
        print("multi-window DSP features loaded")
    else:
        XM = None
        print("multi-window DSP unavailable -- those arms skipped")

    arms = ["filename-only", "audio-only", "fusion", "fusion+agree",
            "family+form"] + (["mw-audio", "mw-fusion"] if have_mw else [])
    acc = {k: {"cov": [], "prec": []} for k in arms}
    cal_t = a.target + a.calib_margin

    for s in range(a.seeds):
        cv = StratifiedGroupKFold(a.splits, shuffle=True, random_state=s)
        for tr, te in cv.split(X, y, groups=g):
            assert not (set(g[tr]) & set(g[te])), "collection leak"
            # --- fit filename trust on TRAINING collections only ---------
            trust = {}
            for c in classes:
                m = np.array([fn[i] == c for i in tr])
                if m.sum() < 5:
                    trust[c] = False
                    continue
                prec = float((y[tr][m] == c).mean())
                trust[c] = prec >= cal_t
            # family-level filename trust, fitted on TRAINING collections only
            fam_trust = {}
            for fam in set(fam_of.values()):
                m = np.array([fn[i] is not None and fam_of[fn[i]] == fam
                              for i in tr])
                if m.sum() < 5:
                    fam_trust[fam] = False
                    continue
                truth_fam = np.array([fam_of[c] for c in y[tr][m]])
                fam_trust[fam] = float((truth_fam == fam).mean()) >= cal_t

            # --- fit the audio threshold on an inner grouped split -------
            inner = StratifiedGroupKFold(3, shuffle=True, random_state=s)
            itr, ical = next(inner.split(X[tr], y[tr], groups=g[tr]))
            p_cal, c_cal = ir.centroid_fit_predict(X[tr][itr], y[tr][itr],
                                                   X[tr][ical], classes)
            thr = pg.global_threshold(c_cal, (p_cal == y[tr][ical]).astype(float),
                                      cal_t)
            p_te, c_te = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
            if XM is not None:
                pm_cal, cm_cal = ir.centroid_fit_predict(
                    XM[tr][itr], y[tr][itr], XM[tr][ical], classes)
                mw_thr = pg.global_threshold(
                    cm_cal, (pm_cal == y[tr][ical]).astype(float), cal_t)
                pm_te, cm_te = ir.centroid_fit_predict(XM[tr], y[tr], XM[te], classes)
            ym_cal = np.array([form_of[c] for c in y[tr][itr]])
            pf_cal, cf_cal = ir.centroid_fit_predict(
                X[tr][itr], ym_cal, X[tr][ical], sorted(set(form_of.values())))
            form_thr = pg.global_threshold(
                cf_cal, (pf_cal == np.array([form_of[c] for c in y[tr][ical]])
                         ).astype(float), cal_t)

            # audio prototypes for the FORM axis, fitted on the training fold
            ym_tr = np.array([form_of[c] for c in y[tr]])
            forms = sorted(set(form_of.values()))
            p_form, c_form = ir.centroid_fit_predict(X[tr], ym_tr, X[te], forms)

            fn_te = fn[te]; y_te = y[te]
            fn_ok = np.array([c is not None and trust.get(c, False) for c in fn_te])
            au_ok = c_te >= thr

            def score(act, pred):
                if act.sum() == 0:
                    return 0.0, 1.0
                return float(act.mean()), float((pred[act] == y_te[act]).mean())

            # filename-only
            cov, prec = score(fn_ok, np.array([c if c else "" for c in fn_te]))
            acc["filename-only"]["cov"].append(100 * cov)
            acc["filename-only"]["prec"].append(100 * prec)
            # audio-only
            cov, prec = score(au_ok, p_te)
            acc["audio-only"]["cov"].append(100 * cov)
            acc["audio-only"]["prec"].append(100 * prec)
            # fusion: filename where trusted, else audio
            fused = np.where(fn_ok, np.array([c if c else "" for c in fn_te]), p_te)
            act = fn_ok | au_ok
            cov, prec = score(act, fused)
            acc["fusion"]["cov"].append(100 * cov)
            acc["fusion"]["prec"].append(100 * prec)
            # fusion+agree: require agreement when both speak
            both = fn_ok & au_ok
            disagree = both & (np.array([c if c else "" for c in fn_te]) != p_te)
            act2 = act & ~disagree
            cov, prec = score(act2, fused)
            acc["fusion+agree"]["cov"].append(100 * cov)
            acc["fusion+agree"]["prec"].append(100 * prec)

            # family (filename) x form (audio) -> exact label
            fn_fam = np.array([fam_of.get(c) if c else None for c in fn_te],
                              dtype=object)
            ff_pred, ff_ok = [], []
            for i in range(len(te)):
                fam, frm = fn_fam[i], p_form[i]
                cand = [c for c in classes
                        if fam is not None and fam_of[c] == fam and form_of[c] == frm]
                if len(cand) == 1 and fn_ok[i] is not None:
                    ff_pred.append(cand[0])
                    # act when the filename family is trusted AND the form
                    # prototype is confident
                    ff_ok.append(bool(fam_trust.get(fam, False))
                                 and c_form[i] >= form_thr)
                else:
                    ff_pred.append(p_te[i]); ff_ok.append(bool(au_ok[i]))
            cov, prec = score(np.array(ff_ok), np.array(ff_pred, dtype=object))
            acc["family+form"]["cov"].append(100 * cov)
            acc["family+form"]["prec"].append(100 * prec)

            if XM is not None:
                mw_ok = cm_te >= mw_thr
                cov, prec = score(mw_ok, pm_te)
                acc["mw-audio"]["cov"].append(100 * cov)
                acc["mw-audio"]["prec"].append(100 * prec)
                fused_mw = np.where(fn_ok,
                                    np.array([c if c else "" for c in fn_te]), pm_te)
                act_mw = fn_ok | mw_ok
                cov, prec = score(act_mw, fused_mw)
                acc["mw-fusion"]["cov"].append(100 * cov)
                acc["mw-fusion"]["prec"].append(100 * prec)

    print(f"target precision {a.target:.0%}, calibrated at {cal_t:.0%} "
          f"(+{a.calib_margin:.0%} for domain shift)\n")
    print(f"  {'arm':16} {'coverage':>11} {'precision':>12} {'meets target':>14}")
    res = {}
    for k in arms:
        cov = float(np.mean(acc[k]["cov"])); prec = float(np.mean(acc[k]["prec"]))
        meets = "YES" if prec >= 100 * a.target else f"no ({prec-100*a.target:+.1f}pp)"
        print(f"  {k:16} {cov:10.1f}% {prec:11.1f}% {meets:>14}")
        res[k] = {"coverage": round(cov, 2), "precision": round(prec, 2),
                  "meets_target": prec >= 100 * a.target}
    best = max((k for k in arms if res[k]["meets_target"]),
               key=lambda k: res[k]["coverage"], default=None)
    print(f"\n  best arm that MEETS the precision target: "
          f"{best or 'NONE'}"
          + (f"  ({res[best]['coverage']:.1f}% coverage)" if best else ""))
    json.dump({"target": a.target, "calibrated_at": cal_t, "seeds": a.seeds,
               "results": res, "best_meeting_target": best},
              open(OUT, "w"), indent=2)
    print(f"wrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
