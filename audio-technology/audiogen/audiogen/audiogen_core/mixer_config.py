from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# Strips: bass, chords, melody, arp, drone, counter_melody, chorus kick (no MIDI/sampler).
AUDIO_MIXER_CHANNEL_COUNT: int = 7
KICK_MIXER_CHANNEL_INDEX: int = 6


@dataclass
class ChorusKickSidechainConfig:
    """
    Chorus-role 4/4 kick + envelope-follower duck on all strips except drone and kick.
    By default uses ``sample_path`` (WAV one-shot); falls back to procedural if missing.

    ``enabled`` gates the whole block for matching arrangement roles. When enabled, use
    ``kick_enabled`` / ``sidechain_enabled`` to omit the kick stem, the pump, or both. If the
    kick is off but sidechain is on, ducking still follows the same 4/4 (no kick in the mix).
    """

    enabled: bool = True
    # Output the 4/4 kick to the dedicated mixer strip (channel ``mixer_channel``).
    kick_enabled: bool = True
    # Apply envelope-follower ducking to non-drone / non-kick stems.
    sidechain_enabled: bool = True
    roles: Tuple[str, ...] = ("b", "chorus", "hook", "tag")
    beats_per_bar: int = 4
    kick_level_linear: float = 0.32
    kick_pulse_ms: float = 14.0
    attack_ms: float = 1.0
    release_ms: float = 12.0
    threshold_db: float = -32.0
    max_depth: float = 0.52
    drone_channel: int = 4
    # On chorus kicks, duck relief for counter melody only (0 = full duck like other stems;
    # 1 = counter fully ignores kick duck). Helps the second line stay audible under pumping.
    counter_melody_sidechain_relief: float = 0.44
    sample_enabled: bool = True
    sample_path: str = "samples/kick.wav"
    sample_max_ms: float = 450.0
    # Dry stem index for the synthesized/sample kick (routed like other strips).
    mixer_channel: int = KICK_MIXER_CHANNEL_INDEX


@dataclass
class MixerStripConfig:

    volume: float = 1.0
    pan: float = 0.0
    reverb_send: float = 0.0
    delay_send: float = 0.0
    distortion_send: float = 0.0

    # DAW controls
    mute: bool = False
    solo: bool = False
    # Routing (bus name). Minimal bus model: default is master.
    output_bus: str = "master"
    # Sends staging: if True, all sends use pre-fader signal (post-pan/EQ).
    sends_pre_fader: bool = False
    # Ableton-like per-send staging (None => inherit from sends_pre_fader).
    reverb_send_pre_fader: Optional[bool] = None
    delay_send_pre_fader: Optional[bool] = None
    distortion_send_pre_fader: Optional[bool] = None

    # Per-strip tone filters (Wwise-style channel authoring).
    # 0 Hz disables that side of the filter; low-pass values above Nyquist are bypassed at runtime.
    filter_enabled: bool = True
    highpass_hz: float = 0.0
    lowpass_hz: float = 0.0
    filter_slope_db_per_oct: float = 12.0


CHANNEL_NAMES: Dict[int, str] = {
    0: "bass",
    1: "chords",
    2: "melody",
    3: "arp",
    4: "drone",
    5: "counter_melody",
    6: "kick",
}


def _db_to_gain(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def default_mixer_strips() -> Dict[int, MixerStripConfig]:
    """
    Default mixer layout using dB-style authoring for channel volumes.

    0 dB corresponds to unity gain (1.0). Negative values attenuate the channel:
    e.g. -12 dB ≈ 0.25, -15 dB ≈ 0.18.
    """

    # Authoring-time dB values for clarity (all musical strips + chorus kick). Converted via _db_to_gain.
    bass_db = -6.0
    chords_db = -9.0
    melody_db = -9.0
    arp_db = -12.0
    drone_db = -18.0
    # Previously −20 dB (far below lead at −9); lift toward arp territory so counter reads in the mix.
    counter_melody_db = -12.5
    chorus_kick_db = -10.0

    # Default: all sends are POST-fader (Ableton "Post").
    _post = dict(
        sends_pre_fader=False,
        reverb_send_pre_fader=False,
        distortion_send_pre_fader=False,
    )

    return {
        # bass
        0: MixerStripConfig(
            **_post,
            volume=_db_to_gain(bass_db),
            pan=0.00,
            reverb_send=0.00,
            delay_send=0.00,
            delay_send_pre_fader=False,
            distortion_send=0.00,
            highpass_hz=30.0,
            lowpass_hz=12000.0,
        ),
        # chords (-15 dB)
        1: MixerStripConfig(
            **_post,
            volume=_db_to_gain(chords_db),
            pan=-0.12,
            reverb_send=0.90,
            delay_send=0.82,
            delay_send_pre_fader=False,
            distortion_send=0.00,
            highpass_hz=70.0,
            lowpass_hz=14000.0,
        ),
        # melody (-12 dB)
        2: MixerStripConfig(
            **_post,
            volume=_db_to_gain(melody_db),
            pan=0.10,
            reverb_send=0.90,
            delay_send=0.82,
            # Important: keep dry melody balanced (post-fader),
            # but make the delay send audible even when the melody fader is low.
            delay_send_pre_fader=False,
            distortion_send=0.00,
            highpass_hz=90.0,
            lowpass_hz=16000.0,
        ),
        # arp
        3: MixerStripConfig(
            **_post,
            volume=_db_to_gain(arp_db),
            pan=0.00,
            reverb_send=0.90,
            delay_send=0.82,
            delay_send_pre_fader=False,
            distortion_send=0.00,
            highpass_hz=120.0,
            lowpass_hz=14000.0,
        ),
        # drone
        4: MixerStripConfig(
            **_post,
            volume=_db_to_gain(drone_db),
            pan=0.00,
            reverb_send=0.33,
            delay_send=0.00,
            delay_send_pre_fader=False,
            distortion_send=0.00,
            highpass_hz=200.0,
            lowpass_hz=7000.0,
        ),
        # counter melody (second line; slightly softer than lead)
        5: MixerStripConfig(
            **_post,
            volume=_db_to_gain(counter_melody_db),
            pan=-0.08,
            reverb_send=0.90,
            delay_send=0.52,
            delay_send_pre_fader=False,
            distortion_send=0.00,
            highpass_hz=100.0,
            lowpass_hz=15000.0,
        ),
        # chorus kick (filled by renderer on chorus roles; silent otherwise)
        6: MixerStripConfig(
            **_post,
            volume=_db_to_gain(chorus_kick_db),
            pan=0.00,
            reverb_send=0.06,
            delay_send=0.00,
            delay_send_pre_fader=False,
            distortion_send=0.00,
            highpass_hz=0.0,
            lowpass_hz=7000.0,
        ),
    }
