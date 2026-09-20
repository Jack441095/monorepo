"""NON-PROTECTED smoke fixtures for harness validation.

Synthesized stand-ins for production relationships. These are NOT real
audio and carry zero qualification value — they exist solely to prove the
validation harness end-to-end before licensed material arrives.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import signal as sps


def _write(path: Path, x: np.ndarray, fs: int):
    from eval.audio_io import write_wav
    write_wav(path, x / (np.max(np.abs(x)) + 1e-12), fs)


def generate_all(out_dir: Path, fs: int = 48000) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260823)
    files = []

    # ---- drum loop: kick/snare/hats pattern --------------------------
    n = 6 * fs
    t = np.arange(n) / fs
    loop = np.zeros(n)

    def kick(t0, f_sweep=(70, 42)):
        seg = np.zeros(n)
        i = int(t0 * fs)
        dur = int(0.35 * fs)
        tt = np.arange(dur) / fs
        sw = f_sweep[0] + (f_sweep[1] - f_sweep[0]) * np.exp(-tt / 0.03)
        ph = 2 * np.pi * np.cumsum(sw) / fs
        seg[i:i + dur] += np.sin(ph) * np.exp(-tt / 0.09)
        cn = int(0.004 * fs)
        ce = np.exp(-np.arange(cn) / (cn / 4))
        seg[i:i + cn] += 0.5 * rng.standard_normal(cn) * ce
        return seg

    def snare_hit(t0):
        seg = np.zeros(n)
        i = int(t0 * fs)
        dur = int(0.25 * fs)
        tt = np.arange(dur) / fs
        seg[i:i + dur] += np.sin(2 * np.pi * 195 * tt) * \
            np.exp(-tt / 0.07) * 0.7
        noise = sps.sosfilt(sps.butter(2, 1500, btype="high", fs=fs,
                                       output="sos"),
                            rng.standard_normal(dur))
        seg[i:i + dur] += noise * np.exp(-tt / 0.09) * 0.5
        return seg

    for beat in range(12):
        t0 = beat * 0.5
        if beat % 4 in (0, 2):
            loop += kick(t0)
            # split stems: body-only and click-only variants rendered below
        if beat % 4 == 1:
            loop += snare_hit(t0)
        if beat % 2 == 1:      # hats
            i = int((t0 + 0.25) * fs)
            hn = int(0.05 * fs)
            hh = sps.sosfilt(sps.butter(2, 8000, btype="high", fs=fs,
                                        output="sos"),
                             rng.standard_normal(hn))
            loop[i:i + hn] += hh * np.exp(-np.arange(hn) / (hn / 3)) * 0.15
    _write(out_dir / "smoke_drumloop_full.wav", loop, fs); files.append("smoke_drumloop_full.wav")

    # kick body stem + click stem (natural pair candidate)
    kick_body = kick(0.0)[:int(0.5 * fs)]
    kn = int(0.5 * fs)
    click = np.zeros(kn)
    cn = int(0.004 * fs)
    ce = np.exp(-np.arange(cn) / (cn / 4))
    click[:cn] = rng.standard_normal(cn) * ce
    click = sps.sosfilt(sps.butter(2, 3000, fs=fs, output="sos"), click)
    _write(out_dir / "smoke_kick_body.wav", kick_body, fs); files.append("smoke_kick_body.wav")
    _write(out_dir / "smoke_kick_click.wav", click, fs); files.append("smoke_kick_click.wav")

    # sub kick (deeper tuning) for reinforcing pair
    sub = kick(0.0, f_sweep=(52, 36))[:kn]
    _write(out_dir / "smoke_kick_sub.wav", sub, fs); files.append("smoke_kick_sub.wav")

    # ---- bass line ----------------------------------------------------
    bass = np.zeros(n)
    notes = [55.0, 55.0, 73.4, 65.4]
    for i_bar in range(6):
        f0 = notes[i_bar % len(notes)]
        i = int(i_bar * 1.0 * fs)
        dur = int(0.9 * fs)
        tt = np.arange(dur) / fs
        env = np.exp(-tt / 0.5) * np.minimum(tt / 0.004, 1)
        bass[i:i + dur] += (np.sin(2 * np.pi * f0 * tt) +
                            0.4 * np.sin(4 * np.pi * f0 * tt)) * env
    _write(out_dir / "smoke_bass_line.wav", bass, fs); files.append("smoke_bass_line.wav")
    bass_sub = np.sin(2 * np.pi * 41.2 * t) * 0.5
    _write(out_dir / "smoke_bass_sub.wav", bass_sub, fs); files.append("smoke_bass_sub.wav")
    bass_dist = np.tanh(6 * bass)
    _write(out_dir / "smoke_bass_distorted.wav", bass_dist, fs); files.append("smoke_bass_distorted.wav")

    # ---- synth pad + octave layer -------------------------------------
    pad_f = 220.0
    pad = (np.sin(2 * np.pi * pad_f * t) +
           0.6 * np.sin(2 * np.pi * pad_f * 1.005 * t) +
           0.3 * np.sin(2 * np.pi * pad_f * 2 * t)) * 0.4 * \
        np.minimum(t / 0.5, 1)
    _write(out_dir / "smoke_pad.wav", pad, fs); files.append("smoke_pad.wav")
    pad_oct = np.sin(2 * np.pi * pad_f * 2 * t) * 0.35
    _write(out_dir / "smoke_pad_octave.wav", pad_oct, fs); files.append("smoke_pad_octave.wav")
    pad_detuned = np.sin(2 * np.pi * pad_f * 0.997 * t +
                         rng.uniform(0, 6.28)) * 0.4   # chorus-like double
    _write(out_dir / "smoke_pad_double_chorus.wav", pad_detuned, fs)
    files.append("smoke_pad_double_chorus.wav")

    # ---- vocal-like formant tone (doubles) -----------------------------
    f_v = 180.0
    def vox(f, vib_phase):
        vib = 1 + 0.01 * np.sin(2 * np.pi * 5.2 * t + vib_phase)
        ph = 2 * np.pi * f * np.cumsum(vib) / fs
        x = np.sign(np.sin(ph)) * 0.3 + np.sin(ph) * 0.7
        sos = sps.butter(2, [300, 3400], btype="band", fs=fs, output="sos")
        return sps.sosfilt(sos, x) * 0.5 * np.minimum(t / 0.3, 1)
    _write(out_dir / "smoke_vox_double_a.wav",
           vox(f_v, 0.0), fs); files.append("smoke_vox_double_a.wav")
    _write(out_dir / "smoke_vox_double_b.wav",
           vox(f_v, 2.1), fs); files.append("smoke_vox_double_b.wav")

    # ---- tonal ringing trap --------------------------------------------
    ring = np.sin(2 * np.pi * 210 * t) * np.exp(-t / 0.8)
    _write(out_dir / "smoke_tonal_ring.wav", ring, fs); files.append("smoke_tonal_ring.wav")

    return [out_dir / f for f in files]
