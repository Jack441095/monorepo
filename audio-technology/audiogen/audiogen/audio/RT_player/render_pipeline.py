# audio/RT_player/render_pipeline.py
# Project module `render_pipeline` (audio).

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from audiogen_core.mixer_config import AUDIO_MIXER_CHANNEL_COUNT

logger = logging.getLogger(__name__)


class RenderPipeline:
    """Owns event routing and per-channel render assembly for AudioRenderer."""

    # Must include 4: composition emits sustained drone as channel-4 note events.
    # (Previously dropped by the single-pass partition when 4 was omitted — audible as
    # sudden dropouts whenever the live drone slice path did not fill that stem.)
    MONO_CHANNELS = {0, 2, 3, 4, 5}

    def __init__(self, owner):
        self.owner = owner

    @staticmethod
    def create_channel_buffers(bar_samples: int, n_channels: int = AUDIO_MIXER_CHANNEL_COUNT) -> Dict[int, np.ndarray]:
        return {
            i: np.zeros((bar_samples, 2), dtype=np.float32)
            for i in range(n_channels)
        }

    @staticmethod
    def partition_mono_chord_events(events: List[Tuple]) -> Tuple[Dict[int, List], List]:
        """
        One pass over sorted bar events: monophonic buckets vs chord (channel 1).
        Avoids scanning the full list again for every monophonic channel and for chords.
        """
        mono_bins: Dict[int, List] = {ch: [] for ch in RenderPipeline.MONO_CHANNELS}
        chord_events: List = []
        for ev in events:
            if not ev:
                continue
            ch = ev[0]
            if ch in mono_bins:
                mono_bins[ch].append(ev)
            elif ch == 1:
                chord_events.append(ev)
        return mono_bins, chord_events

    def render_monophonic_channels(
        self,
        mono_bins: Dict[int, List],
        tempo: float,
        bar_samples: int,
        channel_audio: Dict[int, np.ndarray],
        *,
        events_sorted: bool = False,
    ) -> None:
        for mono_ch in self.MONO_CHANNELS:
            ch_events = mono_bins[mono_ch]
            if not ch_events:
                continue
            try:
                dst = channel_audio[mono_ch]
                self.owner.synthesis_engine.render_monophonic_channel(
                    mono_ch,
                    ch_events,
                    bar_samples,
                    tempo,
                    out=dst,
                    events_sorted=events_sorted,
                )
            except Exception:
                logger.exception("Error rendering monophonic channel %s", mono_ch)

    @staticmethod
    def extract_polyphonic_notes(midi: int, notes) -> List[int]:
        if notes and isinstance(notes, list):
            return [int(n) for n in notes if isinstance(n, (int, np.integer)) and 21 <= n <= 108]
        if 21 <= midi <= 108:
            return [midi]
        return []

    @staticmethod
    def _chord_duration_quantize_sec(duration_sec: float) -> float:
        """Bucket pad lengths for chord cache hits (inaudible on sustained comps)."""
        try:
            from audiogen_core.config import CONFIG

            ms = float(getattr(getattr(CONFIG, "audio", None), "chord_render_duration_quantize_ms", 50.0) or 50.0)
        except Exception:
            ms = 50.0
        if ms <= 1e-6:
            return max(0.05, float(duration_sec))
        step = max(0.001, float(ms) / 1000.0)
        d = max(0.05, float(duration_sec))
        return float(round(d / step) * step)

    def _render_polyphonic_events_legacy(
        self,
        events: List[Tuple],
        tempo: float,
        bar_samples: int,
        channel_audio: Dict[int, np.ndarray],
    ) -> None:
        for ev in events:
            if len(ev) != 6:
                logger.error("Event has wrong length (%s): %s", len(ev), ev)
                continue
            channel, midi, velocity, start_beats, duration_beats, notes = ev
            if not isinstance(channel, int) or channel != 1:
                continue
            start_sample = int(float(start_beats) / 4.0 * float(bar_samples))
            duration_sec = float(duration_beats) * (60.0 / max(40.0, float(tempo)))
            try:
                note_notes = self.extract_polyphonic_notes(midi, notes)
                if not note_notes:
                    continue
                note_audio = self.owner.synthesis_engine.render_chord(
                    note_notes, int(velocity), duration_sec, channel=1
                )
                if note_audio is None or len(note_audio) == 0 or start_sample >= bar_samples:
                    continue
                end = min(start_sample + len(note_audio), bar_samples)
                seg_len = end - start_sample
                if seg_len <= 0:
                    continue
                target = channel_audio[channel][start_sample:end]
                safe_len = min(len(target), len(note_audio[:seg_len]))
                if safe_len > 0:
                    target[:safe_len] += note_audio[:safe_len]
            except Exception as exc:
                logger.exception("Render error on ch1: %s", exc)

    def render_polyphonic_events(
        self,
        events: List[Tuple],
        tempo: float,
        bar_samples: int,
        channel_audio: Dict[int, np.ndarray],
    ) -> None:
        if not events:
            return

        engine = self.owner.synthesis_engine
        get_cr = getattr(engine, "_get_chord_renderer", None)
        if not callable(get_cr):
            self._render_polyphonic_events_legacy(events, tempo, bar_samples, channel_audio)
            return

        chord_renderer = get_cr()
        tempo_f = max(40.0, float(tempo))
        ch = 1
        target = channel_audio[ch]
        sampler_token = ""
        try:
            sampler = engine._get_sampler(engine._channel_to_sampler(ch))
            sampler_token = str(sampler._transposition_mode_cache_token())
        except Exception:
            pass

        unique: Dict[Tuple, Tuple[List[int], int, float]] = {}
        placements: List[Tuple[int, Tuple, int]] = []

        for ev in events:
            if len(ev) != 6:
                logger.error("Event has wrong length (%s): %s", len(ev), ev)
                continue
            channel, midi, velocity, start_beats, duration_beats, notes = ev
            if not isinstance(channel, int) or channel != 1:
                continue

            start_sample = int(float(start_beats) / 4.0 * float(bar_samples))
            if start_sample >= int(bar_samples):
                continue
            duration_sec = float(duration_beats) * (60.0 / tempo_f)
            note_notes = self.extract_polyphonic_notes(midi, notes)
            if not note_notes:
                continue

            vel = int(max(1, min(127, round(int(velocity) / 8.0) * 8)))
            dur_q = self._chord_duration_quantize_sec(duration_sec)
            cache_key = chord_renderer.build_cache_key(
                note_notes,
                vel,
                dur_q,
                ch,
                None,
                0.0,
                sampler_token,
            )
            placements.append((start_sample, cache_key, int(bar_samples)))
            prev = unique.get(cache_key)
            if prev is None or float(prev[2]) < float(dur_q):
                unique[cache_key] = (list(note_notes), vel, float(dur_q))

        for cache_key, (note_notes, vel, dur_q) in unique.items():
            if chord_renderer.get_cached(cache_key) is not None:
                continue
            try:
                engine.render_chord(note_notes, vel, float(dur_q), channel=ch)
            except Exception as exc:
                logger.exception("Chord preload render failed: %s", exc)

        for start_sample, cache_key, bs in placements:
            try:
                note_audio = chord_renderer.get_cached(cache_key)
                if note_audio is None:
                    note_notes, vel, dur_q = unique[cache_key]
                    note_audio = engine.render_chord(note_notes, vel, float(dur_q), channel=ch)
                if note_audio is None or len(note_audio) == 0:
                    continue
                end = min(int(start_sample) + len(note_audio), int(bs))
                seg_len = end - int(start_sample)
                if seg_len <= 0:
                    continue
                note_seg = note_audio[:seg_len]
                dst = target[int(start_sample):end]
                safe_len = min(len(dst), len(note_seg))
                if safe_len > 0:
                    dst[:safe_len] += note_seg[:safe_len]
            except Exception as exc:
                logger.exception("Render error on ch%s: %s", ch, exc)

    @staticmethod
    def apply_drone_and_velocity(
        channel_audio: Dict[int, np.ndarray],
        drone: Optional[np.ndarray],
        bar_samples: int,
        velocity_multiplier: float,
    ) -> None:
        if drone is not None:
            ch4 = channel_audio.get(4)
            if ch4 is not None:
                n = min(int(bar_samples), len(ch4), len(drone))
                if n > 0:
                    ch4[:n] += drone[:n]
            else:
                channel_audio[4] = drone[:bar_samples]

        if velocity_multiplier != 1.0:
            for ch in range(int(AUDIO_MIXER_CHANNEL_COUNT)):
                if ch != 4:
                    channel_audio[ch] *= velocity_multiplier
