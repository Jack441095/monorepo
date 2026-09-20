# core/constants.py
# Project module `constants` (core).

# Centralized constants for the audio generation system

# Allowed note durations (in beats)
DURATIONS = [0.25, 0.5, 1.0, 2.0, 4.0]

# Default sample rate (should be overridden by config)
DEFAULT_SAMPLE_RATE = 44100

# MIDI note range limits
MIDI_MIN = 0
MIDI_MAX = 127

# Default tempo (BPM)
DEFAULT_TEMPO = 70.0

# Beats per bar (default 4/4)
DEFAULT_BEATS_PER_BAR = 4.0