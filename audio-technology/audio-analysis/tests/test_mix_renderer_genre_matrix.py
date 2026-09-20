"""Stage 7 exit-criteria test matrix: 10 synthetic genre/loudness profiles.

Stage 7 (``studio/audio_analysis/audio_analysis/mixdown/mix_renderer.py`` — true
peak limiting, LUFS normalization, 3-band MBC, M/S, atomic output, noise-shaped
dither) is functionally complete and previously verified against only 3 of the
10 genre/loudness profiles the original spec called for (see
``docs/JARVIS_MASTER_EXECUTION_PLAN.md``, Stage 7 "Tests" note: "3 synthetic
mixes (not the full 10-genre matrix)"). This file fills in the remaining
profiles.

For each of the 10 cases below we build real ``StemProfile`` inputs and run
them through the actual ``generate_mix_plan()`` rule engine for the closest
matching base genre (so per-stem EQ/compression/reverb choices come from the
real rule tables in ``mix_rules.py``, not hand-faked), then relabel
``MixPlan.genre`` and override ``target_lufs`` / ``bus.limiter_ceiling_db`` to
the loudness and dynamic-range profile appropriate for that musical style.
``mix_rules.GENRE_MODIFIERS`` only has 8 entries (hip_hop, rock, pop, edm,
acoustic, jazz, cinematic, podcast) — there is no dedicated "classical" or
"metal" entry, so those two reuse the closest sibling's stem rules (jazz for
classical's natural/uncompressed dynamics, rock for metal's guitar-driven
density) purely for per-stem processing; what's actually under test here is
the renderer's behaviour (clipping, true-peak ceiling, LUFS convergence,
render speed) across a spread of loudness/dynamic-range targets, not the mix
decision engine's genre selection (which has its own coverage in
``test_mix_decision_engine.py`` / ``test_genre_profiles.py``).

Exit bars asserted per case (from the Stage 7 spec):
  - no sample-peak clipping
  - true peak (4x oversampled) <= ceiling (validator allows its standard
    0.15 dB measurement-noise margin)
  - integrated LUFS within +/-0.1 LU of target
  - render time <= 2x real-time (i.e. render_seconds <= 2 * audio_duration)
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
from audio_analysis.mixdown.mix_validator import verify_render_output
from audio_analysis.mixdown.stem_classifier import StemProfile

SR = 44100
# 30s, not 6s: the edm case's synth_pad stem has a 0.1Hz ("slow_env" in
# _pad()) amplitude envelope -- a 10s period. At 6s the render never
# completes even one full cycle, so the LUFS-reachability measurement only
# ever saw a partial, non-representative slice of the material's true
# dynamic range. Found 2026-07-10 re-rendering at a realistic ~3.5min song
# length: the edm gap nearly doubled (-0.65 -> -1.12 LU) once the pad's full
# envelope was actually exposed, while every other genre (which don't
# combine a slow-envelope stem with a near-ceiling loudness target the way
# edm does) measured identically at both durations. 30s gives 3 full pad
# cycles -- representative without paying for a full-song-length render on
# every test run (render ratios measured at 210s stay well under the 2x
# MAX_RENDER_RATIO gate for every case, so this isn't a speed-gate risk).
DURATION_S = 30.0
N = int(SR * DURATION_S)
_T = np.arange(N) / SR

LUFS_TOLERANCE = 0.1
CEILING_MARGIN_DB = 0.15
MAX_RENDER_RATIO = 2.0


def _peak_dbfs(x: np.ndarray) -> float:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    return 20.0 * np.log10(max(peak, 1e-12))


def _rms_dbfs(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
    return 20.0 * np.log10(max(rms, 1e-12))


def _crest_db(x: np.ndarray) -> float:
    return _peak_dbfs(x) - _rms_dbfs(x)


# --- Synthetic stem generators -------------------------------------------------
# Not intended to sound musical -- just to give each instrument role plausible
# spectral content, transient behaviour, and level so the renderer's gain
# staging / EQ / compression / limiting chain has something realistic to act on.

def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _kick(bpm: float, freq: float, seed: int) -> np.ndarray:
    beat_period = 60.0 / bpm
    phase = np.mod(_T, beat_period)
    env = np.exp(-phase * 16.0)
    pitch_drop = freq * (1.0 + 1.5 * np.exp(-phase * 60.0))  # pitch envelope "thump"
    tone = np.sin(2 * np.pi * np.cumsum(pitch_drop) / SR) * env
    click = _rng(seed).normal(0, 1, N) * np.exp(-phase * 200.0) * 0.15
    return np.clip(tone + click, -1.0, 1.0) * 0.9


def _bass(freq: float, bpm: float) -> np.ndarray:
    beat_period = 60.0 / bpm
    phase = np.mod(_T, beat_period)
    env = 0.6 + 0.4 * np.exp(-phase * 4.0)
    return (0.55 * np.sin(2 * np.pi * freq * _T) + 0.2 * np.sin(2 * np.pi * freq * 2 * _T)) * env


def _vocal(freq: float, seed: int) -> np.ndarray:
    vibrato = 4.0 * np.sin(2 * np.pi * 5.5 * _T)
    inst_freq = freq + vibrato
    phase = 2 * np.pi * np.cumsum(inst_freq) / SR
    sig = np.sin(phase) + 0.35 * np.sin(2 * phase) + 0.15 * np.sin(3 * phase)
    env = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 0.6 * _T + _rng(seed).uniform(0, 1)))
    return sig * env * 0.4


def _lead(freq: float, seed: int) -> np.ndarray:
    saw = 2.0 * (_T * freq - np.floor(0.5 + _T * freq))
    env = 0.6 + 0.4 * np.sin(2 * np.pi * 1.5 * _T) ** 2
    return saw * env * 0.35


def _pad(freq: float, seed: int) -> np.ndarray:
    noise = _rng(seed).normal(0, 1, N)
    tone = np.sin(2 * np.pi * freq * _T) + 0.5 * np.sin(2 * np.pi * freq * 1.5 * _T)
    slow_env = 0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * _T)
    return (0.5 * tone + 0.05 * noise) * slow_env * 0.3


def _hihat(bpm: float, seed: int) -> np.ndarray:
    step = 60.0 / bpm / 2.0
    phase = np.mod(_T, step)
    env = np.exp(-phase * 90.0)
    noise = _rng(seed).normal(0, 1, N)
    return noise * env * 0.18


def _snare(bpm: float, seed: int) -> np.ndarray:
    beat_period = 60.0 / bpm
    phase = np.mod(_T + beat_period / 2.0, beat_period)
    env = np.exp(-phase * 25.0)
    noise = _rng(seed).normal(0, 1, N) * 0.6
    tone = np.sin(2 * np.pi * 180.0 * _T) * 0.4
    return (noise + tone) * env * 0.8


def _guitar(freq: float, bpm: float, seed: int) -> np.ndarray:
    strums = 60.0 / bpm
    phase = np.mod(_T, strums)
    env = np.exp(-phase * 3.0)
    harm = sum(np.sin(2 * np.pi * freq * k * _T) / k for k in (1, 2, 3, 4))
    return harm * env * 0.4


def _keys(freqs: tuple[float, ...], seed: int) -> np.ndarray:
    chord = sum(np.sin(2 * np.pi * f * _T) for f in freqs) / len(freqs)
    env = 0.6 + 0.4 * np.sin(2 * np.pi * 0.3 * _T) ** 2
    return chord * env * 0.35


def _strings(freqs: tuple[float, ...], seed: int) -> np.ndarray:
    chord = sum(np.sin(2 * np.pi * f * _T) for f in freqs) / len(freqs)
    swell = 0.4 + 0.6 * (0.5 - 0.5 * np.cos(2 * np.pi * 0.08 * _T))
    return chord * swell * 0.4


def _spoken(seed: int) -> np.ndarray:
    # Amplitude-modulated formant-ish tone with silence gaps, standing in for speech.
    words = (np.sin(2 * np.pi * 2.2 * _T) > 0.0).astype(np.float64)
    carrier = np.sin(2 * np.pi * 160.0 * _T) + 0.3 * np.sin(2 * np.pi * 480.0 * _T)
    noise = _rng(seed).normal(0, 1, N) * 0.05
    return (carrier + noise) * words * 0.35


def _make_profile(name: str, instrument: str, samples: np.ndarray) -> tuple[dict, StemProfile]:
    stem_dict = {"name": name, "samples": samples, "sample_rate": SR}
    profile = StemProfile(
        name=name,
        instrument=instrument,
        classification_confidence=1.0,
        classification_method="synthetic",
        sample_rate=SR,
        duration_seconds=DURATION_S,
        peak_dbfs=_peak_dbfs(samples),
        rms_dbfs=_rms_dbfs(samples),
        crest_factor_db=_crest_db(samples),
    )
    return stem_dict, profile


# --- The 10 genre/loudness profiles --------------------------------------------

def _case_pop():
    stems = [
        _make_profile("kick", "kick", _kick(120, 55, 1)),
        _make_profile("bass", "bass", _bass(55 * 2, 120)),
        _make_profile("vocal", "vocal", _vocal(260, 2)),
        _make_profile("synth_lead", "synth_lead", _lead(660, 3)),
        _make_profile("hihat", "hihat", _hihat(120, 4)),
    ]
    return "pop", "pop", stems, -9.0, -1.0


def _case_rock():
    stems = [
        _make_profile("kick", "kick", _kick(132, 60, 5)),
        _make_profile("bass", "bass", _bass(82, 132)),
        _make_profile("guitar", "guitar", _guitar(220, 132, 6)),
        _make_profile("vocal", "vocal", _vocal(220, 7)),
        _make_profile("snare", "snare", _snare(132, 8)),
    ]
    return "rock", "rock", stems, -9.5, -1.0


def _case_hip_hop():
    stems = [
        _make_profile("kick", "kick", _kick(90, 45, 9)),
        _make_profile("sub_bass", "sub_bass", _bass(40, 90)),
        _make_profile("vocal", "vocal", _vocal(180, 10)),
        _make_profile("hihat", "hihat", _hihat(90, 11)),
    ]
    return "hip_hop", "hip_hop", stems, -8.0, -1.0


def _case_edm():
    stems = [
        _make_profile("kick", "kick", _kick(128, 50, 12)),
        _make_profile("sub_bass", "sub_bass", _bass(45, 128)),
        _make_profile("synth_lead", "synth_lead", _lead(880, 13)),
        _make_profile("synth_pad", "synth_pad", _pad(330, 14)),
    ]
    return "edm", "edm", stems, -7.0, -0.5


def _case_acoustic_folk():
    stems = [
        _make_profile("guitar", "guitar", _guitar(196, 96, 15)),
        _make_profile("vocal", "vocal", _vocal(210, 16)),
        _make_profile("keys", "keys", _keys((262.0, 330.0, 392.0), 17)),
        _make_profile("kick", "kick", _kick(96, 70, 18)),
    ]
    return "acoustic", "acoustic", stems, -14.0, -1.5


def _case_classical():
    # No dedicated GENRE_MODIFIERS entry; reuse "jazz" rules (low compression,
    # dynamics preserved) for per-stem processing, then relabel + retarget for
    # classical's wide-dynamic-range mastering profile.
    stems = [
        _make_profile("strings", "strings", _strings((196.0, 246.9, 293.7, 392.0), 19)),
        _make_profile("keys", "keys", _keys((220.0, 277.2, 329.6), 20)),
        _make_profile("bass", "bass", _bass(65, 60)),
    ]
    return "jazz", "classical", stems, -18.0, -3.0


def _case_jazz():
    stems = [
        _make_profile("keys", "keys", _keys((233.1, 293.7, 349.2), 21)),
        _make_profile("bass", "bass", _bass(73, 100)),
        _make_profile("vocal", "vocal", _vocal(245, 22)),
        _make_profile("snare", "snare", _snare(100, 23)),
    ]
    return "jazz", "jazz", stems, -15.0, -1.5


def _case_podcast():
    stems = [
        _make_profile("vocal", "vocal", _spoken(24)),
        _make_profile("other", "other", _pad(220, 25) * 0.15),
    ]
    return "podcast", "podcast", stems, -16.0, -1.0


def _case_ambient_cinematic():
    stems = [
        _make_profile("strings", "strings", _strings((174.6, 220.0, 261.6), 26)),
        _make_profile("ambient", "ambient", _pad(110, 27)),
        _make_profile("vocal", "vocal", _vocal(300, 28) * 0.5),
    ]
    return "cinematic", "ambient_cinematic", stems, -18.0, -2.0


def _case_metal():
    # No dedicated GENRE_MODIFIERS entry; reuse "rock" rules for per-stem
    # processing, then relabel + retarget for metal's dense, loud master.
    stems = [
        _make_profile("kick", "kick", _kick(160, 65, 29)),
        _make_profile("bass", "bass", _bass(65, 160)),
        _make_profile("guitar", "guitar", _guitar(110, 160, 30)),
        _make_profile("vocal", "vocal", _vocal(180, 31)),
    ]
    return "rock", "metal", stems, -8.5, -0.5


CASES = {
    "pop": _case_pop,
    "rock": _case_rock,
    "hip_hop": _case_hip_hop,
    "edm": _case_edm,
    "acoustic_folk": _case_acoustic_folk,
    "classical": _case_classical,
    "jazz": _case_jazz,
    "podcast_spoken_word": _case_podcast,
    "ambient_cinematic": _case_ambient_cinematic,
    "metal": _case_metal,
}


def _build_and_render(case_name: str):
    base_genre, label, stem_pairs, target_lufs, ceiling_db = CASES[case_name]()
    stem_dicts = [p[0] for p in stem_pairs]
    profiles = [p[1] for p in stem_pairs]

    plan = generate_mix_plan(profiles, genre=base_genre, target_lufs=target_lufs)
    plan.genre = label
    plan.bus.limiter_ceiling_db = ceiling_db

    start = time.perf_counter()
    result = mix_and_render_stems(stem_dicts, plan)
    render_seconds = time.perf_counter() - start

    validation = verify_render_output(
        result["left"],
        result["right"],
        result["sample_rate"],
        result["mixdown_wav_bytes"],
        target_lufs=target_lufs,
        measured_lufs=result["measured_lufs"],
        lufs_tolerance=LUFS_TOLERANCE,
        ceiling_db=ceiling_db,
        ceiling_margin_db=CEILING_MARGIN_DB,
    )
    return {
        "case": case_name,
        "target_lufs": target_lufs,
        "ceiling_db": ceiling_db,
        "measured_lufs": result["measured_lufs"],
        "render_seconds": render_seconds,
        "render_ratio": render_seconds / DURATION_S,
        "loudness_solver": result["loudness_solver"],
        "validation": validation,
    }


# ~13-27s per case x 10 real renders (~230s total). Marked slow so a fast local
# loop can deselect it via `pytest -m "not slow"`; the full release suite
# (scripts/eval/full_test_suite.py) and `pytest -m slow` still run it.
@pytest.mark.slow
@pytest.mark.parametrize("case_name", list(CASES.keys()))
def test_genre_loudness_profile_matrix(case_name):
    r = _build_and_render(case_name)
    v = r["validation"]
    m = v["metrics"]
    solver = r["loudness_solver"]

    print(
        f"\n[{r['case']}] target={r['target_lufs']:.1f} LUFS ceiling={r['ceiling_db']:.1f} dBTP | "
        f"measured={r['measured_lufs']:.3f} LUFS (Δ{m['lufs_diff']:+.3f} LU) | "
        f"true_peak={m['true_peak_dbtp']:.3f} dBTP | sample_peak={m['sample_peak']:.6f} | "
        f"crest={m['crest_factor_db']:.1f} dB | render={r['render_seconds']:.3f}s "
        f"({r['render_ratio']:.3f}x real-time)"
    )

    # No clipping.
    assert m["sample_peak"] <= 1.0 + 1e-6, f"clipped: sample peak {m['sample_peak']}"

    # True peak under ceiling (validator's standard measurement-noise margin).
    assert m["true_peak_dbtp"] <= r["ceiling_db"] + CEILING_MARGIN_DB, (
        f"true peak {m['true_peak_dbtp']:.3f} dBTP exceeds ceiling {r['ceiling_db']:.2f} "
        f"(+{CEILING_MARGIN_DB} margin)"
    )

    # Integrated LUFS within +/-0.1 LU of target.
    assert abs(m["lufs_diff"]) <= LUFS_TOLERANCE, (
        f"measured {r['measured_lufs']:.3f} LUFS is {m['lufs_diff']:+.3f} LU from "
        f"target {r['target_lufs']:.2f} (tolerance +/-{LUFS_TOLERANCE})"
    )

    assert solver["found_safe_candidate"] is True
    assert solver["selected_gap_lu"] <= LUFS_TOLERANCE
    assert solver["gain_attempts"]
    if case_name == "edm":
        saturation_attempts = [
            attempt for attempt in solver["crest_reduction"]["attempts"]
            if attempt.get("method") == "soft_saturation"
        ]
        assert saturation_attempts
        successful = [
            attempt for attempt in saturation_attempts
            if attempt["reachable_lufs"] >= r["target_lufs"] - 0.05
        ]
        assert successful
        assert successful[0]["drive_db"] in (9.0, 12.0)

    # Render time <= 2x real-time.
    assert r["render_seconds"] <= MAX_RENDER_RATIO * DURATION_S, (
        f"render took {r['render_seconds']:.3f}s for {DURATION_S:.1f}s of audio "
        f"({r['render_ratio']:.2f}x real-time, ceiling {MAX_RENDER_RATIO}x)"
    )
