"""Build the Real-Audio Validation V1 corpus from owner-authorised sources.

Stages (CLI arg): survey | build | run | pack | metrics | parity | bench
Run 'all' to execute everything in order with incremental JSON output.

Sources are opened READ-ONLY. Derived fixtures live only under
results/real_v1/derived/. The frozen engine is imported untouched.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import signal as sps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval import source_survey as S                          # noqa: E402
from eval.auth_receipts import write_receipts                # noqa: E402
from eval.audio_io import AudioLoadError, load_wav           # noqa: E402
from eval.audio_io import resample_linear                    # noqa: E402


def pair_rates(xa, xb):
    """If sample rates differ, resample B to A's rate (linear; derived
    preview-quality fixture documented in processing meta). Returns
    (xa.samples, xb', fs, resampled_flag)."""
    if xa.sample_rate == xb.sample_rate:
        return xa.samples, xb.samples, xa.sample_rate, False
    yb = resample_linear(xb.samples, xb.sample_rate, xa.sample_rate)
    return xa.samples, yb, xa.sample_rate, True
from eval.blind_pack import build_pack                       # noqa: E402
from eval.cases import CONTROL_GRID, PairCase, case_seed, \
    make_controlled                                          # noqa: E402
from eval.pipeline import analyse_case, records_to_json      # noqa: E402
from eval.score import score                                 # noqa: E402

OUT = ROOT / "results" / "real_v1"
DERIVED = OUT / "derived"
BLIND = OUT / "blind_pack_real"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------- survey

def stage_survey():
    write_receipts(ROOT / "real_audio_import")
    pack_files = S.list_wavs(S.PACK_ROOT)
    stem_files = S.list_wavs(S.STEM_ROOT)
    inv = {
        "pack_wav_files": len(pack_files),
        "stem_wav_files": len(stem_files),
        "pack_groups": len({p.relative_to(S.PACK_ROOT).parts[0]
                            for p in pack_files}),
        "stem_sessions": sorted({p.relative_to(S.STEM_ROOT).parts[0]
                                 for p in stem_files
                                 if not p.relative_to(
                                     S.STEM_ROOT).parts[0].startswith("_")}),
        "note": "_automix_out excluded (another sprint's derived outputs)",
    }
    (OUT / "source_inventory.json").write_text(json.dumps(inv, indent=1))
    log(f"survey: {inv['pack_wav_files']} pack wavs / "
        f"{inv['stem_wav_files']} stem wavs")


# ---------------------------------------------------------------- build

def _evidence_or_none(p: Path):
    ev = S.audio_evidence(p)
    return None if ev is None or "load_error" in ev else ev


def _domain_pool(files, domain, n, per_pack=3, exclude_loops=True,
                 oversample=8):
    cand = S.shortlist_domain(files, domain, exclude_loops)
    pool = []
    for f in cand:
        if len(pool) >= n * oversample:   # verify up to 6x oversample
            break
        ev = _evidence_or_none(f)
        if not ev:
            continue
        refined = S.refine_domain(ev, domain)
        if refined:
            ev["verified_domain"] = refined
            pool.append((f, ev))
        if len(pool) >= n:
            break
    return S.pick_diverse([p for p, _ in pool], n, per_pack)


def stage_build():
    DERIVED.mkdir(parents=True, exist_ok=True)
    pack_files = S.list_wavs(S.PACK_ROOT)
    stem_files = [p for p in S.list_wavs(S.STEM_ROOT)
                  if p.relative_to(S.STEM_ROOT).parts[0] != "_automix_out"]

    used_manifest = []
    cases: list[PairCase] = []

    def register_source(p: Path, group: str, role: str):
        la = load_wav(p)
        try:
            rel = str(p.relative_to(S.PACK_ROOT))
            src_group = "pack/" + group
        except ValueError:
            rel = str(p.relative_to(S.STEM_ROOT))
            src_group = "stems/" + group
        used_manifest.append({
            "path": rel, "sha256": la.sha256,
            "sample_rate": la.sample_rate, "channels": la.channels,
            "duration_s": round(la.duration_s, 3), "role": role})
        return la

    rng = np.random.default_rng(2026)

    # ---------------- CONTROLLED from verified pack one-shots ----------
    plan = [("kick", 16), ("snare", 12), ("clap", 8), ("bass", 16),
            ("perc", 10), ("synth", 12), ("vocal", 6)]
    variants = [g[0] for g in CONTROL_GRID]
    vidx = 0
    n_ctl = 0
    for domain, count in plan:
        picks = _domain_pool(pack_files, domain, count, per_pack=5)
        for i, p in enumerate(picks):
            la = load_wav(p)
            label = variants[vidx % len(variants)]
            vidx += 1
            grid = [g for g in CONTROL_GRID if g[0] == label]
            v2 = [variants[vidx % len(variants)],
                  variants[(vidx + 3) % len(variants)]]
            vidx += 1
            grid = [g for g in CONTROL_GRID if g[0] in v2]
            sub = make_controlled(la, p.relative_to(S.PACK_ROOT).parts[0],
                                  "owner_authorised", domain,
                                  f"ctl|{domain}|{i}|{p.stem[:24]}",
                                  grid=grid, max_pairs_per_source=2)
            for c in sub:
                c.provenance_category = "owner_authorised"
            cases += sub
            n_ctl += len(sub)
            used_manifest.append({
                "path": str(p.relative_to(S.PACK_ROOT)),
                "sha256": la.sha256, "sample_rate": la.sample_rate,
                "channels": la.channels,
                "duration_s": round(la.duration_s, 3),
                "role": f"controlled_source/{domain}"})
    log(f"controlled cases: {n_ctl}")

    # ---------------- HEALTHY ------------------------------------------
    def add(cid, klass, cat, rel, x, y, fs, expected="NO_ACTION",
            prov="owner_authorised", ga="", gb="", truth=None, pol=1,
            processing=None):
        n = min(len(x), len(y))
        lim = min(n, 10 * fs)
        cases.append(PairCase(
            case_id=cid, klass=klass, category=cat, relationship=rel,
            fs=fs, a=x[:lim], b=y[:lim], source_group_a=ga,
            source_group_b=gb, provenance_category=prov,
            truth_offset_samples=truth, truth_polarity=pol,
            expected_action=expected, processing=processing or {}))

    # H1 identity self-pairs from stems
    h1_sessions = ["al_james", "angeloboltini_fragments", "stranger",
                   "reggueton_pop", "dream_of_you", "ae_mere_humsafar"]
    for ses in h1_sessions:
        fs_list = [p for p in stem_files
                   if p.relative_to(S.STEM_ROOT).parts[0] == ses]
        if not fs_list:
            continue
        p = fs_list[int(case_seed(ses)) % len(fs_list)]
        la = load_wav(p)
        add(f"hlt|identity|{ses}", "HEALTHY", "self", "identity_copy",
            la.samples, la.samples.copy(), la.sample_rate)

    # H2 cross-pack same-domain decorrelated pairs
    for domain, npair in (("kick", 20), ("hat", 14), ("snare", 8),
                          ("clap", 6), ("perc", 14)):
        picks = _domain_pool(pack_files, domain, npair * 2 + 2,
                             per_pack=2)
        loads = [(p, load_wav(p)) for p in picks]
        made = 0
        for i in range(len(loads)):
            if made >= npair:
                break
            for j in range(i + 1, len(loads)):
                if made >= npair:
                    break
                pa_, xa_ = loads[i]
                pb_, xb_ = loads[j]
                ya, yb, frs, rsflag = pair_rates(xa_, xb_)
                add(f"hlt|xpack|{domain}|{i}_{j}", "HEALTHY", domain,
                    f"cross_pack_{domain}", ya, yb, frs,
                    processing={"resampled_b": rsflag})
                made += 1

    # H3 frequency-dependent (LR4 crossover recombine of same source)
    xover_sources = _domain_pool(pack_files, "bass", 10, per_pack=2) + \
        _domain_pool(pack_files, "kick", 10, per_pack=2)
    from src.nla import corpus as C
    for i, p in enumerate(xover_sources):
        la = load_wav(p)
        log_ent = C.TransformLog()
        y = C.lr4_crossover_recombine(la.samples[: 4 * la.sample_rate],
                                      la.sample_rate,
                                      float(rng.uniform(120, 900)), log_ent)
        add(f"hlt|lr4|{i}", "HEALTHY", "dispersive",
            "crossover_recombine", la.samples[: len(y)], y,
            la.sample_rate, processing={"lr4_hz":
                                        log_ent.entries[0]["fc_hz"]})

    # H4 different-envelope same source
    env_sources = _domain_pool(pack_files, "synth", 10, per_pack=2) + \
        _domain_pool(pack_files, "bass", 10, per_pack=2)
    for i, p in enumerate(env_sources):
        la = load_wav(p)
        seg = la.samples[: 4 * la.sample_rate].copy()
        t = np.arange(len(seg)) / la.sample_rate
        env = np.exp(-t / 0.35) + 0.35 * np.exp(-t / 0.04)
        b = seg * env / (np.max(np.abs(env)) + 1e-9)
        add(f"hlt|env|{i}", "HEALTHY", "envelope_variation",
            "different_envelope", seg, b, la.sample_rate)

    # H5 tonal loop ambiguity pairs
    loops = [p for p in pack_files
             if re.search(r"loop|pad|texture|atmos", p.name, re.I)]
    lpicks = S.pick_diverse(loops, 14, per_pack=2)
    for i in range(len(lpicks)):
        for j in range(i + 1, len(lpicks)):
            xa, xb = load_wav(lpicks[i]), load_wav(lpicks[j])
            ya, yb, frs, rsflag = pair_rates(xa, xb)
            add(f"hlt|tonal|{i}_{j}", "HEALTHY", "tonal",
                "tonal_ambiguity", ya, yb, frs,
                processing={"resampled_b": rsflag})

    # H7 unrelated complementary cross-domain
    kicks = _domain_pool(pack_files, "kick", 14, per_pack=2)
    hats = _domain_pool(pack_files, "hat", 14, per_pack=2)
    for i in range(min(len(kicks), len(hats))):
        xa, xb = load_wav(kicks[i]), load_wav(hats[i])
        ya, yb, frs, rsflag = pair_rates(xa, xb)
        add(f"hlt|compl|{i}", "HEALTHY", "cross_domain",
            "unrelated_complementary", ya, yb, frs,
            processing={"resampled_b": rsflag})

    n_healthy = sum(1 for c in cases if c.klass == "HEALTHY")
    log(f"healthy cases: {n_healthy}")

    # ---------------- NATURAL from stems --------------------------------
    NATURAL_PAIRS = {
        "atlantisbound_itwasmyfaultforwaiting":
            [("01_Kick.wav", "02_KickSub.wav", "kick+sub"),
             ("03_SnareUp.wav", "04_SnareDown.wav", "snare_top_bottom"),
             ("01_Kick.wav", "08_Overheads.wav", "kick+oh"),
             ("02_KickSub.wav", "08_Overheads.wav", "sub+oh"),
             ("06_Tom1.wav", "07_Tom2.wav", "tom_tom"),
             ("01_Kick.wav", "05_HiHat.wav", "kick_hat")],
        "angeloboltini_fragments":
            [("01_Kick.wav", "08_Drumkit1_Kick.wav", "layered_kicks"),
             ("02_Snare1.wav", "05_Clap.wav", "snare_clap"),
             ("02_Snare1.wav", "03_Snare2.wav", "snare_layers"),
             ("06_HiHat1.wav", "07_HiHat2.wav", "hat_layers"),
             ("01_Kick.wav", "05_Clap.wav", "kick_clap")],
        "al_james":
            [("01_Kick.wav", "06_Claps.wav", "kick_claps"),
             ("02_Snare1.wav", "03_Snare2.wav", "snare_layers"),
             ("02_Snare1.wav", "06_Claps.wav", "snare_claps"),
             ("07_HiHat1.wav", "08_HiHat2.wav", "hat_layers"),
             ("01_Kick.wav", "12_Tom1.wav", "kick_tom")],
        "amyhelmandthehandsomestrangers_rescueme":
            [("Drums-Kick in-M82.wav", "Drums-Kick Out-Cu29.wav",
              "kick_in_out"),
             ("Drums-Snare Bottom-M81.wav", "Drums-Snare Top-M80.wav",
              "snare_top_bottom"),
             ("Drums-Kick in-M82.wav", "Drums-Overhead-ELA M260.wav",
              "kick_oh"),
             ("Drums-Hat-ELA M260.wav", "Drums-Ride-ELA M260.wav",
              "hat_ride"),
             ("Bass-DI.wav", "Chamber-Ar70.wav", "bass_room")],
        "stranger":
            [("_ KICK.wav", "_ BASS.wav", "kick_bass"),
             ("_ KICK.wav", "_ DRUMS.wav", "kick_drumbus"),
             ("_ DRUMS.wav", "_ PERC.wav", "drums_perc"),
             ("_ BASS.wav", "_ BRASS.wav", "bass_brass"),
             ("_ INTRO_MELODY.wav", "_ NOISE.wav", "melody_noise")],
        "reggueton_pop":
            [("_ BASS.wav", "_ DRUMS.wav", "bass_drumbus"),
             ("_ CLAP.wav", "_ DRUMS.wav", "clap_drumbus"),
             ("_ ARP.wav", "_ GATED_PAD.wav", "arp_pad"),
             ("_ BASS.wav", "_ ARP.wav", "bass_arp")],
        "dream_of_you":
            [("_ BASS.wav", "_ CLAP.wav", "bass_clap"),
             ("_ ARPEGGIO.wav", "_ BLEEPS.wav", "arp_bleeps"),
             ("_ HATS.wav", "_ HATS-1.wav", "hat_layers"),
             ("_ BASS.wav", "_ GUITAR_01.wav", "bass_guitar")],
        "ae_mere_humsafar":
            [("01_Kick.wav", "08_Bass.wav", "kick_bass"),
             ("02_Clap.wav", "03_Snare.wav", "clap_snare"),
             ("01_Kick.wav", "02_Clap.wav", "kick_clap"),
             ("04_HiHat.wav", "05_Shaker.wav", "hat_shaker")],
    }

    # systematic intra-session fallback pairs (rhythm-section roles by name)
    ROLE_RX = {"kick": r"kick|bd\b", "snare": r"snare", "clap": r"clap",
               "hat": r"hat|ride|cym", "bass": r"bass|808",
               "drumbus": r"^_?(drums?)\.", "perc": r"perc|shaker|tam"}
    def role_of(name):
        base = Path(name).stem.lower()
        for role, rx in ROLE_RX.items():
            if re.search(rx, base):
                return role
        return None
    session_roles = {}
    for p in stem_files:
        ses = p.relative_to(S.STEM_ROOT).parts[0]
        r = role_of(p.name)
        if r:
            session_roles.setdefault(ses, {}).setdefault(r, []).append(p)
    FALLBACK_COMBOS = [("kick", "bass"), ("kick", "snare"),
                       ("kick", "clap"), ("snare", "clap"),
                       ("snare", "hat"), ("kick", "drumbus"),
                       ("bass", "drumbus"), ("clap", "hat"),
                       ("kick", "perc"), ("bass", "hat"),
                       ("snare", "perc"), ("kick", "hat"),
                       ("bass", "snare"), ("perc", "hat"),
                       ("tom", "kick"), ("bass", "clap"),
                       ("drumbus", "hat"), ("bass", "perc")]

    n_nat = 0
    for ses, pairs in NATURAL_PAIRS.items():
        for fa, fb, rel in pairs:
            pa = next((p for p in stem_files
                       if p.relative_to(S.STEM_ROOT).parts[0] == ses
                       and p.name.endswith(fa)), None)
            pb = next((p for p in stem_files
                       if p.relative_to(S.STEM_ROOT).parts[0] == ses
                       and p.name.endswith(fb)), None)
            if not pa or not pb:
                continue
            try:
                xa, xb = load_wav(pa), load_wav(pb)
            except AudioLoadError:
                continue
            ya, yb, frs, rsflag = pair_rates(xa, xb)
            proc = {"resampled_b": rsflag} if rsflag else {}
            cat = ("kick" if "kick" in rel or "sub" in rel else
                   "snare" if "snare" in rel or "clap" in rel else
                   "bass" if "bass" in rel else
                   "multimic" if "in_out" in rel or "top_bottom" in rel
                   or "oh" in rel else "production")
            add(f"nat|{ses[:14]}|{rel}", "NATURAL", cat, rel,
                ya, yb, frs, expected="UNKNOWN", ga=ses, gb=ses,
                processing=proc)
            n_nat += 1

    # fallback sweep to reach breadth across every session
    existing_rel = {c.relationship for c in cases if c.klass == "NATURAL"}
    for ses, roles in session_roles.items():
        if ses.startswith("_"):
            continue
        for ra, rb in FALLBACK_COMBOS:
            if ra not in roles or rb not in roles:
                continue
            rel_name = f"{ra}_{rb}"
            if any(c.case_id.startswith(f"nat|{ses[:14]}") and
                   c.relationship == rel_name for c in cases):
                continue
            pa = roles[ra][len(roles[ra]) // 2]
            pb = roles[rb][len(roles[rb]) // 2]
            try:
                xa, xb = load_wav(pa), load_wav(pb)
            except AudioLoadError:
                continue
            cat = ra if ra in ("kick", "bass") else                 ("snare" if "snare" in rel_name else "production")
            add(f"nat|{ses[:14]}|fb|{rel_name}", "NATURAL", cat, rel_name,
                xa.samples, xb.samples, xa.sample_rate,
                expected="UNKNOWN", ga=ses, gb=ses)
            n_nat += 1
    log(f"natural cases: {n_nat}")

    summary = {"controlled": n_ctl, "healthy": n_healthy, "natural": n_nat}
    (OUT / "corpus_summary.json").write_text(json.dumps(summary, indent=1))
    (OUT / "used_sources.json").write_text(
        json.dumps(used_manifest, indent=1))

    # serialise cases (audio kept out of JSON; stored as npz shards)
    store = DERIVED / "cases.npz"
    arrays, metas = {}, []
    for i, c in enumerate(cases):
        arrays[f"a{i}"] = c.a.astype(np.float32)
        arrays[f"b{i}"] = c.b.astype(np.float32)
        m = c.meta(); m["fs"] = c.fs; m["index"] = i
        metas.append(m)
    np.savez_compressed(store, **arrays)
    (DERIVED / "cases_meta.json").write_text(json.dumps(metas, indent=1))
    log(f"stored {len(cases)} cases -> {store}")
    return summary


def load_cases():
    metas = json.loads((DERIVED / "cases_meta.json").read_text())
    data = np.load(DERIVED / "cases.npz")
    out = []
    for m in metas:
        i = m["index"]
        out.append(PairCase(
            case_id=m["case_id"], klass=m["class"], category=m["category"],
            relationship=m["relationship"], fs=m["fs"],
            a=data[f"a{i}"].astype(np.float64),
            b=data[f"b{i}"].astype(np.float64),
            provenance_category=m["provenance_category"],
            truth_offset_samples=m["truth_offset_samples"],
            truth_polarity=m["truth_polarity"],
            expected_action=m["expected_action"],
            processing=m.get("processing", {})))
    return out


# ------------------------------------------------------------------ run

def stage_run():
    cases = load_cases()
    records = []
    for i, c in enumerate(cases):
        t0 = time.time()
        r = analyse_case(c)
        records.append(r)
        if i % 20 == 0:
            log(f"engine {i}/{len(cases)} ({time.time()-t0:.1f}s last)")
    (OUT / "records.json").write_text(json.dumps(records_to_json(records),
                                                 indent=1))
    log(f"records written: {len(records)}")
    return records


# ----------------------------------------------------------------- pack

def stage_pack(records=None):
    if records is None:
        records = [{**r, "_a": None, "_b": None} for r in
                   json.loads((OUT / "records.json").read_text())]
        # reload audio for actionable cases only
        meta_by_id = {m["case_id"]: m for m in
                      json.loads((DERIVED / "cases_meta.json").read_text())}
        data = np.load(DERIVED / "cases.npz")
        keep = []
        for r in records:
            is_align = r["product_output"]["action"] == "ALIGN"
            if is_align or r["meta"]["class"] == "HEALTHY":
                i = meta_by_id[r["meta"]["case_id"]]["index"]
                r["_a"] = data[f"a{i}"].astype(np.float64)
                r["_b"] = data[f"b{i}"].astype(np.float64)
            else:
                r["_a"] = r["_b"] = None
            keep.append(r)
        records = keep
    # stratify: all natural ALIGN by confidence band, cap 60
    aligns = [r for r in records
              if r["product_output"]["action"] == "ALIGN"
              and r["meta"]["class"] == "NATURAL"]
    aligns.sort(key=lambda r: -float(r["product_output"].get("confidence", 0)))
    bands = {"high": [], "mid": [], "lower": []}
    for r in aligns:
        c = float(r["product_output"].get("confidence", 0))
        b = "high" if c >= 0.85 else "mid" if c >= 0.6 else "lower"
        if len(bands[b]) < 24:
            bands[b].append(r)
    chosen = bands["high"] + bands["mid"] + bands["lower"]

    # deterministic consistency traps: both slots ORIGINAL
    traps = []
    healthy_nat = [r for r in records if r["meta"]["class"] == "HEALTHY"][:12]
    for r in healthy_nat:
        rr = dict(r)
        rr["_trap_original_only"] = True
        traps.append(rr)

    # stratified CONTROLLED auditions (real audio, known-truth alignment):
    # these measure "when it recommends, does the change help by ear?"
    ctl_align = [r for r in records
                 if r["product_output"]["action"] == "ALIGN"
                 and r["meta"]["class"] == "CONTROLLED"]
    by_dom = defaultdict(list)
    for r in ctl_align:
        by_dom[r["meta"]["category"]].append(r)
    ctl_pick = []
    quota = [("kick", 8), ("snare", 5), ("clap", 3), ("bass", 5),
             ("perc", 3), ("synth", 4), ("vocal", 2)]
    for dom, q in quota:
        pool = sorted(by_dom.get(dom, []),
                      key=lambda r: -float(r["product_output"].
                                           get("confidence", 0)))
        ctl_pick += pool[:q]
    for r in ctl_pick:
        i = meta_by_id[r["meta"]["case_id"]]["index"]
        r["_a"] = data[f"a{i}"].astype(np.float64)
        r["_b"] = data[f"b{i}"].astype(np.float64)
    pack_input = chosen + ctl_pick + traps
    pack = build_pack(pack_input, BLIND)
    # rewrite traps so both slots serve ORIGINAL
    for e in pack["entries"]:
        cid = e["case_id"].replace("|REPEAT", "")
        if any(t["meta"]["case_id"] == cid and t.get("_trap_original_only")
               for t in pack_input):
            e["slot_a"] = e["slot_b"] = "ORIGINAL"
    (BLIND / "pack_manifest.json").write_text(json.dumps(pack, indent=1))
    order = sorted(pack["entries"], key=lambda e: hashlib.sha256(
        (pack["blind_seed"] + e["case_id"]).encode()).hexdigest())
    (BLIND / "presentation_order.json").write_text(
        json.dumps(order, indent=1))
    (OUT / "blind_pack_summary.json").write_text(json.dumps({
        "natural_align_entries": len(chosen),
        "controlled_auditions": len(ctl_pick),
        "consistency_traps": len(traps),
        "total": len(pack["entries"]),
        "blind_seed": pack["blind_seed"],
        "note": "natural ALIGN count limited by real-material coverage; "
                "controlled auditions added so the review can measure "
                "'do recommendations help by ear' on known-truth cases",
    }, indent=1))
    log(f"blind pack: {len(chosen)} natural align + {len(ctl_pick)} "
        f"controlled + {len(traps)} traps (+repeats) = "
        f"{len(pack['entries'])}")


# -------------------------------------------------------------- metrics

def stage_metrics():
    records = json.loads((OUT / "records.json").read_text())
    ctl = [r for r in records if r["meta"]["class"] == "CONTROLLED"
           and r["product_output"]["action"] == "ALIGN"]
    errs_int, errs_frac, within = [], [], {0.25: 0, 1: 0, 2: 0}
    pol_ok, pol_n = 0, 0
    by_domain = defaultdict(list)
    for r in ctl:
        po = r["product_output"]
        truth = float(r["meta"]["truth_offset_samples"] or 0)
        est = float(po.get("offset_samples", 0))
        err = est - truth
        is_frac = abs(truth - round(truth)) > 1e-9
        (errs_frac if is_frac else errs_int).append(abs(err))
        for k in within:
            within[k] += int(abs(err) <= k)
        if po.get("apply_polarity_flip"):
            pol_n += 1
            pol_ok += int(r["meta"]["truth_polarity"] == -1)
        by_domain[r["meta"]["category"]].append(abs(err))
    healthy = [r for r in records
               if r["meta"]["expected_action"] == "NO_ACTION"]
    fps = [r for r in healthy if r["product_output"]["action"] in
           ("ALIGN", "BANDWISE_WARNING")]
    nat = [r for r in records if r["meta"]["class"] == "NATURAL"]
    actions = Counter(r["product_output"]["action"] for r in nat)
    conf_buckets = defaultdict(lambda: {"n": 0, "align": 0})
    for r in nat:
        c = float(r["product_output"].get("confidence", 0) or 0)
        b = min(int(c * 10), 9) / 10.0
        key = f"{b:.1f}-{b+0.1:.1f}"
        conf_buckets[key]["n"] += 1
        conf_buckets[key]["align"] += int(
            r["product_output"]["action"] == "ALIGN")

    metrics = {
        "controlled_actionable": len(ctl),
        "offset_mae_samples": round(float(np.mean(errs_int)), 4)
        if errs_int else None,
        "fractional_mae_samples": round(float(np.mean(errs_frac)), 4)
        if errs_frac else None,
        "within_0.25": round(within[0.25] / max(1, len(errs_int) +
                                                len(errs_frac)), 4),
        "within_1": round(within[1] / max(1, len(errs_int) +
                                          len(errs_frac)), 4),
        "within_2": round(within[2] / max(1, len(errs_int) +
                                          len(errs_frac)), 4),
        "polarity_accuracy_when_flipped_suggested":
            round(pol_ok / pol_n, 4) if pol_n else None,
        "healthy_cases": len(healthy),
        "healthy_false_positive_rate": round(len(fps) / max(1, len(healthy)),
                                             4),
        "healthy_fp_case_ids": [r["meta"]["case_id"] for r in fps][:30],
        "natural_actions": dict(actions),
        "actionable_coverage_natural": round(
            actions.get("ALIGN", 0) / max(1, len(nat)), 4),
        "abstention_rate_overall": round(
            sum(1 for r in records
                if r["product_output"]["action"] in
                ("NO_ACTION", "ABSTAIN")) / max(1, len(records)), 4),
        "confidence_calibration_alignment_share": {
            k: {"n": v["n"], "align_share": round(v["align"] / v["n"], 3)}
            for k, v in sorted(conf_buckets.items())},
        "mae_by_domain": {k: round(float(np.mean(v)), 3)
                          for k, v in by_domain.items()},
    }
    (OUT / "qualification_metrics.json").write_text(json.dumps(metrics,
                                                               indent=1))
    log(json.dumps(metrics, indent=1)[:1500])
    return metrics


# ---------------------------------------------------------------- parity

def stage_parity():
    spike = ROOT / "cpp_spike" / "nla_spike"
    tmp = Path("/var/folders/7n/v41hqm4s3rx4vd536fghb0zh0000gn/T/opencode")
    records = json.loads((OUT / "records.json").read_text())
    meta = {m["case_id"]: m for m in
            json.loads((DERIVED / "cases_meta.json").read_text())}
    data = np.load(DERIVED / "cases.npz")
    from src.nla import methods as M
    picks = [r for r in records
             if r["meta"]["class"] in ("CONTROLLED", "NATURAL")][:10]
    rows = []
    for r in picks:
        i = meta[r["meta"]["case_id"]]["index"]
        a = data[f"a{i}"].astype(np.float32)
        b = data[f"b{i}"].astype(np.float32)
        fa, fb = tmp / "pa.f32", tmp / "pb.f32"
        a.tofile(fa); b.tofile(fb)
        out = subprocess.run([str(spike), str(fa), str(fb), str(len(a)),
                              "256", "0.35"], capture_output=True, text=True)
        ox, _, og, _, _ = map(float, out.stdout.strip().split(","))
        px = M.xcorr_plain(a.astype(np.float64), b.astype(np.float64),
                           256)["offset_samples"]
        pg = M.gcc_soft(a.astype(np.float64), b.astype(np.float64),
                        meta[r["meta"]["case_id"]]["fs"])["offset_samples"]
        rows.append({"case_id": r["meta"]["case_id"],
                     "agree_xcorr": bool(abs(ox - px) <= 0.15),
                     "agree_gcc": bool(abs(og - pg) <= 0.15),
                     "dx": round(abs(ox - px), 4),
                     "dg": round(abs(og - pg), 4)})
    res = {"rows": rows,
           "pass": all(r["agree_xcorr"] and r["agree_gcc"] for r in rows)}
    (OUT / "cpp_real_audio_parity.json").write_text(json.dumps(res, indent=1))
    log(f"parity pass: {res['pass']}")


# ----------------------------------------------------------------- bench

def stage_bench():
    from eval import bench as B
    data = np.load(DERIVED / "cases.npz")
    meta = json.loads((DERIVED / "cases_meta.json").read_text())
    nat = [m for m in meta if m["class"] == "NATURAL"][:8]
    pairs = []
    for m in nat:
        i = m["index"]
        pairs.append((data[f"a{i}"].astype(np.float64)[:48000],
                      data[f"b{i}"].astype(np.float64)[:48000], m["fs"]))
    res = B.run(pairs)
    (OUT / "bench.json").write_text(json.dumps(res, indent=1))
    log(f"bench uncontested={res['uncontested']} "
        f"p50={res['ms_p50']}ms p95={res['ms_p95']}ms")


STAGES = {"survey": stage_survey, "build": stage_build, "run": stage_run,
          "pack": stage_pack, "metrics": stage_metrics,
          "parity": stage_parity, "bench": stage_bench}

if __name__ == "__main__":
    for st in (sys.argv[1:] or ["all"]):
        for name, fn in STAGES.items():
            if st in (name, "all"):
                log(f"=== {name} ===")
                fn()
