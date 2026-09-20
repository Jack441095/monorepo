"""Experiment registry and result helpers."""
import json
import os
import datetime
import hashlib
import numpy as np

LAB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def code_sha():
    try:
        import subprocess
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=LAB_ROOT)
        return out.stdout.strip() or "uncommitted"
    except Exception:
        return "unknown"


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def save_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(str(type(o)))

    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=default)
    return path


def load_json(path):
    with open(path) as f:
        return json.load(f)


def fixture_id(seed, sr, dur_s, kind, extra=""):
    raw = f"{kind}|{seed}|{sr}|{dur_s}|{extra}"
    return kind + "_" + hashlib.sha1(raw.encode()).hexdigest()[:10]


def register_experiment(registry_path, entry):
    reg = load_json(registry_path) if os.path.exists(registry_path) else {"registry_version": "AERL_REGISTRY_1.0", "experiments": []}
    reg["experiments"] = [e for e in reg["experiments"] if e.get("experiment_id") != entry.get("experiment_id")]
    entry.setdefault("date", now_iso())
    entry.setdefault("code_version", code_sha())
    reg["experiments"].append(entry)
    save_json(registry_path, reg)
    return reg


def pct(v, q):
    return float(np.percentile(np.asarray(v), q))


def stats(values):
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {"n": 0}
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    se = sd / np.sqrt(len(a)) if len(a) > 1 else 0.0
    ci95 = 1.96 * se
    return {
        "n": int(len(a)),
        "mean": mean,
        "median": float(np.median(a)),
        "std": sd,
        "p05": pct(a, 5),
        "p50": pct(a, 50),
        "p95": pct(a, 95),
        "ci95_lo": mean - ci95,
        "ci95_hi": mean + ci95,
    }
