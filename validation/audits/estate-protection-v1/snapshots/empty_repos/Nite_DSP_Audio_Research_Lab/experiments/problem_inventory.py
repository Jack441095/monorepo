"""Build the 55-problem inventory, weighted ranking, and portfolio selection."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lab.registry import save_json, LAB_ROOT  # noqa: E402

WEIGHTS = {
    "USER_PAIN": 0.14,
    "FREQUENCY": 0.12,
    "TIME_SAVED": 0.12,
    "MEASURABILITY": 0.09,
    "GROUND_TRUTH_QUALITY": 0.10,
    "TECHNICAL_FEASIBILITY": 0.12,
    "DIFFERENTIATION": 0.08,
    "REALTIME_FEASIBILITY": 0.06,
    "FALSE_POSITIVE_SAFETY": 0.09,
    "NITE_STRATEGIC_FIT": 0.08,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

P = []


def add(pid, domain, problem, user, workflow, manual, freq, pain, measur, gtq, feas, diff, rt, fp_safe, fit, dsp, ml, hybrid, product, rcost):
    P.append({
        "problem_id": pid,
        "domain": domain,
        "problem": problem,
        "user": user,
        "workflow": workflow,
        "current_manual_process": manual,
        "frequency_per_project": freq,
        "scores_0_10": {
            "USER_PAIN": pain,
            "FREQUENCY": freq_score_map[freq],
            "TIME_SAVED": time_map[manual],
        },
        "technical_measurability": measur,
        "ground_truth_feasibility": gtq,
        "automation_potential": feas,
        "false_positive_risk": 10 - fp_safe,
        "dsp_suitability": dsp,
        "ml_suitability": ml,
        "hybrid_suitability": hybrid,
        "product_opportunity": product,
        "research_cost": rcost,
    })


freq_score_map = {"daily": 10, "most-projects": 8, "common": 6, "occasional": 4, "rare": 2}
time_map = {
    "ear + solo/flip polarity by trial": 7,
    "nudge regions against each other by ear": 8,
    "sweep analyzer overlays by hand": 5,
    "A/B mono button + experience": 6,
    "trial-and-error EQ/notching by ear": 6,
    "manual gain riding and meter watching": 4,
    "listen on multiple systems iteratively": 7,
    "browse hundreds of samples by ear": 9,
    "audition transposition ranges manually": 6,
    "meter checks (built-in DAW)": 3,
}


def full(pid, domain, problem, user, workflow, manual_key, freq_key, scores, dsp, ml, hybrid, product, rcost, extra=None):
    alias = {
        "USER_PAIN": "USER_PAIN", "FREQUENCY": "FREQUENCY", "TIME_SAVED": "TIME_SAVED",
        "MEASURABILITY": "MEASURABILITY", "GROUND_TRUTH": "GROUND_TRUTH_QUALITY",
        "FEASIBILITY": "TECHNICAL_FEASIBILITY", "DIFFERENTIATION": "DIFFERENTIATION",
        "REALTIME": "REALTIME_FEASIBILITY", "FP_TOLERANCE": "FALSE_POSITIVE_SAFETY",
        "FIT": "NITE_STRATEGIC_FIT",
    }
    s = {alias[k.upper()]: v for k, v in scores.items()}
    P.append({
        "problem_id": pid,
        "domain": domain,
        "problem": problem,
        "user": user,
        "workflow": workflow,
        "current_manual_process": manual_key,
        "frequency": freq_key,
        "frequency_per_project": freq_key,
        "pain_qualitative": s["USER_PAIN"],
        "scores_0_10": s,
        "dsp_suitability": dsp,
        "ml_suitability": ml,
        "hybrid_suitability": hybrid,
        "product_opportunity": product,
        "research_cost": rcost,
        **(extra or {}),
    })


# ---- A/B Layer alignment & phase -----------------------------------------
full("P01", "layer_alignment", "Multi-layer transient timing alignment (kick/snare/clap stacks)",
     "producer/engineer", "drum design, layering", "nudge regions against each other by ear", "most-projects",
     dict(user_pain=8, frequency=8, time_saved=8, measurability=9, ground_truth=9, feasibility=9, differentiation=7, realtime=7, fp_tolerance=6, fit=9),
     9, 3, 8, "Alignment assistant (Product #2 candidate)", 2)
full("P02", "layer_alignment", "Polarity decision per layer",
     "producer/engineer", "drum/bass layering, multi-mic", "ear + solo/flip polarity by trial", "most-projects",
     dict(user_pain=8, frequency=8, time_saved=7, measurability=9, ground_truth=9, feasibility=9, differentiation=7, realtime=7, fp_tolerance=4, fit=9),
     9, 2, 8, "same as P01", 2)
full("P03", "phase", "Frequency-dependent (all-pass) misalignment detection",
     "mix engineer", "filtered layers, linear-phase confusion", "ear + null test by trial", "occasional",
     dict(user_pain=6, frequency=5, time_saved=6, measurability=8, ground_truth=8, feasibility=6, differentiation=8, realtime=5, fp_tolerance=4, fit=8),
     8, 3, 7, "advanced mode of alignment tool", 4)
full("P04", "layer_alignment", "Snare/clap stack alignment",
     "producer", "drum design", "nudge regions against each other by ear", "most-projects",
     dict(user_pain=7, frequency=7, time_saved=7, measurability=8, ground_truth=8, feasibility=9, differentiation=6, realtime=7, fp_tolerance=6, fit=8),
     9, 2, 8, "same as P01", 2)
full("P05", "phase", "Parallel processing path latency compensation",
     "engineer", "parallel comp, split chains", "manual delay compensation / plugin reporting", "common",
     dict(user_pain=6, frequency=6, time_saved=7, measurability=9, ground_truth=9, feasibility=8, differentiation=5, realtime=8, fp_tolerance=8, fit=7),
     9, 1, 8, "DAW utility; low standalone pull", 3)
full("P06", "layer_alignment", "Sample-replacement timing to original performance",
     "producer", "draug replacement", "ear + nudge", "common",
     dict(user_pain=6, frequency=6, time_saved=6, measurability=8, ground_truth=8, feasibility=8, differentiation=5, realtime=7, fp_tolerance=6, fit=7),
     8, 3, 7, "SLO adjacent feature", 3)
full("P07", "phase", "Multi-mic drum phase alignment (OH vs close)",
     "engineer", "drum mixing", "ear + flip/nudge per mic", "occasional",
     dict(user_pain=6, frequency=4, time_saved=6, measurability=8, ground_truth=7, feasibility=7, differentiation=6, realtime=6, fp_tolerance=4, fit=6),
     8, 3, 7, "alignment tool vertical", 4)
full("P08", "layer_alignment", "Abstention: double-tracks/loose performances must NOT be tightened",
     "producer", "vocal/guitar doubles", "none (knowing when not to)", "common",
     dict(user_pain=5, frequency=6, time_saved=4, measurability=7, ground_truth=6, feasibility=6, differentiation=7, realtime=6, fp_tolerance=2, fit=7),
     6, 5, 6, "abstention layer of alignment tool", 3)

# ---- C/D Low end -----------------------------------------------------------
full("P09", "low_end", "Kick/bass fundamental collision detection",
     "producer/engineer", "low-end balancing", "sweep analyzer overlays by hand", "most-projects",
     dict(user_pain=8, frequency=8, time_saved=7, measurability=8, ground_truth=7, feasibility=8, differentiation=7, realtime=6, fp_tolerance=6, fit=9),
     8, 4, 8, "Low-end intelligence panel", 3)
full("P10", "low_end", "Low-frequency partial cancellation detection",
     "producer/engineer", "low-end balancing", "A/B mono + flip by ear", "most-projects",
     dict(user_pain=8, frequency=7, time_saved=7, measurability=8, ground_truth=8, feasibility=8, differentiation=7, realtime=6, fp_tolerance=6, fit=9),
     8, 3, 8, "Low-end intelligence panel", 3)
full("P11", "low_end", "Bass decay masking next kick transient",
     "producer/engineer", "groove clarity", "ear + gain rides", "most-projects",
     dict(user_pain=6, frequency=7, time_saved=5, measurability=8, ground_truth=7, feasibility=8, differentiation=7, realtime=5, fp_tolerance=5, fit=8),
     8, 4, 8, "Low-end intelligence panel", 3)
full("P12", "low_end", "Sidechain necessity detection",
     "producer", "EDM/pop low end", "trial-and-error EQ/notching by ear", "common",
     dict(user_pain=6, frequency=7, time_saved=5, measurability=7, ground_truth=6, feasibility=7, differentiation=6, realtime=6, fp_tolerance=5, fit=7),
     7, 4, 7, "advice module", 3)
full("P13", "stereo", "Sub-bass mono compatibility (club systems)",
     "producer/engineer", "master prep", "A/B mono button + experience", "common",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=8, ground_truth=8, feasibility=8, differentiation=5, realtime=7, fp_tolerance=8, fit=7),
     8, 2, 8, "mastering checklist item", 2)
full("P14", "low_end", "Kick tuning vs track key relation",
     "producer", "sound design", "tune by ear to root note", "common",
     dict(user_pain=5, frequency=6, time_saved=5, measurability=7, ground_truth=6, feasibility=7, differentiation=5, realtime=6, fp_tolerance=6, fit=6),
     7, 4, 7, "SLO adjacent advice", 3)
full("P15", "gain", "Headroom inefficiency from low-end summation",
     "engineer", "gain staging", "meter checks (built-in DAW)", "most-projects",
     dict(user_pain=6, frequency=8, time_saved=5, measurability=8, ground_truth=8, feasibility=8, differentiation=6, realtime=7, fp_tolerance=7, fit=8),
     8, 2, 8, "headroom report", 2)

# ---- E Masking -------------------------------------------------------------
full("P16", "masking", "Vocal vs lead synth masking",
     "mix engineer", "vocal clarity", "trial-and-error EQ/notching by ear", "most-projects",
     dict(user_pain=7, frequency=7, time_saved=6, measurability=7, ground_truth=6, feasibility=7, differentiation=6, realtime=5, fp_tolerance=4, fit=8),
     7, 6, 8, "masking map", 4)
full("P17", "masking", "Time-frequency critical-band overlap vs static spectrum overlap",
     "mix engineer", "mix clarity triage", "sweep analyzer overlays by hand", "most-projects",
     dict(user_pain=7, frequency=8, time_saved=7, measurability=8, ground_truth=7, feasibility=7, differentiation=8, realtime=5, fp_tolerance=4, fit=8),
     8, 5, 8, "masking intelligence core", 3)
full("P18", "masking", "Harmonic density masking in dense arrangements",
     "producer", "arrangement", "ear + mute faders", "common",
     dict(user_pain=5, frequency=6, time_saved=4, measurability=6, ground_truth=5, feasibility=6, differentiation=6, realtime=4, fp_tolerance=4, fit=6),
     6, 6, 7, "arrangement advisor", 4)
full("P19", "masking", "Discriminate benign/musical overlap from problematic masking",
     "mix engineer", "mix triage", "ear only", "most-projects",
     dict(user_pain=8, frequency=8, time_saved=7, measurability=7, ground_truth=6, feasibility=6, differentiation=8, realtime=5, fp_tolerance=3, fit=8),
     7, 7, 8, "trust layer of masking map", 3)
full("P20", "arrangement", "Frequency hoarding across arrangement density",
     "producer", "arrangement review", "ear + solo browsing", "common",
     dict(user_pain=5, frequency=5, time_saved=4, measurability=7, ground_truth=6, feasibility=7, differentiation=6, realtime=4, fp_tolerance=6, fit=6),
     7, 5, 7, "arrangement heatmap", 3)

# ---- F Transients/dynamics -------------------------------------------------
full("P21", "dynamics", "Transient smearing detection after limiting",
     "engineer", "mastering/loudness", "ear + sample A/B", "common",
     dict(user_pain=6, frequency=6, time_saved=4, measurability=7, ground_truth=6, feasibility=7, differentiation=6, realtime=6, fp_tolerance=6, fit=7),
     8, 4, 7, "loudness quality check", 3)
full("P22", "dynamics", "Over-compression / punch-loss detection",
     "producer/engineer", "bus/master dynamics", "ear + meter", "most-projects",
     dict(user_pain=7, frequency=7, time_saved=5, measurability=8, ground_truth=7, feasibility=8, differentiation=5, realtime=7, fp_tolerance=6, fit=7),
     8, 4, 7, "dynamics health panel", 2)
full("P23", "transients", "Layered percussion reinforcement vs cancellation",
     "producer", "drum design", "ear + solo layers", "most-projects",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=8, ground_truth=8, feasibility=8, differentiation=6, realtime=6, fp_tolerance=6, fit=8),
     8, 2, 8, "alignment tool sibling", 3)
full("P24", "transients", "Attack-slope conflict between stacked layers",
     "producer", "drum design", "ear + envelope editors", "occasional",
     dict(user_pain=4, frequency=5, time_saved=3, measurability=7, ground_truth=6, feasibility=7, differentiation=6, realtime=6, fp_tolerance=5, fit=6),
     7, 4, 6, "layer doctor", 3)
full("P25", "transients", "Transient-density overload in busy sections",
     "producer", "arrangement", "ear", "occasional",
     dict(user_pain=4, frequency=4, time_saved=3, measurability=6, ground_truth=5, feasibility=6, differentiation=5, realtime=5, fp_tolerance=5, fit=5),
     6, 5, 6, "arrangement advisor", 3)

# ---- G Stereo --------------------------------------------------------------
full("P26", "stereo", "Mono-collapse risk quantification with band localisation",
     "producer/engineer", "mix/master QC", "mono button + guess band", "most-projects",
     dict(user_pain=7, frequency=7, time_saved=6, measurability=8, ground_truth=8, feasibility=8, differentiation=6, realtime=7, fp_tolerance=6, fit=8),
     9, 3, 8, "stereo doctor", 2)
full("P27", "stereo", "Side-heavy bass detection",
     "engineer", "mix QC", "mono button + bass walk", "common",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=8, ground_truth=8, feasibility=8, differentiation=6, realtime=7, fp_tolerance=8, fit=7),
     8, 2, 8, "stereo doctor", 2)
full("P28", "stereo", "Asymmetric stereo / image shift",
     "engineer", "mix QC", "L/R solo flip", "common",
     dict(user_pain=5, frequency=5, time_saved=4, measurability=7, ground_truth=7, feasibility=7, differentiation=5, realtime=7, fp_tolerance=7, fit=6),
     7, 2, 7, "stereo doctor", 2)
full("P29", "stereo", "False-positive-safe width assessment (Haas/decorrelated reverb is legal)",
     "tool designer", "QC automation design", "none today (tools cry wolf)", "common",
     dict(user_pain=5, frequency=6, time_saved=5, measurability=8, ground_truth=7, feasibility=8, differentiation=7, realtime=6, fp_tolerance=4, fit=7),
     8, 4, 7, "trust benchmark for stereo tools", 3)
full("P30", "stereo", "Reverb-return correlation problems",
     "engineer", "spatial mix", "ear", "occasional",
     dict(user_pain=4, frequency=4, time_saved=3, measurability=7, ground_truth=6, feasibility=7, differentiation=5, realtime=6, fp_tolerance=7, fit=5),
     7, 3, 6, "stereo doctor extra", 3)

# ---- H Resonance/harshness --------------------------------------------------
full("P31", "resonance", "Stable resonance vs musical harmonic discrimination",
     "mix/master engineer", "tonal correction", "sweep + notch by ear", "most-projects",
     dict(user_pain=7, frequency=7, time_saved=6, measurability=8, ground_truth=7, feasibility=7, differentiation=6, realtime=5, fp_tolerance=4, fit=7),
     8, 5, 8, "resonance scanner", 3)
full("P32", "resonance", "Harshness detection in 2-5 kHz region",
     "mix engineer", "vocal/synth harshness", "de-harsh by ear", "common",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=6, ground_truth=5, feasibility=6, differentiation=5, realtime=6, fp_tolerance=4, fit=6),
     6, 6, 7, "resonance scanner mode", 4)
full("P33", "resonance", "Sibilance energy profiling for de-ess guidance",
     "mix engineer", "vocal chain", "de-esser by ear+meter", "common",
     dict(user_pain=6, frequency=6, time_saved=4, measurability=7, ground_truth=7, feasibility=7, differentiation=4, realtime=7, fp_tolerance=6, fit=6),
     7, 4, 7, "well-served category; low differentiation", 2)
full("P34", "resonance", "Low-mid build-up diagnosis",
     "mix engineer", "tonal balance", "reference A/B by ear", "common",
     dict(user_pain=5, frequency=6, time_saved=4, measurability=7, ground_truth=5, feasibility=6, differentiation=4, realtime=6, fp_tolerance=5, fit=6),
     6, 5, 7, "tone balance report", 3)
full("P35", "resonance", "Temporary spectral peak vs persistent resonance",
     "master engineer", "resonance control", "dynamic EQ by ear", "common",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=7, ground_truth=7, feasibility=7, differentiation=6, realtime=5, fp_tolerance=6, fit=6),
     8, 4, 7, "resonance scanner temporal mode", 3)

# ---- I Translation ----------------------------------------------------------
full("P36", "translation", "Phone-speaker robustness indicators",
     "producer", "translation checks", "listen on multiple systems iteratively", "most-projects",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=6, ground_truth=4, feasibility=6, differentiation=6, realtime=5, fp_tolerance=5, fit=7),
     6, 6, 7, "translation predictor", 4)
full("P37", "translation", "Mono translation loss prediction",
     "producer/engineer", "translation checks", "mono button + experience", "most-projects",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=7, ground_truth=6, feasibility=7, differentiation=5, realtime=6, fp_tolerance=6, fit=7),
     7, 4, 7, "translation predictor", 3)
full("P38", "translation", "Small-speaker LF rolloff audibility check",
     "producer", "translation checks", "car/phone test", "common",
     dict(user_pain=5, frequency=5, time_saved=4, measurability=6, ground_truth=4, feasibility=6, differentiation=5, realtime=5, fp_tolerance=6, fit=6),
     5, 5, 6, "translation predictor", 4)
full("P39", "translation", "Club/car LF-emphasis robustness",
     "producer", "genre masters", "club playtest", "occasional",
     dict(user_pain=4, frequency=4, time_saved=3, measurability=6, ground_truth=4, feasibility=5, differentiation=5, realtime=5, fp_tolerance=6, fit=5),
     5, 5, 6, "translation predictor", 4)
full("P40", "translation", "Streaming loudness normalisation mismatch prediction",
     "producer", "delivery", "meter + platform docs", "common",
     dict(user_pain=5, frequency=6, time_saved=5, measurability=8, ground_truth=7, feasibility=8, differentiation=3, realtime=7, fp_tolerance=8, fit=6),
     9, 2, 8, "delivery checker", 2)

# ---- K/L/M Samples & context -------------------------------------------------
full("P41", "sample_context", "Sample-in-context compatibility scoring ('fits THIS track')",
     "producer", "sample selection", "browse hundreds of samples by ear", "most-projects",
     dict(user_pain=7, frequency=8, time_saved=7, measurability=6, ground_truth=5, feasibility=6, differentiation=8, realtime=6, fp_tolerance=4, fit=9),
     6, 7, 8, "SLO_CANDIDATE contextual ranker", 4)
full("P42", "timbre", "Timbre matching for layering suggestions",
     "producer", "layering", "ear + library browsing", "common",
     dict(user_pain=6, frequency=7, time_saved=6, measurability=6, ground_truth=5, feasibility=6, differentiation=7, realtime=5, fp_tolerance=5, fit=8),
     6, 7, 8, "SLO_CANDIDATE", 4)
full("P43", "sample_context", "Sample key/fundamental clash detection",
     "producer", "sample use", "tune by ear / key finder apps", "common",
     dict(user_pain=6, frequency=7, time_saved=5, measurability=7, ground_truth=6, feasibility=7, differentiation=4, realtime=6, fp_tolerance=6, fit=7),
     7, 4, 7, "SLO_CANDIDATE flag", 3)
full("P44", "sample_context", "One-shot class/transient matching for replacement",
     "producer", "replacement workflows", "library filter + ear", "common",
     dict(user_pain=5, frequency=6, time_saved=4, measurability=7, ground_truth=6, feasibility=7, differentiation=4, realtime=6, fp_tolerance=6, fit=6),
     7, 5, 7, "SLO_CANDIDATE", 3)
full("P45", "sample_context", "Library OOD detection (sample unlike anything in library)",
     "SLO system", "taxonomy/QC", "none", "common",
     dict(user_pain=5, frequency=5, time_saved=4, measurability=7, ground_truth=5, feasibility=6, differentiation=6, realtime=6, fp_tolerance=5, fit=8),
     6, 6, 7, "SLO_CANDIDATE OOD gate", 3)

# ---- J Gain -------------------------------------------------------------------
full("P46", "gain", "Gain-staging inconsistency across stems",
     "producer", "session setup", "manual meter watching", "common",
     dict(user_pain=5, frequency=6, time_saved=5, measurability=7, ground_truth=6, feasibility=7, differentiation=3, realtime=7, fp_tolerance=7, fit=6),
     7, 2, 7, "session hygiene scan", 2)
full("P47", "gain", "Delivery loudness target deviation early warning",
     "producer", "delivery", "offline metering", "common",
     dict(user_pain=5, frequency=6, time_saved=5, measurability=8, ground_truth=7, feasibility=8, differentiation=3, realtime=7, fp_tolerance=8, fit=6),
     8, 1, 7, "delivery checker", 2)
full("P48", "gain", "Bus overload / intersample peak risk",
     "engineer", "mastering", "true-peak meters", "common",
     dict(user_pain=5, frequency=6, time_saved=4, measurability=8, ground_truth=8, feasibility=8, differentiation=4, realtime=6, fp_tolerance=8, fit=6),
     8, 2, 8, "mastering checklist", 2)

# ---- P Reverb/spatial ----------------------------------------------------------
full("P49", "reverb", "Reverb tail masking following transients",
     "mix engineer", "spatial balance", "ear + freeze prints", "common",
     dict(user_pain=5, frequency=5, time_saved=3, measurability=7, ground_truth=6, feasibility=6, differentiation=6, realtime=5, fp_tolerance=5, fit=6),
     7, 5, 7, "space advisor", 4)
full("P50", "reverb", "Pre-delay/early-reflection clutter diagnosis",
     "mix engineer", "spatial balance", "ear", "occasional",
     dict(user_pain=4, frequency=4, time_saved=3, measurability=5, ground_truth=4, feasibility=5, differentiation=5, realtime=4, fp_tolerance=5, fit=5),
     5, 5, 6, "space advisor", 4)
full("P51", "reverb", "Ambience balance judged in context of arrangement density",
     "producer", "spatial balance", "ear + section solos", "common",
     dict(user_pain=4, frequency=5, time_saved=3, measurability=5, ground_truth=4, feasibility=5, differentiation=4, realtime=4, fp_tolerance=4, fit=5),
     5, 6, 6, "context engine seed", 4)

# ---- R Clipping ----------------------------------------------------------------
full("P52", "distortion", "Clipping diagnosis (hard clip vs intentional saturation)",
     "engineer", "QC", "waveform zoom + ear", "common",
     dict(user_pain=6, frequency=6, time_saved=5, measurability=8, ground_truth=7, feasibility=7, differentiation=5, realtime=6, fp_tolerance=6, fit=7),
     8, 4, 7, "session hygiene scan", 3)
full("P53", "distortion", "Intersample peak clipping risk on consumer DACs",
     "master engineer", "mastering QC", "ISP meters", "common",
     dict(user_pain=5, frequency=5, time_saved=4, measurability=8, ground_truth=8, feasibility=8, differentiation=4, realtime=6, fp_tolerance=8, fit=5),
     8, 2, 8, "mastering checklist", 2)

# ---- T Sampler -------------------------------------------------------------------
full("P54", "sampling", "Multi-zone sampling vs single-root extreme transposition",
     "instrument builder/producer", "sample instrument creation", "audition transposition ranges manually", "occasional",
     dict(user_pain=6, frequency=5, time_saved=6, measurability=8, ground_truth=7, feasibility=6, differentiation=9, realtime=5, fp_tolerance=7, fit=8),
     7, 5, 8, "smart zoning (SLO_CANDIDATE)", 4)
full("P55", "sampling", "Root-note/fundamental detection accuracy for sampled notes",
     "instrument builder", "zoning", "piano-roll compare by ear", "common",
     dict(user_pain=5, frequency=5, time_saved=5, measurability=7, ground_truth=7, feasibility=7, differentiation=6, realtime=6, fp_tolerance=6, fit=7),
     7, 4, 7, "prerequisite for P54", 3)


for p in P:
    assert set(p["scores_0_10"]) == set(WEIGHTS), p["problem_id"]

for p in P:
    p["weighted_total"] = round(sum(p["scores_0_10"][k] * w for k, w in WEIGHTS.items()), 3)

ranked = sorted(P, key=lambda p: -p["weighted_total"])
for i, p in enumerate(ranked, 1):
    p["rank"] = i

PORTFOLIO = ["P01", "P02", "P03", "P08", "P09", "P10", "P11", "P15", "P17", "P19", "P22", "P23",
             "P26", "P27", "P29", "P31", "P35", "P54"]
portfolio_set = set(PORTFOLIO)
for p in P:
    p["selected_for_portfolio"] = p["problem_id"] in portfolio_set

out = {
    "registry_version": "RESEARCH_PROBLEM_REGISTRY_1.0",
    "weights_documented_a_priori": WEIGHTS,
    "score_scale": "0-10, integer, judgment-based triage before experiments; not evidence",
    "fp_tolerance_definition": "10 = false positives are cheap/easily avoided; 2 = false positives destroy trust or cause damage",
    "n_problems": len(P),
    "problems": P,
}

save_json(os.path.join(LAB_ROOT, "controller", "RESEARCH_PROBLEM_REGISTRY.json"), out)

lines = [
    "# Research Problem Inventory & Weighted Ranking",
    "",
    f"{len(P)} problems inventoried across domains A-T.",
    "",
    "| Rank | ID | Domain | Problem | Score | Portfolio |",
    "|---:|---|---|---|---:|---|",
]
for p in ranked:
    lines.append(f"| {p['rank']} | {p['problem_id']} | {p['domain']} | {p['problem'][:70]} | {p['weighted_total']} | {'YES' if p['selected_for_portfolio'] else ''} |")
lines += [
    "",
    "## Selected research portfolio (18 problem IDs -> 6 experiment tracks + shared lib)",
    "",
    "- Track A (deterministic DSP, priority): P01, P02, P03, P04-family, P08 abstention, P23",
    "- Track B (contextual DSP): P09, P10, P11, P15",
    "- Track C (contextual analysis + ML-assisted classifier): P17, P19 (+P16 fixtures)",
    "- Track E (deterministic DSP + controls): P26, P27, P28, P29",
    "- Track F (deterministic DSP near-miss discipline): P31, P35",
    "- Track J (DSP/ML-assisted falsification): P54, P55",
    "- Workflow/product problem covered by Track A (alignment = Product #2 candidate under falsification)",
    "",
]
with open(os.path.join(LAB_ROOT, "reports", "PROBLEM_INVENTORY_AND_RANKING.md"), "w") as f:
    f.write("\n".join(lines))

print(f"problems={len(P)} top5=" + ", ".join(f"{p['problem_id']}({p['weighted_total']})" for p in ranked[:5]))
