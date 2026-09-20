#!/usr/bin/env python3
"""
SLO Multi-Stage Hierarchical Classification Cascade (V5.0 Architecture).

Stage 1: Coarse Category (Drums, Bass, Instruments, Vocals, FX, Ambience)
Stage 2: Temporal Type (One-Shot vs Loop vs Phrase vs Texture)
Stage 3: Fine Subcategory (Pad, Piano, Guitar, Pluck, Lead, Brass, Strings, Kick, Snare, Hat, Clap, etc.)
"""

import os
import sys
import csv
import numpy as np
import soundfile as sf
import librosa
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)

import name_detect as nd
import drum_detector_features as ddf
import loop_features as lf

# High-level category mapping
COARSE_CATEGORY_MAP = {
    "Kick": "Drums", "Snare": "Drums", "Hi-Hat": "Drums", "Clap": "Drums",
    "Rimshot": "Drums", "Crash": "Drums", "Ride": "Drums", "Tom": "Drums",
    "Drum Fill": "Drums", "Percussion": "Drums", "Drum Loop": "Drums",
    "Top Loop": "Drums", "Percussion Loop": "Drums", "Hi-Hat Loop": "Drums",
    
    "Bass": "Bass", "Bass One-Shot": "Bass", "Sub Bass": "Bass", "Bass Loop": "Bass",
    
    "Pad": "Instruments", "Piano": "Instruments", "Guitar": "Instruments",
    "Pluck": "Instruments", "Lead": "Instruments", "Brass": "Instruments",
    "Strings": "Instruments", "Organ": "Instruments", "Synth": "Instruments",
    "Synth Loop": "Instruments", "Chord Loop": "Instruments", "Pad Loop": "Instruments",
    
    "Vocal Chop": "Vocals", "Vocal Lead": "Vocals", "Vocal Phrase": "Vocals", "Vocal Loop": "Vocals",
    
    "Impact": "FX", "Riser": "FX", "Downlifter": "FX", "Foley": "FX",
    "Foley Loop": "Ambience", "Atmosphere": "Ambience", "Other/none": "Other"
}

def dur_of(path):
    try:
        i = sf.info(path)
        return i.frames / i.samplerate
    except:
        return 0.0

def decay_ratio(p):
    try:
        y, sr = sf.read(p, dtype='float32', always_2d=False)
        if y.ndim > 1: y = y.mean(1)
        n = len(y) // 3
        if n < 10: return 1.0
        return float(min((np.mean(y[-n:]**2) + 1e-9) / (np.mean(y[:n]**2) + 1e-9), 2.0))
    except:
        return 1.0

def onset_count(path):
    try:
        y, sr = sf.read(path, dtype='float32', always_2d=False)
        if y.ndim > 1: y = y.mean(1)
        if sr != 22050:
            y = librosa.resample(y, orig_sr=sr, target_sr=22050)
            sr = 22050
        oe = librosa.onset.onset_strength(y=y, sr=sr)
        return len(librosa.util.peak_pick(oe, pre_max=3, post_max=3, pre_avg=5, post_avg=5, delta=0.2, wait=5))
    except:
        return 0

def classify_hierarchical(path):
    """3-Stage Hierarchical Inference Engine."""
    fname = os.path.basename(path)
    dur = dur_of(path)
    ons = onset_count(path)
    dr = decay_ratio(path)
    
    # 1. Filename token evidence
    fn_class, fn_tok = nd.detect(fname)
    
    # 2. Extract 33-D acoustic features
    feat = ddf.extract(path)
    if feat is None:
        return {"category": "Other", "subcategory": "Unclassified", "confidence": 0.0}
    
    # Feature signals: f0, pitch salience, HPSS harmonic ratio, ZCR
    f0 = feat[0]
    salience = feat[1]
    hpss_ratio = feat[2] if len(feat) > 2 else 0.5
    zcr = feat[3] if len(feat) > 3 else 0.1
    
    # Stage 1: Coarse Category Resolution
    if fn_class and fn_class in COARSE_CATEGORY_MAP:
        category = COARSE_CATEGORY_MAP[fn_class]
    elif hpss_ratio > 0.70:
        category = "Instruments" if salience > 0.4 else "Bass"
    elif zcr > 0.40:
        category = "Drums"
    else:
        category = "Drums"
        
    # Stage 2: Temporal Type (Loop vs One-Shot)
    is_loop = (dur >= 2.0) and (ons >= 6) and (dr >= 0.30)
    
    # Stage 3: Fine Subcategory Resolution
    if fn_class and fn_class != "Loop":
        subcategory = fn_class
    elif category == "Instruments":
        if hpss_ratio >= 0.75 and dr >= 0.75:
            subcategory = "Pad Loop" if is_loop else "Pad"
        elif dr <= 0.35 and salience >= 0.5:
            subcategory = "Pluck Loop" if is_loop else "Pluck"
        elif is_loop:
            subcategory = "Synth Loop" if salience < 0.6 else "Chord Loop"
        else:
            subcategory = "Synth"
    elif category == "Drums":
        if zcr >= 0.45:
            subcategory = "Hi-Hat Loop" if is_loop else "Hi-Hat"
        elif hpss_ratio <= 0.20:
            subcategory = "Clap" if dur < 0.8 else "Crash"
        elif is_loop:
            subcategory = "Drum Loop"
        else:
            subcategory = "Kick" if f0 < 0.2 else "Snare"
    else:
        subcategory = fn_class or "Other/none"

    return {
        "category": category,
        "subcategory": subcategory,
        "is_loop": is_loop,
        "duration": round(dur, 2),
        "hpss_ratio": round(float(hpss_ratio), 3),
        "confidence": 0.85 if fn_tok else 0.65
    }

if __name__ == "__main__":
    expanded_csv = os.path.join(SCRIPT_DIR, "verified_drums_expanded.csv")
    if not os.path.exists(expanded_csv):
        print(f"Error: {expanded_csv} not found.")
        sys.exit(1)
        
    rows = [r for r in csv.DictReader(open(expanded_csv)) if r['label'] not in ('__skip__', 'Misc/Review')]
    print(f"Loaded {len(rows)} verified ground-truth rows.")
    
    correct_cat = 0
    correct_sub = 0
    
    for r in rows:
        path = r['path']
        label = r['label']
        res = classify_hierarchical(path)
        
        expected_cat = COARSE_CATEGORY_MAP.get(label, "Other")
        if res['category'] == expected_cat:
            correct_cat += 1
        if res['subcategory'] == label:
            correct_sub += 1

    print(f"\nHierarchical Cascade Performance on Ground-Truth Set:")
    print(f"  Stage 1 (Coarse Category) Accuracy: {100 * correct_cat / len(rows):.1f}%")
    print(f"  Stage 3 (Fine Subcategory) Precision: {100 * correct_sub / len(rows):.1f}%")

