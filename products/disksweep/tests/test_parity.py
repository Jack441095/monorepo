"""Parity fuzz: 5000 seeded adversarial paths, C++ IsBlocked == Python is_blocked."""

import os
import random
import shutil
import subprocess

import pytest

from sidecar import classifier as C

SEED = 20260917
N = 5000

BASES = [
    "/System",
    "/System/Library",
    "/bin",
    "/sbin",
    "/usr",
    "/usr/bin",
    "/usr/local",
    "/usr/local/var/cache",
    "/usr/local/Caches",
    "/usr/localx",
    "/Systemx",
    "/system",
    "/SYSTEM",
    "/private/var/vm",
    "/System/Volumes/Data/private/var/vm",
    "/Users/a/Library/Caches",
    "/Users/a/.cache/huggingface",
    "/Volumes/B/Backups.backupdb",
    "/Library/Extensions",
    "/",
    "",
]

TAILS = [
    "",
    "/",
    "//",
    "x",
    "x/",
    "../System",
    "../../System/Library",
    "./x",
    "a/../b",
    "..",
    "../..",
    ".kext",
    ".kext/Contents",
    "lib.kext.bak",
    "Backups.backupdb",
    "sleepimage",
    "Caches",
    "unicode-\u00e9-x",
    " space ",
    ".",
]

JOINS = ["/", "//", "/./", "/../"]


def gen_paths():
    rng = random.Random(SEED)
    out = []
    for _ in range(N):
        b = rng.choice(BASES)
        parts = [b] + [rng.choice(TAILS) for _ in range(rng.randint(0, 3))]
        p = parts[0]
        for t in parts[1:]:
            p = p + rng.choice(JOINS) + t
        out.append(p)
    return out


def build_parity_bin(tmp):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "scanner", "parity.cpp")
    exe = os.path.join(tmp, "parity")
    cxx = shutil.which("clang++") or shutil.which("g++") or "clang++"
    r = subprocess.run(
        [cxx, "-std=c++17", src, "-o", exe], capture_output=True, text=True
    )
    if r.returncode != 0:
        pytest.skip(f"no working C++ compiler: {r.stderr[:200]}")
    return exe


def test_parity_5k(tmp_path):
    exe = build_parity_bin(str(tmp_path))
    paths = gen_paths()
    assert len(paths) == N
    r = subprocess.run(
        [exe], input="\n".join(paths), capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert len(lines) == N
    mismatches = []
    for p, got in zip(paths, lines):
        want = "1" if C.is_blocked(p) else "0"
        if got != want:
            mismatches.append((p, want, got))
            if len(mismatches) >= 10:
                break
    assert not mismatches, f"parity mismatches (first 10): {mismatches}"
