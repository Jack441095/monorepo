"""Realtime playback prewarm helpers (chord cache + mix/master paths)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def prewarm_chord_cache(
    player: Any,
    *,
    root_note: int,
    tempo_bpm: float,
    velocities: Optional[List[int]] = None,
    durations_sec: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Best-effort chord cache prewarm to avoid mid-run cache miss spikes.

  Pre-renders a bounded palette of common chord shapes across diatonic degrees near ``root_note``.
    """
    out: Dict[str, Any] = {"enabled": True, "attempts": 0, "successes": 0, "skipped": False}
    try:
        engine = getattr(player, "synthesis_engine", None)
    except Exception:
        engine = None
    if engine is None:
        out["skipped"] = True
        return out

    if velocities is None:
        velocities = [72]
    tempo = max(40.0, float(tempo_bpm))
    if durations_sec is None:
        beat_durations = [3.75, 4.0]
        raw_durations = [float(b) * 60.0 / tempo for b in beat_durations]
        durations_sec = []
        for d in raw_durations:
            step = 0.05
            q_d = float(round(max(0.05, d) / step) * step)
            durations_sec.append(q_d)

    try:
        engine.preload_samplers(["chords"])
    except Exception:
        pass

    degree_offsets = (0, 2, 4, 5, 7, 9, 11)
    chord_templates = (
        (0, 4, 7),
        (0, 3, 7),
        (0, 4, 7, 10),
        (0, 4, 7, 11),
        (0, 3, 7, 10),
    )

    def _clamp_midi(n: int) -> int:
        return int(min(108, max(21, int(n))))

    base = _clamp_midi(int(root_note))
    while base < 48:
        base += 12
    while base > 72:
        base -= 12

    for off in degree_offsets:
        for tpl in chord_templates:
            notes = [_clamp_midi(base + int(off) + int(x)) for x in tpl]
            inversions = [notes]
            if len(notes) >= 3:
                inv1 = list(notes[1:]) + [notes[0] + 12]
                inv2 = list(notes[2:]) + [notes[0] + 12, notes[1] + 12]
                inversions.extend([inv1, inv2])
            for chord_notes in inversions[:3]:
                for vel in velocities:
                    for dur in durations_sec:
                        out["attempts"] += 1
                        try:
                            _ = engine.render_chord(list(chord_notes), int(vel), float(dur), channel=1)
                            out["successes"] += 1
                        except Exception:
                            continue

    out["tempo_bpm"] = float(tempo)
    out["root_note"] = int(root_note)
    return out


def prewarm_monophonic_cache(
    player: Any,
    *,
    root_note: int,
    tempo_bpm: float,
    channels: Optional[List[int]] = None,
    velocities: Optional[List[int]] = None,
    durations_beats: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Best-effort mono note cache prewarm for section-change render spikes."""
    out: Dict[str, Any] = {"enabled": True, "attempts": 0, "successes": 0, "skipped": False}
    try:
        engine = getattr(player, "synthesis_engine", None)
    except Exception:
        engine = None
    if engine is None:
        out["skipped"] = True
        return out

    if channels is None:
        channels = [2, 3]
    if velocities is None:
        velocities = [80]
    if durations_beats is None:
        durations_beats = [0.25, 0.5]

    tempo = max(40.0, float(tempo_bpm))
    root = int(root_note)
    scale_offsets = (-12, -7, 0, 2, 4, 7, 12)
    try:
        from sampler.monophonic import quantize_mono_duration_sec
    except Exception:
        def quantize_mono_duration_sec(value):
            return round(float(value), 4)

    def _clamp_midi(n: int) -> int:
        return int(min(108, max(21, int(n))))

    seen = set()
    for ch in channels:
        try:
            sampler_name = engine._channel_to_sampler(int(ch))
        except Exception:
            sampler_name = None
        if not sampler_name:
            continue
        try:
            sampler = engine._get_sampler(str(sampler_name))
        except Exception:
            continue
        for off in scale_offsets:
            midi = _clamp_midi(root + int(off))
            for vel in velocities:
                for dur_beats in durations_beats:
                    dur_sec = quantize_mono_duration_sec(float(dur_beats) * (60.0 / tempo))
                    key = (str(sampler_name), int(midi), int(vel), float(dur_sec))
                    if key in seen:
                        continue
                    seen.add(key)
                    out["attempts"] += 1
                    try:
                        sampler.render_note(int(midi), int(vel), float(dur_sec))
                        out["successes"] += 1
                    except Exception:
                        continue

    out["tempo_bpm"] = float(tempo)
    out["root_note"] = int(root)
    out["channels"] = [int(c) for c in channels]
    return out


def warmup_mix_master(
    player: Any,
    *,
    root_note: int,
    tempo_bpm: float,
    sample_rate: int,
) -> Dict[str, Any]:
    """Render a dummy bar to trigger mix/master allocations and return paths once."""
    out: Dict[str, Any] = {"enabled": True, "ok": True}
    try:
        renderer = getattr(player, "renderer", None)
    except Exception:
        renderer = None
    if renderer is None:
        out["ok"] = False
        out["reason"] = "no renderer"
        return out
    tempo = max(40.0, float(tempo_bpm))
    try:
        audio_cfg = getattr(player.config, "audio", None)
        buffer_size = int(getattr(audio_cfg, "buffer_size", 8192) or 8192)
    except Exception:
        buffer_size = 8192
    bar_sec = 4.0 * 60.0 / tempo
    bar_samples = int(round(bar_sec * sample_rate))
    root = int(root_note)
    chord = [root, root + 4, root + 7]
    events = [
        (0, root - 12, 72, 0.0, 4.0, [root - 12]),
        (1, chord[0], 72, 0.0, 4.0, chord),
        (2, root + 12, 64, 0.25, 0.75, [root + 12]),
    ]
    try:
        _ = renderer.render_bar(events, tempo=float(tempo), bar_samples=int(bar_samples), drone=None)
        mb = getattr(renderer, "master_bus", None)
        if mb is not None and hasattr(mb, "warmup_realtime_path"):
            try:
                mb.warmup_realtime_path(
                    n_samples=int(buffer_size),
                    reverb_processor=getattr(renderer, "reverb_processor", None),
                    reverb_quality_tier="safe",
                )
            except Exception:
                pass
    except Exception as exc:
        out["ok"] = False
        out["reason"] = f"{type(exc).__name__}: {exc}"
    out["tempo_bpm"] = float(tempo)
    out["bar_samples"] = int(bar_samples)
    return out


def run_rt_prewarm(
    player: Any,
    *,
    root_note: int,
    tempo_bpm: float,
    sample_rate: int,
    chord_cache: bool = True,
    mono_cache: bool = True,
    mix_master: bool = True,
) -> Dict[str, Any]:
    """Run enabled prewarm steps; returns a small report dict."""
    report: Dict[str, Any] = {}
    if chord_cache:
        report["chords"] = prewarm_chord_cache(
            player,
            root_note=int(root_note),
            tempo_bpm=float(tempo_bpm),
        )
    if mono_cache:
        report["mono"] = prewarm_monophonic_cache(
            player,
            root_note=int(root_note),
            tempo_bpm=float(tempo_bpm),
        )
    if mix_master:
        report["mix_master"] = warmup_mix_master(
            player,
            root_note=int(root_note),
            tempo_bpm=float(tempo_bpm),
            sample_rate=int(sample_rate),
        )
    return report
