"""Every device Ableton Live 12 Suite ships, by exact browser name.

Generated from the installed app's own device folders (Builtin + Core
Library, minus Legacy and Max for Live pack-ins) on 2026-09-29 with
``python3 tooling/scripts/device_coverage.py`` against Live 12.4.6. We keep a
checked-in copy because CI and most dev machines have no Live install; to
refresh, rerun that script and paste its device list here.

We use this for honest answers, never for writes: a request naming a genuine
stock device that KENN cannot insert yet says exactly that, instead of
pretending the device does not exist or risking AbletonOSC's fuzzy
browser search (which once resolved "Reverb" to "Convolution Reverb" and
"Delay" to "Align Delay" on real Live). Insertion stays gated by
DEVICE_INSERTION_ALLOWLIST in live_action_service.py.
"""

from __future__ import annotations


_INSTRUMENTS = frozenset({
    "Analog",
    "Collision",
    "Drift",
    "Drum Rack",
    "Drum Sampler",
    "Drum Synth",
    "Electric",
    "External Instrument",
    "Impulse",
    "Instrument Rack",
    "Meld",
    "Operator",
    "Sampler",
    "Simpler",
    "Tension",
    "Wavetable",
})
_AUDIO_EFFECTS = frozenset({
    "Align Delay",
    "Amp",
    "Audio Effect Rack",
    "Auto Filter",
    "Auto Pan-Tremolo",
    "Auto Shift",
    "Beat Repeat",
    "Cabinet",
    "Channel EQ",
    "Chorus-Ensemble",
    "Compressor",
    "Corpus",
    "Delay",
    "Drum Buss",
    "Dynamic Tube",
    "EQ Eight",
    "EQ Three",
    "Echo",
    "Envelope Follower",
    "Erosion",
    "External Audio Effect",
    "Filter Delay",
    "Gate",
    "Glue Compressor",
    "Grain Delay",
    "Hybrid Reverb",
    "LFO",
    "Limiter",
    "Looper",
    "Multiband Dynamics",
    "Overdrive",
    "Pedal",
    "Phaser-Flanger",
    "Redux",
    "Resonators",
    "Reverb",
    "Roar",
    "Saturator",
    "Shaper",
    "Shifter",
    "Spectral Resonator",
    "Spectral Time",
    "Spectrum",
    "Tuner",
    "Utility",
    "Vinyl Distortion",
    "Vocoder",
})
_MIDI_EFFECTS = frozenset({
    "Arpeggiator",
    "CC Control",
    "Chord",
    "Envelope MIDI",
    "Expression Control",
    "MIDI Effect Rack",
    "MIDI Monitor",
    "MPE Control",
    "Note Echo",
    "Note Length",
    "Pitch",
    "Random",
    "Scale",
    "Shaper MIDI",
    "Velocity",
})

STOCK_DEVICES: frozenset[str] = _INSTRUMENTS | _AUDIO_EFFECTS | _MIDI_EFFECTS

STOCK_DEVICE_CATEGORIES: dict[str, str] = {
    **{name: "Instruments" for name in _INSTRUMENTS},
    **{name: "Audio Effects" for name in _AUDIO_EFFECTS},
    **{name: "MIDI Effects" for name in _MIDI_EFFECTS},
}


def stock_device_name(value: str | None) -> str | None:
    """Return the exact Live browser name for a case-insensitive match, else None."""
    wanted = str(value or "").strip().casefold()
    if not wanted:
        return None
    for name in STOCK_DEVICES:
        if name.casefold() == wanted:
            return name
    return None


__all__ = ["STOCK_DEVICES", "STOCK_DEVICE_CATEGORIES", "stock_device_name"]
