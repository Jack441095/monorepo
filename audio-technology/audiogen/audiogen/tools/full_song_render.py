from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# (channel, midi, velocity, start_beats, duration_beats, notes)
SongEvent = Tuple[int, Any, int, float, float, List[int]]


def slice_events_for_bar(
    events: Sequence[SongEvent],
    *,
    bar_index: int,
    beats_per_bar: float = 4.0,
) -> List[SongEvent]:
    """Crop song-global events to one bar and translate timestamps to bar-local beats."""
    out: List[SongEvent] = []
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    bar_start = float(bar_index) * bpb
    bar_end = bar_start + bpb
    for ev in list(events or []):
        if not ev or len(ev) != 6:
            continue
        try:
            ch, midi, vel, st, dur, notes = ev
            stf = float(st)
            durf = float(dur)
        except Exception:
            continue
        if durf <= 1e-9:
            continue
        ev_end = stf + durf
        if ev_end <= bar_start or stf >= bar_end:
            continue
        local_start = max(stf, bar_start) - bar_start
        local_end = min(ev_end, bar_end) - bar_start
        local_dur = float(local_end - local_start)
        if local_dur <= 1e-9:
            continue
        try:
            out.append((int(ch), midi, int(vel), float(local_start), float(local_dur), list(notes)))
        except Exception:
            continue
    return out


def tempo_for_beat(tempo_map: Sequence[Tuple[float, float]], beat: float, *, fallback_bpm: float = 70.0) -> float:
    """Return BPM for a given beat using a piecewise-constant tempo_map[(start_beat, bpm)]."""
    bpm = float(fallback_bpm)
    for tp in list(tempo_map or []):
        try:
            start_beat, this_bpm = float(tp[0]), float(tp[1])
        except Exception:
            continue
        if start_beat <= float(beat):
            bpm = float(this_bpm)
        else:
            break
    return max(20.0, min(260.0, float(bpm)))


def arrangement_role_for_export_bar(song_render: Any, bar_index: int) -> str:
    """Map global bar index within ``song_render`` to ``metadata.section_roles`` entry."""
    if song_render is None:
        return ""
    try:
        sections = list(getattr(song_render, "sections", []) or [])
        md = getattr(song_render, "metadata", None) or {}
        roles = list(md.get("section_roles") or [])
    except Exception:
        return ""
    bi = int(bar_index)
    start_bar = 0
    for i, sec in enumerate(sections):
        try:
            bars = int(getattr(sec, "bars", 0) or 0)
        except Exception:
            bars = 0
        if bars <= 0:
            continue
        if start_bar <= bi < start_bar + bars:
            if i < len(roles):
                return str(roles[i] or "").strip().lower()
            return ""
        start_bar += bars
    return ""


def arrangement_pre_chorus_last_bar_for_export(song_render: Any, bar_index: int) -> bool:
    """True when this global bar is the last bar of a pre-chorus section in the song timeline."""
    if song_render is None:
        return False
    try:
        sections = list(getattr(song_render, "sections", []) or [])
        md = getattr(song_render, "metadata", None) or {}
        roles = list(md.get("section_roles") or [])
    except Exception:
        return False
    bi = int(bar_index)
    start_bar = 0
    for i, sec in enumerate(sections):
        try:
            bars = int(getattr(sec, "bars", 0) or 0)
        except Exception:
            bars = 0
        if bars <= 0:
            continue
        if start_bar <= bi < start_bar + bars:
            role = str(roles[i] if i < len(roles) else "").strip().lower()
            if role == "pre_chorus" and bi == start_bar + bars - 1:
                return True
            return False
        start_bar += bars
    return False


def render_song_events_to_audio(
    *,
    config: Any,
    song_events: Sequence[SongEvent],
    total_bars: int,
    song_render: Any = None,
    beats_per_bar: float = 4.0,
    fallback_bpm: float = 70.0,
) -> Tuple[np.ndarray, int]:
    """Render song-global events to one contiguous stereo float32 buffer (no file I/O)."""
    from audio.RT_player.renderer import AudioRenderer
    from audio.audio_container import AudioContainer
    from composition.song_generator import SongRender
    from audiogen_core.constants import DEFAULT_SAMPLE_RATE
    from sampler import SamplerEngine as SamplerSynthesisEngine

    if song_render is None:
        song_render = SongRender(sections=[], events=list(song_events or []), tempo_map=[], metadata={})

    sample_rate = int(getattr(getattr(config, "audio", None), "sample_rate", DEFAULT_SAMPLE_RATE) or DEFAULT_SAMPLE_RATE)
    container = AudioContainer.create_from_config(config)
    synth = SamplerSynthesisEngine(config)
    try:
        synth.preload_samplers(["bass", "chords", "melody", "arp", "drone", "counter_melody"])
    except Exception:
        pass

    renderer = AudioRenderer(
        synthesis_engine=synth,
        mixer=container.mixer,
        sample_rate=container.sample_rate,
        master_bus=getattr(container, "master_bus", None),
    )

    tempo_map: List[Tuple[float, float]] = []
    try:
        tempo_map = list(getattr(song_render, "tempo_map", []) or [])
    except Exception:
        tempo_map = []
    if tempo_map:
        try:
            fallback_bpm = float(tempo_map[0][1])
        except Exception:
            pass

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    bars_i = max(0, int(total_bars))
    rendered_bars: List[Optional[np.ndarray]] = [None] * bars_i

    def _render_single_bar(bar_idx: int) -> Tuple[int, np.ndarray]:
        beat = float(bar_idx) * bpb
        bpm = tempo_for_beat(tempo_map, beat, fallback_bpm=float(fallback_bpm))
        bar_samples = int(round((bpb * 60.0 / max(1.0, float(bpm))) * float(sample_rate)))
        bar_samples = max(1, int(bar_samples))
        ev_bar = slice_events_for_bar(list(song_events or []), bar_index=int(bar_idx), beats_per_bar=bpb)
        role_bar = arrangement_role_for_export_bar(song_render, int(bar_idx))

        export_fx_scale = 1.0
        try:
            _aexp = getattr(config, "audio", None)
            if _aexp is not None and bool(getattr(_aexp, "arrangement_fx_return_automation_enabled", True)):
                from data.arrangement_curves import arrangement_role_fx_return_mult

                _st = float(getattr(_aexp, "arrangement_fx_return_strength", 1.0) or 1.0)
                export_fx_scale = float(arrangement_role_fx_return_mult(str(role_bar or ""), strength=_st))
        except Exception:
            export_fx_scale = 1.0

        export_vel_ride = 1.0
        try:
            _aexp2 = getattr(config, "audio", None)
            if _aexp2 is not None and bool(getattr(_aexp2, "arrangement_velocity_ride_enabled", True)):
                from data.arrangement_curves import arrangement_role_velocity_ride_mult

                _vst2 = float(getattr(_aexp2, "arrangement_velocity_ride_strength", 1.0) or 1.0)
                _pcl_m = arrangement_pre_chorus_last_bar_for_export(song_render, int(bar_idx))
                _sw2 = bool(getattr(_aexp2, "arrangement_pre_chorus_last_bar_swell_enabled", True))
                _pss2 = float(getattr(_aexp2, "arrangement_pre_chorus_last_bar_swell_strength", 1.0) or 1.0)
                export_vel_ride = float(
                    arrangement_role_velocity_ride_mult(
                        str(role_bar or ""),
                        strength=_vst2,
                        pre_chorus_last_bar=(_pcl_m and _sw2),
                        pre_chorus_swell_strength=_pss2,
                    )
                )
        except Exception:
            export_vel_ride = 1.0

        audio_bar = renderer.render_bar(
            ev_bar,
            tempo=float(bpm),
            bar_samples=int(bar_samples),
            velocity_multiplier=float(export_vel_ride),
            arrangement_role=str(role_bar or ""),
            fx_return_scale=float(export_fx_scale),
        )
        return bar_idx, audio_bar.astype("float32", copy=False)

    # Bars are rendered strictly sequentially and on a single shared
    # `renderer`/`container.mixer` -- NOT parallelizable across a thread
    # pool. Reverted 2026-08-01 after finding a ThreadPoolExecutor version
    # here: AudioRenderer._get_channel_buffers() caches and reuses a numpy
    # buffer keyed only by bar length in samples (renderer.py's
    # _channel_buffers_by_len), so two same-length bars rendered
    # concurrently would write into the *same* array. Deeper than a data
    # race, too: AudioMixer's Delay.process() carries _write_idx/_read_idx
    # ring-buffer state across calls (mixer.py), so delay/reverb tails are
    # only correct when bars are processed in order -- rendering them out
    # of sequence would produce wrong effect tails even with per-thread
    # buffers to fix the race. Bar rendering isn't independent work.
    for bar_idx in range(bars_i):
        try:
            idx, bar_arr = _render_single_bar(bar_idx)
            rendered_bars[idx] = bar_arr
        except Exception:
            logger.exception("In-memory render failed at bar %d/%d", int(bar_idx) + 1, int(bars_i))
            break

    valid_bars = [b for b in rendered_bars if b is not None]
    if valid_bars:
        return np.concatenate(valid_bars, axis=0).astype("float32", copy=False), int(sample_rate)
    return np.zeros((1, 2), dtype="float32"), int(sample_rate)


def write_full_song_outputs(
    *,
    config: Any,
    song_events: Sequence[SongEvent],
    total_bars: int,
    song_render: Any,
    export_dir: Path,
    name_prefix: str = "song",
    stem: Optional[str] = None,
    write_wav: bool = True,
    write_midi: bool = True,
    write_report: bool = True,
    export_stems: bool = False,
) -> Dict[str, str]:
    """
    Render arranged-song events to stereo WAV (+ MIDI/report sidecars) in export_dir.

    Returns dict of paths (missing outputs are ""):
      - wav
      - midi
      - report_json
      - stems: dict of {channel_name: path}, only populated when export_stems
        is True. Captures the real per-instrument (bass/chords/melody/arp/
        drone/counter_melody/kick) buffers the renderer already computes
        before mixer summing -- not a separate solo render pass, so stems
        are exact pre-mix signal, not an approximation.
    """
    from audio.RT_player.renderer import AudioRenderer
    from audio.audio_container import AudioContainer
    from composition.song_generator import SongGenerator, SongRender
    from audiogen_core.constants import DEFAULT_SAMPLE_RATE
    from sampler import SamplerEngine as SamplerSynthesisEngine

    wavfile = None
    if write_wav:
        try:
            from scipy.io import wavfile as _wavfile  # type: ignore[import]

            wavfile = _wavfile
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "WAV export requested but scipy is not available. Install scipy or disable WAV export."
            ) from e

    export_dir.mkdir(parents=True, exist_ok=True)

    safe_prefix = "".join(c if (str(c).isalnum() or c in {"-", "_"}) else "_" for c in str(name_prefix))
    if stem is None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        stem = f"{safe_prefix}_{stamp}" if safe_prefix else f"song_{stamp}"
    else:
        stem = str(stem)

    if song_render is None:
        song_render = SongRender(sections=[], events=list(song_events or []), tempo_map=[], metadata={})

    out: Dict[str, str] = {"wav": "", "midi": "", "report_json": "", "stem": str(stem), "stems": {}}

    if write_report:
        try:
            out["report_json"] = str(
                Path(SongGenerator.export_report(song_render, out_path=str(export_dir / f"{stem}.json")))
            )
        except Exception:
            logger.exception("Offline export: report sidecar failed")
            out["report_json"] = ""

    if write_midi:
        try:
            midi_path = export_dir / f"{stem}.mid"
            SongGenerator.export_to_midi(song_render, out_path=str(midi_path))
            out["midi"] = str(midi_path)
        except Exception as e:
            msg = str(e or "")
            if "pretty_midi" in msg or "MIDI export requires" in msg:
                logger.warning("Offline export: MIDI skipped (%s)", msg)
            else:
                logger.exception("Offline export: MIDI failed")
            out["midi"] = ""

    if not write_wav:
        return out

    sample_rate = int(getattr(getattr(config, "audio", None), "sample_rate", DEFAULT_SAMPLE_RATE) or DEFAULT_SAMPLE_RATE)

    container = AudioContainer.create_from_config(config)
    synth = SamplerSynthesisEngine(config)
    try:
        synth.preload_samplers(["bass", "chords", "melody", "arp", "drone", "counter_melody"])
    except Exception:
        pass

    renderer = AudioRenderer(
        synthesis_engine=synth,
        mixer=container.mixer,
        sample_rate=container.sample_rate,
        master_bus=getattr(container, "master_bus", None),
    )

    tempo_map: List[Tuple[float, float]] = []
    try:
        tempo_map = list(getattr(song_render, "tempo_map", []) or [])
    except Exception:
        tempo_map = []

    fallback_bpm = 70.0
    if tempo_map:
        try:
            fallback_bpm = float(tempo_map[0][1])
        except Exception:
            fallback_bpm = 70.0

    bars_i = max(0, int(total_bars))
    rendered_bars: List[np.ndarray] = []
    stem_sink: Optional[Dict[int, List[np.ndarray]]] = {} if export_stems else None
    for bar_idx in range(bars_i):
        if int(bar_idx) == 0 or int(bar_idx) % 4 == 0 or int(bar_idx) == int(bars_i) - 1:
            try:
                logger.info("Offline render: bar %d/%d", int(bar_idx) + 1, int(bars_i))
            except Exception:
                pass
        beat = float(bar_idx) * 4.0
        bpm = tempo_for_beat(tempo_map, beat, fallback_bpm=float(fallback_bpm))
        bar_samples = int(round((4.0 * 60.0 / max(1.0, float(bpm))) * float(sample_rate)))
        bar_samples = max(1, int(bar_samples))
        ev_bar = slice_events_for_bar(list(song_events or []), bar_index=int(bar_idx), beats_per_bar=4.0)
        role_bar = arrangement_role_for_export_bar(song_render, int(bar_idx))

        export_fx_scale = 1.0
        try:
            _aexp = getattr(config, "audio", None)
            if _aexp is not None and bool(getattr(_aexp, "arrangement_fx_return_automation_enabled", True)):
                from data.arrangement_curves import arrangement_role_fx_return_mult

                _st = float(getattr(_aexp, "arrangement_fx_return_strength", 1.0) or 1.0)
                export_fx_scale = float(arrangement_role_fx_return_mult(str(role_bar or ""), strength=_st))
        except Exception:
            export_fx_scale = 1.0

        export_vel_ride = 1.0
        try:
            _aexp2 = getattr(config, "audio", None)
            if _aexp2 is not None and bool(getattr(_aexp2, "arrangement_velocity_ride_enabled", True)):
                from data.arrangement_curves import arrangement_role_velocity_ride_mult

                _vst2 = float(getattr(_aexp2, "arrangement_velocity_ride_strength", 1.0) or 1.0)
                _pcl_m = arrangement_pre_chorus_last_bar_for_export(song_render, int(bar_idx))
                _sw2 = bool(getattr(_aexp2, "arrangement_pre_chorus_last_bar_swell_enabled", True))
                _pss2 = float(getattr(_aexp2, "arrangement_pre_chorus_last_bar_swell_strength", 1.0) or 1.0)
                export_vel_ride = float(
                    arrangement_role_velocity_ride_mult(
                        str(role_bar or ""),
                        strength=_vst2,
                        pre_chorus_last_bar=(_pcl_m and _sw2),
                        pre_chorus_swell_strength=_pss2,
                    )
                )
        except Exception:
            export_vel_ride = 1.0

        try:
            audio_bar = renderer.render_bar(
                ev_bar,
                tempo=float(bpm),
                bar_samples=int(bar_samples),
                velocity_multiplier=float(export_vel_ride),
                arrangement_role=str(role_bar or ""),
                fx_return_scale=float(export_fx_scale),
                stem_sink=stem_sink,
            )
            rendered_bars.append(audio_bar.astype("float32", copy=False))
        except Exception:
            logger.exception("Offline render failed at bar %d/%d", int(bar_idx) + 1, int(bars_i))
            break

    if rendered_bars:
        audio = np.concatenate(rendered_bars, axis=0).astype("float32", copy=False)
    else:
        audio = np.zeros((1, 2), dtype="float32")

    wav_path = export_dir / f"{stem}.wav"
    try:
        assert wavfile is not None
        wav_i16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("int16")
        wavfile.write(str(wav_path), int(sample_rate), wav_i16)
        out["wav"] = str(wav_path)
    except Exception:
        logger.exception("Offline WAV write failed")
        out["wav"] = ""

    if export_stems and stem_sink:
        from audiogen_core.mixer_config import CHANNEL_NAMES

        stems_out: Dict[str, str] = {}
        for ch, bars_list in stem_sink.items():
            if not bars_list:
                continue
            try:
                stem_audio = np.concatenate(bars_list, axis=0).astype("float32", copy=False)
                name = CHANNEL_NAMES.get(int(ch), f"channel{ch}")
                stem_path = export_dir / f"{stem}_stem_{name}.wav"
                stem_i16 = (np.clip(stem_audio, -1.0, 1.0) * 32767.0).astype("int16")
                assert wavfile is not None
                wavfile.write(str(stem_path), int(sample_rate), stem_i16)
                stems_out[name] = str(stem_path)
            except Exception:
                logger.exception("Offline export: stem WAV write failed for channel %s", ch)
        out["stems"] = stems_out

    return out

