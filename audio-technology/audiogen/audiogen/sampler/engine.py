from audiogen_core.config import resolve_config
import logging
from typing import Dict, List, Optional, Tuple, cast

import numpy as np

from audiogen_core.config import CONFIG
from audiogen_core.mixer_config import CHANNEL_NAMES, KICK_MIXER_CHANNEL_INDEX

from .chord_renderer import ChordRenderer
from .monophonic import MonophonicRenderer
from .registry import SamplerRegistry
from .sampler import Sampler

logger = logging.getLogger(__name__)

# Monophonic channels (bass, melody, arp, drone bed)
MONOPHONIC_CHANNEL_NAMES = frozenset({"bass", "melody", "arp", "drone", "counter_melody"})


class SamplerEngine:
    """
    High‑level manager for multiple samplers (bass, chords, melody, drone, counter).
    Provides lazy loading and rendering functions.
    """

    def __init__(self, config=None):
        self.config = config or CONFIG
        self._sample_rate = self.config.audio.sample_rate
        self.registry = SamplerRegistry(
            config=self.config,
            sample_rate=self._sample_rate,
            sampler_factory=self._create_sampler,
            mono_renderer_factory=self._create_monophonic_renderer,
        )
        self.samplers = self.registry.samplers
        self._mono_renderers = self.registry.mono_renderers
        audio_cfg = getattr(self.config, "audio", None)
        chord_cache_maxsize = 1024
        chord_cache_max_bytes = 64 * 1024 * 1024
        if audio_cfg is not None:
            chord_cache_maxsize = int(getattr(audio_cfg, "chord_cache_maxsize", 1024) or 1024)
            chord_cache_max_bytes = int(
                getattr(audio_cfg, "chord_cache_max_bytes", 64 * 1024 * 1024) or (64 * 1024 * 1024)
            )
        self.chord_renderer = ChordRenderer(
            self, maxsize=int(max(16, chord_cache_maxsize)), max_bytes=int(max(0, chord_cache_max_bytes))
        )
        logger.info("Sampler engine ready (lazy loading)")

    def _create_sampler(self, sampler_config, sample_rate: int):
        try:
            return Sampler(sampler_config, sample_rate=sample_rate, global_config=self.config)
        except TypeError:
            # Tests may patch `Sampler` with a simpler signature.
            return Sampler(sampler_config, sample_rate)

    @staticmethod
    def _create_monophonic_renderer(sampler, sample_rate: int):
        return MonophonicRenderer(sampler, sample_rate)

    def _get_chord_renderer(self) -> ChordRenderer:
        renderer = getattr(self, "chord_renderer", None)
        if renderer is None:
            maxsize = getattr(self, "_chord_cache_maxsize", 1024)
            max_bytes = getattr(self, "_chord_cache_max_bytes", 64 * 1024 * 1024)
            renderer = ChordRenderer(self, maxsize=maxsize, max_bytes=max_bytes)
            legacy_cache = getattr(self, "_chord_cache", None)
            if legacy_cache is not None:
                renderer.cache = legacy_cache
                try:
                    renderer._cache_bytes = int(
                        sum(int(getattr(v, "nbytes", 0) or 0) for v in legacy_cache.values())
                    )
                except Exception:
                    renderer._cache_bytes = 0
            self.chord_renderer = renderer
        return renderer

    def _get_sampler(self, name: str) -> Sampler:
        # `get_sampler` returns an existing sampler if already loaded.
        # Avoid hot-path debug logging on every access; only log when a sampler
        # transitions from unloaded -> loaded.
        try:
            was_loaded = name in getattr(self.registry, "samplers", {})
        except Exception:
            was_loaded = False
        sampler = self.registry.get_sampler(name)
        if not was_loaded:
            logger.debug("Lazy loaded sampler: %s", name)
        return sampler

    def preload_all_samplers(self):
        """Load all sampler configurations synchronously to avoid lazy loading in threads."""
        logger.info("Pre-loading all samplers...")
        for sampler_config in self.config.samplers:
            try:
                self._get_sampler(sampler_config.name)
                logger.info(f"Pre-loaded sampler: {sampler_config.name}")
            except Exception as e:
                logger.error(f"Failed to pre-load sampler {sampler_config.name}: {e}")
        logger.info("All samplers pre-loaded")

    def preload_samplers(self, sampler_names: List[str]):
        """Load a selected subset of samplers synchronously."""
        if not sampler_names:
            return
        requested = set(sampler_names)
        logger.info("Pre-loading selected samplers: %s", ", ".join(sorted(requested)))
        for sampler_config in self.config.samplers:
            if sampler_config.name not in requested:
                continue
            try:
                self._get_sampler(sampler_config.name)
                logger.info("Pre-loaded sampler: %s", sampler_config.name)
            except Exception as e:
                logger.error("Failed to pre-load sampler %s: %s", sampler_config.name, e)

    def _channel_to_sampler(self, channel: int) -> Optional[str]:
        if int(channel) == int(KICK_MIXER_CHANNEL_INDEX):
            return None
        base = CHANNEL_NAMES.get(channel)
        if base is None:
            return None
        # Instrument-source routing:
        # - sampler: existing channel->sampler mapping (legacy/default)
        # - piano: prefer dedicated piano samplers if present; otherwise fall back safely
        try:
            source = str(
                getattr(getattr(self.config, "composition", None), "instrument_source", "sampler")
                or "sampler"
            ).strip().lower()
        except Exception:
            source = "sampler"
        if source != "piano":
            return base

        # Keep drone unchanged in piano mode.
        if int(channel) == 4:
            return base

        configured = set()
        try:
            configured = {str(getattr(s, "name", "") or "") for s in list(getattr(self.config, "samplers", []) or [])}
        except Exception:
            configured = set()

        candidates = [f"piano_{base}", f"{base}_piano"]
        # Support a single shared piano sampler for all musical channels.
        if int(channel) in (0, 1, 2, 3, 5):
            candidates.insert(0, "piano")
        for name in candidates:
            if name in configured:
                return str(name)
        return base

    def prewarm_notes(self, midi_notes: List[int], velocity: int = 80):
        for midi in set(midi_notes):
            for ch in range(6):
                sampler_name = self._channel_to_sampler(ch)
                if sampler_name and sampler_name in self.samplers:
                    self.samplers[sampler_name].render_note(midi, velocity, 0.1)

    def unload_samplers(self, *, keep: Optional[set[str]] = None) -> int:
        """
        Drop cached sampler instances so they reload from current CONFIG when needed.

        `keep` is a set of sampler names to preserve (e.g. {"drone"} to keep the drone continuous).
        """
        try:
            k = {str(x) for x in (keep or set()) if str(x)}
        except Exception:
            k = set()
        try:
            return int(self.registry.drop_all_except(k))
        except Exception:
            return 0

    def prefetch_events(
        self,
        events: List[Tuple],
        *,
        tempo: float,
        default_velocity: int = 80,
    ) -> None:
        """
        Best-effort cache prefill for the next bar.
        This is intentionally "dumb": just render the exact note/chord shapes to populate LRU caches.
        Safe to call from a background thread.
        """
        if not events:
            return
        try:
            tempo = float(tempo)
            if tempo <= 0:
                return
        except (ValueError, TypeError):
            return

        seen = set()
        for ev in events:
            if not ev or len(ev) != 6:
                continue
            ch, midi, vel, _start_beats, dur_beats, notes = ev
            if not isinstance(ch, int) or ch < 0 or ch > 5:
                continue
            try:
                velocity = (
                    int(vel)
                    if isinstance(vel, (int, np.integer))
                    else int(default_velocity)
                )
                duration_sec = float(dur_beats) * (60.0 / tempo)
            except (ValueError, TypeError):
                continue
            if duration_sec <= 0.0:
                continue
            # Align with sampler note cache rounding (avoids duplicate prefetch work).
            dur_key = round(float(duration_sec), 4)
            if ch == 1:

                ms = resolve_config("audio", "chord_render_duration_quantize_ms", 50.0, float)
                if ms > 1e-6:
                    step = max(0.001, float(ms) / 1000.0)
                    d = max(0.05, float(duration_sec))
                    dur_key = round(d / step) * step
                else:
                    dur_key = round(float(duration_sec), 4)

            # Monophonic channels
            if ch in (0, 2, 3, 4, 5):
                try:
                    from .monophonic import quantize_mono_duration_sec

                    dur_key = quantize_mono_duration_sec(duration_sec)
                except (ImportError, AttributeError, ValueError, TypeError):
                    dur_key = round(float(duration_sec), 4)
                sampler_name = self._channel_to_sampler(ch)
                if not sampler_name:
                    continue
                k = (str(sampler_name), int(midi), int(velocity), float(dur_key), None)
                if k in seen:
                    continue
                seen.add(k)
                try:
                    sampler = self._get_sampler(sampler_name)
                    sampler.render_note(int(midi), velocity, float(dur_key))
                except Exception as e:
                    logger.warning(
                        "Prefetch render_note failed for sampler %s, note %d: %s",
                        sampler_name, midi, e, exc_info=True
                    )
                    continue
                continue

            # Chords (channel 1)
            if ch == 1:
                chord_notes: List[int] = []
                if notes and isinstance(notes, list):
                    chord_notes = [
                        int(n)
                        for n in notes
                        if isinstance(n, (int, np.integer)) and 21 <= int(n) <= 108
                    ]
                elif isinstance(midi, (int, np.integer)) and 21 <= int(midi) <= 108:
                    chord_notes = [int(midi)]
                if not chord_notes:
                    continue
                ck = (tuple(sorted(chord_notes)), int(velocity), float(dur_key))
                if ck in seen:
                    continue
                seen.add(ck)
                try:
                    self.render_chord(chord_notes, velocity, float(dur_key), channel=1)
                except Exception as e:
                    logger.warning(
                        "Prefetch render_chord failed for notes %s: %s",
                        chord_notes, e, exc_info=True
                    )
                    continue

    def render_monophonic_channel(
        self,
        channel: int,
        events: List[Tuple],
        bar_samples: int,
        tempo: float,
        out: Optional[np.ndarray] = None,
        *,
        events_sorted: bool = False,
    ) -> np.ndarray:
        """Events must already be filtered to this ``channel`` (see RenderPipeline)."""
        bs = int(max(0, bar_samples))
        sampler_name = self._channel_to_sampler(channel)
        if sampler_name is None:
            if out is not None:
                if out.shape != (bs, 2) or out.dtype != np.float32:
                    raise ValueError(f"out must be float32 ({bs}, 2)")
                out.fill(0.0)
                return out
            return np.zeros((bs, 2), dtype=np.float32)
        renderer = self.registry.get_monophonic_renderer(sampler_name)
        if renderer is None:
            self._get_sampler(sampler_name)
            renderer = self.registry.get_monophonic_renderer(sampler_name)
        return renderer.render_bar(
            events, bar_samples, tempo, out=out, events_sorted=events_sorted
        )

    def render(self, midi: int, velocity: int, duration_sec: float, channel: int = 0) -> np.ndarray:
        sampler_name = self._channel_to_sampler(channel)
        if sampler_name is None:
            raise ValueError(f"No sampler mapped for MIDI channel {channel}")
        sampler = self._get_sampler(sampler_name)
        return sampler.render_note(midi, velocity, duration_sec)

    def render_chord(
        self,
        chord_notes: List[int],
        velocity: int,
        duration_sec: float,
        channel: int = 1,
        tags: Optional[List[str]] = None,
        spread: float = 0.0,
    ) -> np.ndarray:
        sampler_name = cast(str, self._channel_to_sampler(channel))
        sampler = self._get_sampler(sampler_name)
        return self._get_chord_renderer().render(
            sampler,
            chord_notes,
            velocity,
            duration_sec,
            channel=channel,
            tags=tags,
            spread=spread,
        )

    def render_drone_block(
        self, duration_sec: float, midi_note: int = 60, velocity: int = 80
    ) -> np.ndarray:
        """Render a block of drone audio (fixed pitch, looping)."""
        sampler_name = "drone"
        sampler = self._get_sampler(sampler_name)
        return sampler.render_note(midi_note, velocity, duration_sec)

    def get_sampler_info(self) -> Dict[str, Dict]:
        info = {}
        for name, s in self.samplers.items():
            if s.layers and s._raw_cache:
                layer = s.layers[0]
                audio = s._raw_cache[0]
                info[name] = {
                    "root_midi": layer.root_midi,
                    "root_note": self._midi_to_note(layer.root_midi),
                    "monophonic": name in MONOPHONIC_CHANNEL_NAMES,
                    "duration": len(audio) / self._sample_rate,
                    "channels": audio.shape[1] if audio.ndim > 1 else 1,
                    "file": str(layer.file_path),
                    "num_layers": len(s.layers),
                    "loop_start_samples": layer.loop_start,
                    "loop_end_samples": layer.loop_end,
                    "filter": {
                        "enabled": layer.pitch_tracking,
                        "settings": layer.filter_settings,
                    },
                }
        return info

    def update_filter_settings(self, channel_name: str, **kwargs):
        if channel_name in self.samplers:
            if channel_name == "bass" and "max_cutoff" in kwargs:
                kwargs["max_cutoff"] = min(kwargs["max_cutoff"], 750.0)
            sampler = self.samplers[channel_name]
            for layer in sampler.layers:
                if layer.filter_settings is None:
                    layer.filter_settings = {}
                layer.filter_settings.update(kwargs)
            logger.info(f"Updated {channel_name} filter settings: {kwargs}")

    @staticmethod
    def _midi_to_note(midi: int) -> str:
        notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return f"{notes[midi % 12]}{(midi // 12) - 1}"


# Backward‑compatibility alias
SamplerSynthesisEngine = SamplerEngine
