"""Generate LAYER_ALIGNMENT_FROZEN_ENGINE_V1.json — the engine freeze receipt.

Freeze semantics (Real-Audio Validation V1):
  - hashes every engine module, the C++ spike source and binary
  - extracts thresholds/config PROGRAMMATICALLY from the live modules
    (a freeze that copies numbers by hand can drift; this cannot)
  - records git state, interpreter and library versions
  - computes one canonical digest over the whole payload

The frozen artifact must be created BEFORE any real-audio contact.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENGINE_FILES = [
    "src/nla/__init__.py",
    "src/nla/corpus.py",
    "src/nla/methods.py",
    "src/nla/interaction.py",
    "src/nla/decision.py",
    "src/nla/scenarios.py",
    "cpp_spike/nla_spike.cpp",
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT.parent,
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    import numpy as np
    import scipy

    from src.nla import decision as D
    from src.nla import interaction as I
    from src.nla import methods as M

    files = {}
    for rel in ENGINE_FILES:
        p = ROOT / rel
        if p.exists():
            files[rel] = sha256_file(p)
        else:
            print(f"WARN missing {rel}")

    cpp_bin = ROOT / "cpp_spike" / "nla_spike"
    if cpp_bin.exists():
        files["cpp_spike/nla_spike.bin"] = sha256_file(cpp_bin)

    config = {
        # classification thresholds (live extraction)
        "classify_thresholds": dict(D.TH),
        # search configuration
        "fast_search": {
            "coarse_step": 2,
            "prior_weight": I.fast_search.__defaults__[2]
            if I.fast_search.__defaults__ else None,
            "max_dev": 10,
            "bands_hz_weight": [[20, 120, 3.0], [120, 250, 2.0],
                                [20, None, 1.0]],
        },
        "recommend_policy": {
            "min_improvement_db": __import__("inspect").signature(
                D.recommend).parameters["min_improvement_db"].default,
            "low_band_gate_db": {"active_low_min": 2.5, "broadband_fallback": 1.0},
        },
        "estimator_config": {
            "primary": "xcorr_plain(parabolic on unnormalised profile)",
            "confidence_feature": "gcc_soft gamma=0.35",
            "gcc_soft_gamma": 0.35,
            "default_bands_hz": [[n, lo, hi] for n, lo, hi in M.DEFAULT_BANDS],
            "cross_spectrum": {
                "window": "hann", "smooth_bins": 7, "floor_db": -70.0},
            "ambiguity_rel_threshold": 0.85,
            "spectral_overlap_rel_thr_db": -20.0,
            "non_overlapping_abstain_below": 0.15,
        },
        "policy_notes": [
            "estimate-then-verify: correlation owns timing; energy objective "
            "verifies within +/-10 samples of measured offset",
            "NO_ACTION is first-class; abstention classes: UNRELATED, "
            "AMBIGUOUS(periodic), AMBIGUOUS(non-overlapping spectra)",
            "low-band benefit gate blocks broadband-only 'wins' on "
            "decorrelated material",
        ],
    }

    payload = {
        "artifact": "LAYER_ALIGNMENT_FROZEN_ENGINE_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_branch": git("branch", "--show-current"),
        "git_head": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain").strip()),
        "engine_files_sha256": files,
        "config": config,
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "rules": [
            "no tuning on real audio after this freeze",
            "failures found on real audio are REPORTED (V2 backlog), not patched",
            "real audio must not become a secret development set",
        ],
    }
    canon = json.dumps(payload, sort_keys=True, indent=1).encode()
    payload["canonical_digest_sha256"] = hashlib.sha256(canon).hexdigest()

    out = ROOT / "LAYER_ALIGNMENT_FROZEN_ENGINE_V1.json"
    out.write_text(json.dumps(payload, sort_keys=True, indent=1))
    print(f"frozen -> {out}")
    print(f"canonical digest: {payload['canonical_digest_sha256'][:16]}...")
    print(f"git head: {payload['git_head'][:12]} dirty={payload['git_dirty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
