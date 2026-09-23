#!/usr/bin/env python3
"""Render the original, rights-clear KENN investor-demo music fixture.

The result is a deterministic 16-bar electronic production, not a test-tone
fixture. Eight stems match the checked-in Ableton topology, and two evidence
renders provide the full mix and isolated vocal scope used by conversational
analysis. WAV outputs remain local/ignored; the manifest records exact hashes,
provenance, musical structure, and deliberate analysis cues.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import wave
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "kenn.investor_demo_audio.v1"
TEMPO_BPM = 120.0
TRACKS = (
    ("Kick", "01_Kick.wav"),
    ("Snare / Clap", "02_Snare_Clap.wav"),
    ("Hi-Hats", "03_Hi-Hats.wav"),
    ("Drum Bus", "04_Drum_Bus_Texture.wav"),
    ("Bass", "05_Bass.wav"),
    ("Synth", "06_Synth.wav"),
    ("Lead Vocal", "07_Lead_Vocal_Texture.wav"),
    ("FX Print", "08_FX_Print.wav"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _midi(note: float) -> float:
    return 440.0 * (2.0 ** ((note - 69.0) / 12.0))


def _stereo(mono: np.ndarray, pan: float = 0.0) -> np.ndarray:
    angle = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
    return np.column_stack((mono * math.cos(angle), mono * math.sin(angle)))


def _add(target: np.ndarray, source: np.ndarray, start_seconds: float, sample_rate: int) -> None:
    start = max(0, int(round(start_seconds * sample_rate)))
    if start >= len(target):
        return
    end = min(len(target), start + len(source))
    target[start:end] += source[: end - start]


def _decay_envelope(length: int, sample_rate: int, decay: float, attack: float = 0.003) -> np.ndarray:
    t = np.arange(length, dtype=np.float64) / sample_rate
    return np.minimum(1.0, t / max(attack, 1.0 / sample_rate)) * np.exp(-t / decay)


def _kick(sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    length = int(0.42 * sample_rate)
    t = np.arange(length, dtype=np.float64) / sample_rate
    frequency = 43.0 + 92.0 * np.exp(-t / 0.025)
    phase = 2.0 * np.pi * np.cumsum(frequency) / sample_rate
    body = np.sin(phase) * np.exp(-t / 0.15)
    click = rng.standard_normal(length) * np.exp(-t / 0.004)
    click = np.concatenate(([0.0], np.diff(click)))
    return np.tanh((body + 0.10 * click) * 1.6) * 0.86


def _snare(sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    length = int(0.34 * sample_rate)
    t = np.arange(length, dtype=np.float64) / sample_rate
    noise = rng.standard_normal(length)
    high = np.concatenate(([0.0], np.diff(noise)))
    tone = np.sin(2.0 * np.pi * 188.0 * t) + 0.35 * np.sin(2.0 * np.pi * 376.0 * t)
    return np.tanh((0.48 * high * np.exp(-t / 0.075) + 0.4 * tone * np.exp(-t / 0.11)) * 1.2) * 0.55


def _hat(sample_rate: int, rng: np.random.Generator, *, open_hat: bool) -> np.ndarray:
    duration = 0.26 if open_hat else 0.075
    length = int(duration * sample_rate)
    t = np.arange(length, dtype=np.float64) / sample_rate
    noise = rng.standard_normal(length)
    high = np.concatenate(([0.0, 0.0], np.diff(noise, n=2)))
    return np.tanh(high * 0.8) * np.exp(-t / (0.12 if open_hat else 0.025)) * 0.16


def _bass_note(note: int, duration: float, sample_rate: int) -> np.ndarray:
    length = max(1, int(duration * sample_rate))
    t = np.arange(length, dtype=np.float64) / sample_rate
    f = _midi(note)
    phase = (f * t) % 1.0
    saw = 2.0 * phase - 1.0
    sub = np.sin(2.0 * np.pi * (f * 0.5) * t)
    envelope = _decay_envelope(length, sample_rate, decay=max(0.18, duration * 0.7), attack=0.008)
    return np.tanh((0.62 * saw + 0.8 * sub) * envelope * 1.3) * 0.50


def _pluck(note: int, duration: float, sample_rate: int) -> np.ndarray:
    length = max(1, int(duration * sample_rate))
    t = np.arange(length, dtype=np.float64) / sample_rate
    f = _midi(note)
    harmonics = sum(
        (1.0 / harmonic) * np.sin(2.0 * np.pi * f * harmonic * t)
        for harmonic in range(1, 7)
    )
    envelope = _decay_envelope(length, sample_rate, decay=0.22, attack=0.004)
    return np.tanh(harmonics * envelope * 0.9) * 0.27


def _vowel_note(note: int, duration: float, sample_rate: int, phase_offset: float) -> np.ndarray:
    length = max(1, int(duration * sample_rate))
    t = np.arange(length, dtype=np.float64) / sample_rate
    f0 = _midi(note)
    vibrato = 1.0 + 0.004 * np.sin(2.0 * np.pi * 5.1 * t + phase_offset)
    phase = 2.0 * np.pi * f0 * np.cumsum(vibrato) / sample_rate
    formants = (720.0, 1220.0, 2600.0)
    voice = np.zeros(length, dtype=np.float64)
    for harmonic in range(1, 24):
        hz = harmonic * f0
        weight = sum(math.exp(-0.5 * ((hz - center) / (130.0 + center * 0.06)) ** 2) for center in formants)
        voice += (0.14 + weight) * np.sin(harmonic * phase) / harmonic
    attack = np.minimum(1.0, t / 0.06)
    release = np.minimum(1.0, np.maximum(0.0, (duration - t) / 0.18))
    return np.tanh(voice * 1.4) * attack * release * 0.34


def _echo(stereo: np.ndarray, sample_rate: int, delay_seconds: float, feedback: float) -> np.ndarray:
    result = stereo.copy()
    delay = max(1, int(delay_seconds * sample_rate))
    for repeat in range(1, 4):
        offset = delay * repeat
        if offset >= len(result):
            break
        gain = feedback ** repeat
        result[offset:, 0] += stereo[:-offset, 1] * gain
        result[offset:, 1] += stereo[:-offset, 0] * gain
    return result


def _write_pcm16(path: Path, stereo: np.ndarray, sample_rate: int) -> None:
    bounded = np.clip(stereo, -0.999, 0.999)
    pcm = np.round(bounded * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _render_stems(*, sample_rate: int, bars: int, seed: int) -> dict[str, np.ndarray]:
    if sample_rate < 8000:
        raise ValueError("sample_rate must be at least 8000 Hz")
    if bars < 2:
        raise ValueError("bars must be at least 2")
    rng = np.random.default_rng(seed)
    beat = 60.0 / TEMPO_BPM
    duration = bars * 4.0 * beat
    frames = int(round(duration * sample_rate))
    stems = {name: np.zeros((frames, 2), dtype=np.float64) for name, _ in TRACKS}

    kick_hit = _kick(sample_rate, rng)
    snare_hit = _snare(sample_rate, rng)
    closed_hat = _hat(sample_rate, rng, open_hat=False)
    open_hat = _hat(sample_rate, rng, open_hat=True)
    for bar in range(bars):
        bar_start = bar * 4.0 * beat
        energy = 0.52 if bar < 2 else (0.36 if bars >= 12 and 8 <= bar < 10 else 1.0)
        kick_steps = (0.0, 2.0) if bar < 2 else (0.0, 1.5, 2.0, 3.25)
        for position in kick_steps:
            _add(stems["Kick"], _stereo(kick_hit * energy), bar_start + position * beat, sample_rate)
        if bar >= 1:
            for position in (1.0, 3.0):
                _add(stems["Snare / Clap"], _stereo(snare_hit * energy), bar_start + position * beat, sample_rate)
        for eighth in range(8):
            swing = 0.035 if eighth % 2 else 0.0
            velocity = 0.72 if eighth % 2 else 1.0
            hit = open_hat if eighth == 7 and bar >= 2 else closed_hat
            _add(stems["Hi-Hats"], _stereo(hit * velocity * energy, pan=(-0.32 if eighth % 2 else 0.28)), bar_start + eighth * beat / 2 + swing, sample_rate)

        # Parallel room/percussion texture on the track labelled Drum Bus.
        for position, note in ((0.75, 45), (2.75, 48)):
            tom = _bass_note(note, 0.22, sample_rate) * 0.30 * energy
            _add(stems["Drum Bus"], _stereo(tom, pan=-0.2 if position < 1 else 0.2), bar_start + position * beat, sample_rate)

    progression = ((38, 45, 50), (34, 41, 46), (41, 48, 53), (36, 43, 48))  # Dm, Bb, F, C
    bass_patterns = ((38, 38, 45, 38), (34, 34, 41, 34), (41, 41, 48, 41), (36, 36, 43, 36))
    for bar in range(bars):
        bar_start = bar * 4.0 * beat
        chord = progression[bar % len(progression)]
        if bar >= 1 and not (bars >= 12 and bar == 8):
            for quarter, note in enumerate(bass_patterns[bar % 4]):
                note_audio = _bass_note(note, beat * 0.86, sample_rate)
                _add(stems["Bass"], _stereo(note_audio), bar_start + quarter * beat, sample_rate)
        if bar >= 2:
            arp = (chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12, chord[0] + 24, chord[1] + 12, chord[2] + 12, chord[1] + 12)
            for eighth, note in enumerate(arp):
                sound = _pluck(note, beat * 0.65, sample_rate)
                pan = -0.42 if eighth % 2 == 0 else 0.42
                _add(stems["Synth"], _stereo(sound, pan=pan), bar_start + eighth * beat / 2, sample_rate)

        # A quiet harmonic pad lives in the FX print and opens across sections.
        pad_length = int(4.0 * beat * sample_rate)
        t = np.arange(pad_length, dtype=np.float64) / sample_rate
        pad = sum(np.sin(2.0 * np.pi * _midi(note) * t) for note in chord) / 3.0
        pad *= np.sin(np.linspace(0.0, math.pi, pad_length)) ** 0.7
        left = pad
        right = np.roll(pad, int(0.011 * sample_rate))
        _add(stems["FX Print"], np.column_stack((left, right)) * 0.11, bar_start, sample_rate)

    # Original wordless lead motif, introduced halfway and repeated with a lift.
    phrase = ((62, 0.0, 1.35), (65, 1.5, 0.42), (67, 2.0, 0.86), (69, 3.0, 0.82))
    phrase_starts = [4]
    if bars >= 12:
        phrase_starts.extend((10, 12, 14))
    for phrase_index, start_bar in enumerate(phrase_starts):
        if start_bar >= bars:
            continue
        for note, beat_offset, length_beats in phrase:
            lifted = note + (12 if phrase_index == len(phrase_starts) - 1 else 0)
            sound = _vowel_note(lifted, length_beats * beat, sample_rate, phase_offset=phrase_index * 0.7)
            stereo = _stereo(sound, pan=(-0.08 if phrase_index % 2 else 0.08))
            _add(stems["Lead Vocal"], stereo, (start_bar * 4.0 + beat_offset) * beat, sample_rate)
    stems["Lead Vocal"] = _echo(stems["Lead Vocal"], sample_rate, delay_seconds=0.25, feedback=0.22)

    # Deliberate, documented vocal near-clipping passage for the scoped demo check.
    if bars >= 12:
        start = int(12.0 * 4.0 * beat * sample_rate)
        end = min(frames, start + int(1.5 * beat * sample_rate))
        stems["Lead Vocal"][start:end] = np.clip(stems["Lead Vocal"][start:end] * 4.5, -0.995, 0.995)

    # Riser and impact provide an audible section boundary without external samples.
    if bars >= 8:
        riser_duration = min(4.0 * beat, duration)
        length = int(riser_duration * sample_rate)
        t = np.arange(length, dtype=np.float64) / sample_rate
        noise = rng.standard_normal(length)
        brightness = np.linspace(0.05, 0.5, length)
        riser = np.tanh(np.concatenate(([0.0], np.diff(noise))) * brightness) * np.linspace(0.0, 0.24, length)
        start_seconds = max(0.0, (min(bars, 10) * 4.0 * beat) - riser_duration)
        _add(stems["FX Print"], _stereo(riser), start_seconds, sample_rate)

    return stems


def render_demo_audio(
    out_dir: Path, *, sample_rate: int = 48000, bars: int = 16, seed: int = 20260923,
) -> dict[str, Any]:
    """Render stems, evidence files, and a fail-closed provenance manifest."""
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stems = _render_stems(sample_rate=sample_rate, bars=bars, seed=seed)
    files: list[dict[str, Any]] = []
    for track_name, filename in TRACKS:
        path = out_dir / filename
        _write_pcm16(path, stems[track_name], sample_rate)
        files.append({
            "role": "ableton_stem",
            "track_name": track_name,
            "path": filename,
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            "license": "generated-internal",
        })

    weights = {
        "Kick": 0.88,
        "Snare / Clap": 0.52,
        "Hi-Hats": 0.72,
        "Drum Bus": 0.42,
        "Bass": 0.92,
        "Synth": 0.66,
        "Lead Vocal": 0.72,
        "FX Print": 0.56,
    }
    mix = sum(stems[name] * weights[name] for name, _ in TRACKS)
    # Preserve musical dynamics while intentionally allowing a few near-full-scale
    # runs. The analyzer reports sample peaks, not true-peak or mastered loudness.
    mix = np.tanh(mix * 1.18)
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix * (0.992 / peak)
    mix_path = out_dir / "KENN_Demo_Mix_Analysis.wav"
    vocal_path = out_dir / "KENN_Demo_Lead_Vocal_Analysis.wav"
    _write_pcm16(mix_path, mix, sample_rate)
    _write_pcm16(vocal_path, stems["Lead Vocal"], sample_rate)
    for role, path, track_name in (
        ("analysis_mix", mix_path, None),
        ("analysis_vocal", vocal_path, "Lead Vocal"),
    ):
        files.append({
            "role": role,
            "track_name": track_name,
            "path": path.name,
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            "license": "generated-internal",
        })

    script_path = Path(__file__).resolve()
    manifest = {
        "schema": SCHEMA,
        "title": "Neon Proof — original KENN investor-demo composition",
        "origin": "Deterministically synthesized by this repository-owned generator; no samples, model weights, external recordings, or third-party musical material are used.",
        "rights": {
            "status": "rights-cleared",
            "license_label": "generated-internal",
            "copyright_risk": "No external audio or composition source.",
            "commercial_demo_allowed": True,
        },
        "render": {
            "sample_rate_hz": sample_rate,
            "bit_depth": 16,
            "channels": 2,
            "tempo_bpm": TEMPO_BPM,
            "bars": bars,
            "duration_seconds": bars * 4.0 * 60.0 / TEMPO_BPM,
            "seed": seed,
            "generator": script_path.name,
            "generator_sha256": _sha256(script_path),
        },
        "musical_structure": "D-minor electronic production with intro, groove, breakdown, lift, original wordless lead motif, and section-transition FX.",
        "deliberate_analysis_cues": [
            "Kick and bass are intentionally forward for a reproducible low-end-heavy balance check.",
            "The isolated lead-vocal texture contains a documented near-full-scale passage beginning at bar 13.",
            "Wide delayed synth/pad material supports a mono-compatibility listening check; KENN must report only what its measurements support.",
        ],
        "files": files,
        "ableton_track_order": [name for name, _ in TRACKS],
        "analysis_environment": {
            "KENN_LIVE_AUDIO_CAPTURE_PATH": str(mix_path),
            "KENN_LIVE_VOCAL_CAPTURE_PATH": str(vocal_path),
        },
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--bars", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260923)
    args = parser.parse_args()
    manifest = render_demo_audio(
        args.out_dir,
        sample_rate=args.sample_rate,
        bars=args.bars,
        seed=args.seed,
    )
    print(json.dumps({
        "status": "rendered",
        "out_dir": str(args.out_dir.expanduser().resolve()),
        "files": len(manifest["files"]),
        "duration_seconds": manifest["render"]["duration_seconds"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
