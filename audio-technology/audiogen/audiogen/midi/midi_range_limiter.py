# midi/midi_range_limiter.py
# Project module `midi_range_limiter` (midi).

# midi_range_limiter.py - MIDI Note Range Constraints

#./////// ////////////////////////////////////////////////////////////
# This module defines a MIDIRangeLimiter class that manages MIDI note range constraints for different channels (bass, chords, melody, drone/harmony).
# It allows for clamping MIDI notes to specified ranges, applying octave shifts if necessary,
# and provides presets for different emotional profiles.
# that can be applied to the range configurations. This ensures that generated MIDI notes fit within the 
# playable and musically appropriate ranges for each channel, 
# while also allowing for emotional expression through range adjustments.  

import random
import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ChannelRangeConfig:
    """MIDI range configuration for a channel"""
    name: str
    min_note: int  # Minimum MIDI note (inclusive)
    max_note: int  # Maximum MIDI note (inclusive)
    preferred_min: int  # Preferred minimum (for random generation)
    preferred_max: int  # Preferred maximum (for random generation)
    octave_shift_allowed: bool = True  # Can we shift by octaves to fit range?
    
    def clamp_note(self, note: int) -> int:
        """Clamp a note to the allowed range"""
        if self.octave_shift_allowed:
            # Shift by octaves until in range
            while note < self.min_note:
                note += 12
            while note > self.max_note:
                note -= 12
        
        # Final clamp
        return max(self.min_note, min(self.max_note, note))
    
    def clamp_notes(self, notes: List[int]) -> List[int]:
        """Clamp all notes in a list"""
        return [self.clamp_note(note) for note in notes]
    
    def get_random_octave_offset(self) -> int:
        """Get random octave offset within preferred range"""
        # Calculate which octaves fit within preferred range
        base_note = 60  # Middle C
        octave_offsets = []
        
        for offset in [-36, -24, -12, 0, 12, 24, 36]:
            test_note = base_note + offset
            if self.preferred_min <= test_note <= self.preferred_max:
                octave_offsets.append(offset)
        
        return random.choice(octave_offsets) if octave_offsets else 0

class MIDIRangeLimiter:
    """Manage MIDI range limits for all channels"""
    
    # Standard MIDI note reference
    # C-1=0, C0=12, C1=24, C2=36, C3=48, C4=60, C5=72, C6=84, C7=96, C8=108
    
    def __init__(self):
        """Initialize with sensible defaults"""
        self.configs = {
            # Bass: Low range (E1-C3)
            0: ChannelRangeConfig(
                name="bass",
                min_note=33,   # A1
                max_note=48,   # C3
                preferred_min=36,  # C2
                preferred_max=44   # G#2
            ),
            
            # Chords: Mid range (C2-C5)
            1: ChannelRangeConfig(
                name="chords",
                # Raise the floor slightly so neutral pads don't feel subby/muddy.
                min_note=48,   # C3
                max_note=84,   # C7
                preferred_min=55,  # G3
                preferred_max=78     # G6
            ),
            
            # Melody: Mid-high range (C4-C6)
            2: ChannelRangeConfig(
                name="melody",
                min_note=60,   # C4 (Middle C)
                max_note=88,   # E6
                preferred_min=60, # E4
                preferred_max=81   # A5
            ),

            # Arp: stable mid-high register (G3-C6). Keep narrower than melody to avoid runaway highs.
            3: ChannelRangeConfig(
                name="arp",
                min_note=55,   # G3
                # Cap at E5 by default (closer to reference renders; avoids glassy top).
                max_note=76,   # E5
                preferred_min=60,  # C4
                preferred_max=74,  # D5
            ),
            
            # Harmony: Similar to chords but slightly higher (C3-C5)
            4: ChannelRangeConfig(
                name="harmony",
                min_note=48,   # C3
                max_note=72,   # C5
                preferred_min=52,  # E3
                preferred_max=67   # G4
            ),

            # Counter-melody: same ballpark as lead, slightly narrower top.
            5: ChannelRangeConfig(
                name="counter_melody",
                min_note=58,   # A#3
                max_note=86,   # D6
                preferred_min=60,
                preferred_max=79,
            ),
        }
        self.default_configs = deepcopy(self.configs)
        self._lock = threading.Lock()
    
    def set_channel_range(self, channel: int, min_note: int, max_note: int,
                         preferred_min: int = None, preferred_max: int = None):
        """Set custom range for a channel (thread-safe)"""
        with self._lock:
            if channel in self.configs:
                self.configs[channel].min_note = min_note
                self.configs[channel].max_note = max_note
                if preferred_min is not None:
                    self.configs[channel].preferred_min = preferred_min
                if preferred_max is not None:
                    self.configs[channel].preferred_max = preferred_max

    def reset_to_defaults(self):
        """Restore all channel ranges to their default values."""
        with self._lock:
            self.configs = deepcopy(self.default_configs)
    
    def clamp_note(self, note: int, channel: int) -> int:
        """Clamp a single note to channel's range (thread-safe)"""
        with self._lock:
            if channel in self.configs:
                return self.configs[channel].clamp_note(note)
        return note
    
    def clamp_notes(self, notes: List[int], channel: int) -> List[int]:
        """Clamp all notes to channel's range (thread-safe)"""
        with self._lock:
            if channel in self.configs:
                return self.configs[channel].clamp_notes(notes)
        return notes
    
    def get_preferred_octave_offset(self, channel: int) -> int:
        """Get random octave offset for this channel's preferred range (thread-safe)"""
        with self._lock:
            if channel in self.configs:
                return self.configs[channel].get_random_octave_offset()
        return 0
    
    def get_range_info(self, channel: int) -> Dict:
        """Get range information for a channel (thread-safe)"""
        with self._lock:
            if channel not in self.configs:
                return {}
            config = self.configs[channel]
            return {
                'name': config.name,
                'min_note': config.min_note,
                'max_note': config.max_note,
                'min_note_name': self._note_to_name(config.min_note),
                'max_note_name': self._note_to_name(config.max_note),
                'preferred_min': config.preferred_min,
                'preferred_max': config.preferred_max,
                'range_octaves': (config.max_note - config.min_note) / 12
            }
    
    def get_all_ranges(self) -> Dict[int, Dict]:
        """Get range info for all channels (thread-safe)"""
        with self._lock:
            return {ch: self.get_range_info(ch) for ch in self.configs.keys()}
    
    @staticmethod
    def _note_to_name(midi_note: int) -> str:
        """Convert MIDI note number to name (e.g., C4, G#5)"""
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi_note // 12) - 1
        note_name = note_names[midi_note % 12]
        return f"{note_name}{octave}"
    
    @staticmethod
    def note_name_to_midi(note_name: str) -> int:
        """Convert note name to MIDI number (e.g., 'C4' -> 60)"""
        note_names = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5,
                     'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
        
        # Parse note name
        if len(note_name) >= 2:
            if note_name[1] == '#':
                note = note_names.get(note_name[:2], 0)
                octave = int(note_name[2:]) if len(note_name) > 2 else 4
            else:
                note = note_names.get(note_name[0], 0)
                octave = int(note_name[1:]) if len(note_name) > 1 else 4
            
            return (octave + 1) * 12 + note
        return 60  # Default to middle C

# Emotion-specific range presets
EMOTION_RANGE_PRESETS = {
    "admiration": {
        0: (33, 48),
        1: (50, 72),
        2: (62, 84),
        3: (55, 79),  # keep arp warm/steady
    },
    "amusement": {
        0: (33, 48),
        1: (52, 76),
        2: (64, 88),
    },
    "approval": {
        0: (33, 48),
        1: (50, 72),
        2: (62, 84),
    },
    "caring": {
        0: (33, 45),
        1: (45, 62),
        2: (62, 84),
    },
    "confusion": {
        0: (33, 48),
        1: (48, 72),
        2: (60, 84),
    },
    "curiosity": {
        0: (33, 48),
        1: (50, 74),
        2: (64, 86),
    },
    "desire": {
        0: (33, 48),
        1: (48, 70),
        2: (62, 82),
    },
    # Darker emotions: keep chord pads below ~D4; lead sits D4+ to avoid masking.
    "sadness": {
        0: (33, 44),
        1: (43, 58),
        2: (62, 84),
    },
    "grief": {
        0: (33, 40),
        1: (40, 56),
        2: (62, 82),
    },
    "disappointment": {
        0: (33, 45),
        1: (42, 58),
        2: (62, 84),
    },
    "remorse": {
        0: (33, 44),
        1: (42, 57),
        2: (62, 82),
    },
    "relief": {
        0: (33, 45),
        1: (45, 62),
        2: (62, 81),
    },
    
    # Brighter, higher emotions
    "joy": {
        0: (32, 48),   # Bass: G#1-C3 (normal)
        1: (52, 76),   # Chords: E3-E5 (bright)
        2: (64, 88),   # Melody: E4-E6 (high, bright)
    },
    "excitement": {
        0: (32, 48),   # Bass: G#1-C3
        1: (55, 79),   # Chords: G3-G5 (higher)
        2: (67, 88),   # Melody: G4-E6 (very high!)
    },
    "gratitude": {
        0: (33, 48),
        1: (50, 72),
        2: (62, 82),
    },
    "optimism": {
        0: (33, 48),
        1: (52, 76),
        2: (64, 86),
        3: (55, 76),
    },
    "pride": {
        0: (33, 48),
        1: (52, 76),
        2: (64, 86),
    },
    "surprise": {
        0: (33, 48),
        1: (52, 76),
        2: (65, 88),
    },
    
    # Moderate emotions
    "calm": {
        0: (33, 44),   # Bass: A1-G#2
        1: (48, 67),   # Chords: C3-G4 (moderate)
        2: (60, 79),   # Melody: C4-G5 (moderate)
    },
    "love": {
        0: (32, 48),   # Bass: G#1-C3
        1: (50, 70),   # Chords: D3-A#4 (warm)
        2: (62, 81),   # Melody: D4-A5 (sweet)
    },
    "embarrassment": {
        0: (33, 45),
        1: (48, 67),
        2: (60, 79),
    },
    "neutral": {
        0: (33, 48),
        1: (36, 72),
        2: (60, 88),
        3: (55, 76),
    },
    "realization": {
        0: (33, 46),
        1: (48, 69),
        2: (60, 81),
    },
    
    # Tense emotions
    "anger": {
        0: (33, 40),   # Bass: A1-E2 (aggressive low)
        1: (45, 69),   # Chords: A2-A4 (punchy)
        2: (60, 84),   # Melody: C4-C6 (wide range)
    },
    "fear": {
        0: (33, 48),   # Bass: A1-C3
        1: (52, 76),   # Chords: E3-E5 (tense)
        2: (67, 88),   # Melody: G4-E6 (high, anxious)
    },
    "annoyance": {
        0: (33, 44),
        1: (45, 69),
        2: (60, 82),
    },
    "disapproval": {
        0: (33, 44),
        1: (45, 69),
        2: (60, 82),
    },
    "disgust": {
        0: (33, 44),
        1: (45, 68),
        2: (59, 81),
    },
    "nervousness": {
        0: (33, 46),
        1: (48, 72),
        2: (64, 86),
    },
}

def apply_emotion_ranges(limiter: MIDIRangeLimiter, emotion_name: str):
    """Apply emotion-specific range preset to limiter"""
    limiter.reset_to_defaults()
    emotion_name_lower = emotion_name.lower()
    
    if emotion_name_lower in EMOTION_RANGE_PRESETS:
        preset = EMOTION_RANGE_PRESETS[emotion_name_lower]
        for channel, (min_note, max_note) in preset.items():
            # Calculate preferred range (middle 70% of range)
            range_size = max_note - min_note
            preferred_min = min_note + int(range_size * 0.15)
            preferred_max = max_note - int(range_size * 0.15)
            
            limiter.set_channel_range(
                channel, 
                min_note, 
                max_note,
                preferred_min,
                preferred_max
            )
        return True
    return False

# Global instance
RANGE_LIMITER = MIDIRangeLimiter()
