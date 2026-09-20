# audio/audio_container.py
# ---------------------------------------------------------------------------
# Wires mixer (dry + sends), RoomReverb instance, and MasterBus (returns + master).
# ---------------------------------------------------------------------------
# Central dependency injection container
import logging
from dataclasses import dataclass
from typing import Any, Optional

from audio.engine import EVENT_BUS, AudioMixer, MasterBus
from audiogen_core.mixer_config import AUDIO_MIXER_CHANNEL_COUNT
from audio.engine.reverb import RoomReverb
from midi.midi_range_limiter import MIDIRangeLimiter
from midi.velocity_mapper import VelocityMappingManager

logger = logging.getLogger(__name__)

_DIVISION_BEATS = {
    # straight
    "1/1": 4.0,
    "1/2": 2.0,
    "1/4": 1.0,
    "1/8": 0.5,
    "1/16": 0.25,
    "1/32": 0.125,
    # dotted
    "1/2.": 3.0,
    "1/4.": 1.5,
    "1/8.": 0.75,
    "1/16.": 0.375,
    # triplet
    "1/2t": 4.0 / 3.0,
    "1/4t": 2.0 / 3.0,
    "1/8t": 1.0 / 3.0,
    "1/16t": 1.0 / 6.0,
}


def _tempo_synced_delay_ms(*, bpm: float, division: str) -> Optional[float]:
    try:
        b = float(bpm)
        if b <= 1e-6:
            return None
    except Exception:
        return None
    div = (division or "").strip()
    beats = _DIVISION_BEATS.get(div)
    if beats is None:
        return None
    return float(beats) * (60.0 / float(b)) * 1000.0


def melody_wants_shared_reverb_aux(audio: Any) -> bool:
    """True when melody channel_delay asks for signal on the shared reverb aux."""
    try:
        mcfg = (getattr(audio, "channel_delay", None) or {}).get(2) or {}
    except Exception:
        return False
    if not bool(mcfg.get("enabled", False)):
        return False
    try:
        return float(mcfg.get("reverb_send", 0.22)) > 1e-6
    except Exception:
        return True


def apply_melody_aux_send_hints(mixer: Any, channel_delay: Any, *, melody_ch: int = 2) -> Any:
    """Apply melody channel_delay mix/reverb hints without lowering authored sends."""
    get_channel = getattr(mixer, "get_channel", None)
    if get_channel is None:
        return None
    mch = get_channel(int(melody_ch))
    if mch is None:
        return None
    try:
        mcfg = (channel_delay or {}).get(int(melody_ch)) or {}
    except Exception:
        return mch
    if not bool(mcfg.get("enabled", False)):
        return mch

    try:
        mx = float(mcfg.get("mix", 0.2))
    except Exception:
        mx = 0.2
    delay_send = max(0.0, min(1.0, mx))
    try:
        mch.delay_send = max(float(getattr(mch, "delay_send", 0.0) or 0.0), delay_send)
    except Exception:
        mch.delay_send = delay_send

    try:
        rs = float(mcfg.get("reverb_send", 0.22))
    except Exception:
        rs = 0.22
    reverb_send = max(0.0, min(1.0, rs))
    try:
        mch.reverb_send = max(float(getattr(mch, "reverb_send", 0.0) or 0.0), reverb_send)
    except Exception:
        mch.reverb_send = reverb_send
    return mch


_MISSING = object()


def _field_from_source(source: Any, name: str, default: Any = _MISSING) -> Any:
    if isinstance(source, dict):
        if name in source:
            return source.get(name)
        return default
    return getattr(source, name, default)


def _apply_channel_field(ch: Any, source: Any, ch_idx: int, name: str, cast: Any = None, default: Any = _MISSING) -> None:
    try:
        raw = _field_from_source(source, name, default)
        if raw is _MISSING:
            return
        setattr(ch, name, cast(raw) if cast is not None and raw is not None else raw)
    except Exception:
        logger.debug("failed applying mixer field %s for ch=%s", name, ch_idx, exc_info=True)


def _apply_mixer_channel_source(ch: Any, source: Any, ch_idx: int, *, strip_mode: bool) -> None:
    defaults = {
        "volume": 1.0,
        "pan": 0.0,
        "reverb_send": 0.0,
    } if strip_mode else {}
    _apply_channel_field(ch, source, ch_idx, "volume", float, defaults.get("volume", _MISSING))
    _apply_channel_field(ch, source, ch_idx, "pan", float, defaults.get("pan", _MISSING))
    _apply_channel_field(ch, source, ch_idx, "reverb_send", float, defaults.get("reverb_send", _MISSING))

    for name in ("mute", "solo", "sends_pre_fader"):
        _apply_channel_field(ch, source, ch_idx, name, bool, False if strip_mode and name != "sends_pre_fader" else _MISSING)

    _apply_channel_field(ch, source, ch_idx, "output_bus", lambda value: str(value or "master"), "master" if strip_mode else _MISSING)

    # Per-send pre/post values may be True, False, or None.
    for name in ("reverb_send_pre_fader", "delay_send_pre_fader", "distortion_send_pre_fader"):
        _apply_channel_field(ch, source, ch_idx, name, None, None if strip_mode else _MISSING)

    _apply_channel_field(ch, source, ch_idx, "delay_send", float, getattr(ch, "delay_send", 0.0) if strip_mode else _MISSING)
    _apply_channel_field(
        ch,
        source,
        ch_idx,
        "distortion_send",
        float,
        getattr(ch, "distortion_send", 0.0) if strip_mode else _MISSING,
    )

    _apply_channel_field(ch, source, ch_idx, "filter_enabled", bool, getattr(ch, "filter_enabled", True) if strip_mode else _MISSING)
    _apply_channel_field(ch, source, ch_idx, "highpass_hz", float, getattr(ch, "highpass_hz", 0.0) if strip_mode else _MISSING)
    _apply_channel_field(ch, source, ch_idx, "lowpass_hz", float, getattr(ch, "lowpass_hz", 0.0) if strip_mode else _MISSING)
    _apply_channel_field(
        ch,
        source,
        ch_idx,
        "filter_slope_db_per_oct",
        float,
        getattr(ch, "filter_slope_db_per_oct", 12.0) if strip_mode else _MISSING,
    )


@dataclass
class AudioContainer:
    """Container for all audio processing components."""
    config: Any
    sample_rate: int
    mixer: Any = None
    master_bus: Any = None
    reverb: Any = None
    range_limiter: Any = None
    velocity_mapper: Any = None
    event_bus: Any = None

    @classmethod
    def create_from_config(cls, config):
        sample_rate = config.audio.sample_rate

        logger.info(f"Creating AudioContainer(sample_rate={sample_rate}Hz)")

        mixer = AudioMixer(num_channels=int(AUDIO_MIXER_CHANNEL_COUNT), sample_rate=sample_rate)
        mixer.set_event_bus(EVENT_BUS)

        # Default mix staging keeps the arrangement wider and gives ambience
        # something to work with before any runtime automation is applied.
        strips = getattr(getattr(config, "audio", None), "mixer_strips", None)
        channel_defaults = config.audio.channel_mix
        if isinstance(strips, dict) and strips:
            for ch_idx, strip in strips.items():
                ch = mixer.get_channel(int(ch_idx))
                if ch:
                    _apply_mixer_channel_source(ch, strip, int(ch_idx), strip_mode=True)
        else:
            for ch_idx, defaults in channel_defaults.items():
                ch = mixer.get_channel(ch_idx)
                if ch:
                    _apply_mixer_channel_source(ch, defaults, int(ch_idx), strip_mode=False)

        # Apply EQ settings from config
        for ch_idx, eq_cfg in config.audio.channel_eq.items():
            ch = mixer.get_channel(ch_idx)
            if ch:
                ch.eq_enabled = eq_cfg.enabled
                ch.eq_low_gain_db = eq_cfg.low_gain_db
                ch.eq_mid_gain_db = eq_cfg.mid_gain_db
                ch.eq_high_gain_db = eq_cfg.high_gain_db
                ch.eq_low_freq = eq_cfg.low_freq
                ch.eq_mid_freq = eq_cfg.mid_freq
                ch.eq_high_freq = eq_cfg.high_freq
                ch.eq_mid_q = eq_cfg.mid_q
                logger.debug(f"EQ set for channel {ch_idx}: low={eq_cfg.low_gain_db}dB, "
                             f"mid={eq_cfg.mid_gain_db}dB, high={eq_cfg.high_gain_db}dB")

        # Apply delay settings from config
        for ch_idx, delay_cfg in config.audio.channel_delay.items():
            ch = mixer.get_channel(ch_idx)
            if ch:
                ch.delay_enabled = delay_cfg.get("enabled", False)
                # Optional tempo-sync: `division` in quarter-note beats (e.g. 1/4, 1/8., 1/8t).
                time_ms = float(delay_cfg.get("time_ms", 300.0))
                if bool(delay_cfg.get("sync", False)):
                    bpm = None
                    try:
                        # Prefer shared helper that respects global tempo scale / overrides.
                        from audiogen_core.config import effective_tempo_bpm_from_config

                        bpm = float(effective_tempo_bpm_from_config(config))
                    except Exception:
                        bpm = None
                    if bpm:
                        div = str(delay_cfg.get("division", "1/4"))
                        synced = _tempo_synced_delay_ms(bpm=float(bpm), division=div)
                        if synced is not None:
                            time_ms = float(synced)
                ch.delay_time_ms = time_ms
                ch.delay_feedback = delay_cfg.get("feedback", 0.4)
                ch.delay_mix = delay_cfg.get("mix", 0.3)
                logger.debug(f"Delay set for channel {ch_idx}: enabled={ch.delay_enabled}, "
                             f"time={ch.delay_time_ms}ms, fb={ch.delay_feedback}, mix={ch.delay_mix}")

        # If the melody channel_delay is enabled, treat its mix as an *additional* hint
        # for the DAW-style aux send level. Crucially, don't zero existing delay sends:
        # mixer strips/presets may already be authoring delay sends for multiple channels.
        apply_melody_aux_send_hints(mixer, getattr(config.audio, "channel_delay", None))

        # Create reverb (melody channel_delay can request the shared reverb aux even if reverb was off).
        reverb = RoomReverb(
            sample_rate=sample_rate,
            highpass_hz=float(getattr(config.audio, "reverb_return_highpass_hz", 500.0) or 500.0),
            highpass_slope_db_per_oct=float(
                getattr(config.audio, "reverb_return_highpass_slope_db_per_oct", 12.0) or 12.0
            ),
        )
        if hasattr(config.audio, 'reverb_rt60'):
            reverb.set_rt60(config.audio.reverb_rt60)
        if hasattr(config.audio, 'reverb_damping'):
            reverb.set_damping(config.audio.reverb_damping)
        if hasattr(reverb, "set_predelay_ms"):
            reverb.set_predelay_ms(float(getattr(config.audio, "reverb_predelay_ms", 28.0) or 28.0))
        if hasattr(reverb, "set_early_reflections"):
            reverb.set_early_reflections(
                enabled=bool(getattr(config.audio, "reverb_early_reflections_enabled", True)),
                level=float(getattr(config.audio, "reverb_early_reflections_level", 0.24) or 0.24),
            )
        if hasattr(reverb, "set_return_lowpass"):
            reverb.set_return_lowpass(
                float(getattr(config.audio, "reverb_return_lowpass_hz", 9500.0) or 9500.0),
                float(getattr(config.audio, "reverb_return_lowpass_slope_db_per_oct", 12.0) or 12.0),
            )
        if hasattr(reverb, "set_return_highpass"):
            reverb.set_return_highpass(
                float(getattr(config.audio, "reverb_return_highpass_hz", 500.0) or 500.0),
                float(getattr(config.audio, "reverb_return_highpass_slope_db_per_oct", 12.0) or 12.0),
            )
        if melody_wants_shared_reverb_aux(config.audio) and not bool(getattr(config.audio, "reverb_enabled", True)):
            try:
                config.audio.reverb_enabled = True
            except Exception:
                pass
        try:
            rw = float(getattr(config.audio, "reverb_wet", 0.5))
        except Exception:
            rw = 0.5
        if bool(getattr(config.audio, "reverb_enabled", True)):
            reverb.set_wet(rw)
        else:
            reverb.set_wet(0.0)

        range_limiter = MIDIRangeLimiter()
        velocity_mapper = VelocityMappingManager()
        master_bus = MasterBus.from_audio_config(config)
        master_bus.reverb_processor = reverb
        master_bus.attach_event_bus(EVENT_BUS)

        # Drive shared delay line from melody strip when its channel_delay is enabled.
        try:
            mch2 = mixer.get_channel(2)
            if mch2 is not None and bool(getattr(mch2, "delay_enabled", False)):
                master_bus.delay_time_ms = float(getattr(mch2, "delay_time_ms", master_bus.delay_time_ms))
                fb = float(getattr(mch2, "delay_feedback", master_bus.delay_feedback))
                master_bus.delay_feedback = max(0.0, min(0.99, fb))
        except Exception:
            pass

        container = cls(
            config=config,
            sample_rate=sample_rate,
            mixer=mixer,
            master_bus=master_bus,
            reverb=reverb,
            range_limiter=range_limiter,
            velocity_mapper=velocity_mapper,
            event_bus=EVENT_BUS
        )

        logger.info("AudioContainer created successfully")
        return container

    def apply_audio_config(self, config):
        # Live path for `fx <preset>`: syncs RoomReverb RT60/damping/wet and MasterBus
        # return-track + limiter settings from config.audio (see CONFIG._apply_post_process_preset).
        self.config = config
        if self.reverb:
            self.reverb.set_rt60(config.audio.reverb_rt60)
            self.reverb.set_damping(config.audio.reverb_damping)
            if hasattr(self.reverb, "set_predelay_ms"):
                self.reverb.set_predelay_ms(float(getattr(config.audio, "reverb_predelay_ms", 28.0) or 28.0))
            if hasattr(self.reverb, "set_early_reflections"):
                self.reverb.set_early_reflections(
                    enabled=bool(getattr(config.audio, "reverb_early_reflections_enabled", True)),
                    level=float(getattr(config.audio, "reverb_early_reflections_level", 0.24) or 0.24),
                )
            if hasattr(self.reverb, "set_return_lowpass"):
                self.reverb.set_return_lowpass(
                    float(getattr(config.audio, "reverb_return_lowpass_hz", 9500.0) or 9500.0),
                    float(getattr(config.audio, "reverb_return_lowpass_slope_db_per_oct", 12.0) or 12.0),
                )
            if hasattr(self.reverb, "set_return_highpass"):
                self.reverb.set_return_highpass(
                    float(getattr(config.audio, "reverb_return_highpass_hz", 500.0) or 500.0),
                    float(getattr(config.audio, "reverb_return_highpass_slope_db_per_oct", 12.0) or 12.0),
                )
            en = bool(getattr(config.audio, "reverb_enabled", True))
            if not en and melody_wants_shared_reverb_aux(config.audio):
                try:
                    config.audio.reverb_enabled = True
                    en = True
                except Exception:
                    pass
            try:
                rw = float(getattr(config.audio, "reverb_wet", 0.5))
            except Exception:
                rw = 0.5
            self.reverb.set_wet(rw if en else 0.0)
        if self.master_bus is not None:
            self.master_bus.configure_from_audio_config(config)

    def get_parameters(self, channel: int, velocity: int) -> dict:
        """Get all synthesis parameters for a channel at given velocity."""
        if self.velocity_mapper:
            channel_names = {0: 'bass', 1: 'chords', 2: 'melody', 3: 'arp', 4: 'harmony'}
            channel_name = channel_names.get(channel)
            if channel_name is None:
                return {}
            return self.velocity_mapper.get_parameters(channel_name, velocity)
        return {}

    def reset(self):
        """Reset all audio components to initial state."""
        logger.info("Resetting AudioContainer")
        if self.mixer:
            self.mixer.reset_all_filters()
        logger.info("AudioContainer reset complete")


# Global container instance
_global_container: Optional[AudioContainer] = None

def get_audio_container() -> Optional[AudioContainer]:
    return _global_container

def set_audio_container(container: AudioContainer):
    global _global_container
    _global_container = container
    logger.info("Global AudioContainer set")
