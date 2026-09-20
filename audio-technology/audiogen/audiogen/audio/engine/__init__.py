# audio/engine/__init__.py
# Package marker for `audio`.

# audio/engine/__init__.py
from .event_bus import EventBus
from .mixer import AudioMixer, MixerChannel
from .master_bus import MasterBus, MasterBusSettings, lookahead_limiter_mono_gain

# Create a global event bus instance
EVENT_BUS = EventBus()

# Do NOT import LIMITER, REVERB, or SAMPLE_RATE – they are removed.
# The audio container provides mixer, etc.

__all__ = [
    'EventBus',
    'MixerChannel',
    'AudioMixer',
    'MasterBus',
    'MasterBusSettings',
    'lookahead_limiter_mono_gain',
    'EVENT_BUS',
]