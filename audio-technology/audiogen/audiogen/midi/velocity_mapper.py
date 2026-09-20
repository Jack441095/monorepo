# midi/velocity_mapper.py
# Project module `velocity_mapper` (midi).

# velocity_mapper.py
# Velocity Mapping System for MIDI Parameters
# This module provides a flexible system to map MIDI velocity (0-127) to various synthesis parameters like amplitude,
# filter cutoff, resonance, and attack time. Each channel can have
# its own unique mapping curves and ranges, allowing for expressive and dynamic performances.

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass
class VelocityMapping:
    """Configuration for how velocity maps to a parameter"""
    min_value: float        # Parameter value at velocity 0
    max_value: float        # Parameter value at velocity 127
    curve: str = 'linear'   # 'linear', 'exponential', 'logarithmic', 'sigmoid'
    exponent: float = 2.0   # For exponential/power curves
    enabled: bool = True    # Can be disabled per channel
    
    def map(self, velocity: int) -> float:
        """Map velocity (0-127) to parameter value"""
        if not self.enabled:
            # Return neutral mid-range value when bypassed, not an extreme
            return (self.min_value + self.max_value) / 2.0
        
        # Normalize velocity to 0.0-1.0
        vel_norm = np.clip(velocity / 127.0, 0.0, 1.0)
        
        # Apply curve
        if self.curve == 'linear':
            scaled = vel_norm
        elif self.curve == 'exponential':
            # y = x^n where n > 1 gives exponential response
            scaled = vel_norm ** self.exponent
        elif self.curve == 'logarithmic':
            # y = log(1 + k*x) / log(1 + k) for k > 0
            k = 9.0  # Adjustable curve steepness
            scaled = np.log(1 + k * vel_norm) / np.log(1 + k)
        elif self.curve == 'sigmoid':
            # S-curve for natural dynamic response
            # Maps 0-1 input to 0-1 output with smooth acceleration
            x = (vel_norm - 0.5) * 6  # Center and scale
            scaled = 1.0 / (1.0 + np.exp(-x))
            # Normalize to 0-1 range
            scaled = (scaled - 1.0/(1.0 + np.exp(3))) / (1.0/(1.0 + np.exp(-3)) - 1.0/(1.0 + np.exp(3)))
        else:
            scaled = vel_norm
        
        # Map to parameter range
        return self.min_value + (self.max_value - self.min_value) * scaled


class ChannelVelocityMapper:
    """Manages velocity mappings for a single channel"""
    
    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        
        # Default mappings for different parameters
        self.amplitude = VelocityMapping(
            min_value=0.0,
            max_value=1.0,
            curve='exponential',
            exponent=2.0,  # Exponential feels more natural for volume
            enabled=True
        )
        
        self.filter_cutoff = VelocityMapping(
            min_value=200.0,   # Hz - dark/muted
            max_value=8000.0,  # Hz - bright/open
            curve='exponential',
            exponent=2.5,      # Steep curve for dramatic filter sweep
            enabled=True
        )
        
        self.filter_resonance = VelocityMapping(
            min_value=0.1,
            max_value=0.9,
            curve='linear',
            enabled=False  # Off by default
        )
        
        self.attack_time = VelocityMapping(
            min_value=0.05,   # Seconds - fast attack
            max_value=0.001,  # Seconds - instant attack (inverted!)
            curve='exponential',
            exponent=1.5,
            enabled=False  # Off by default
        )
    
    def get_amplitude(self, velocity: int) -> float:
        """Get amplitude multiplier for this velocity"""
        return self.amplitude.map(velocity)
    
    def get_filter_cutoff(self, velocity: int) -> float:
        """Get filter cutoff frequency for this velocity"""
        return self.filter_cutoff.map(velocity)
    
    def get_filter_resonance(self, velocity: int) -> float:
        """Get filter resonance for this velocity"""
        return self.filter_resonance.map(velocity)
    
    def get_attack_time(self, velocity: int) -> float:
        """Get attack time for this velocity"""
        return self.attack_time.map(velocity)


class VelocityMappingManager:
    """Global manager for all channel velocity mappings"""
    
    def __init__(self):
        self.channels: Dict[str, ChannelVelocityMapper] = {
            'bass': ChannelVelocityMapper('bass'),
            'chords': ChannelVelocityMapper('chords'),
            'melody': ChannelVelocityMapper('melody'),
            'arp': ChannelVelocityMapper('arp'),
            'harmony': ChannelVelocityMapper('harmony'),
            'drone': ChannelVelocityMapper('drone'),
            'counter_melody': ChannelVelocityMapper('counter_melody'),
        }
        
        # Set up sensible defaults per channel
        self._configure_defaults()
    
    def _configure_defaults(self):
        """Configure sensible default mappings per channel"""
        
        # BASS - No velocity variation for consistency
        self.channels['bass'].amplitude.enabled = False
        self.channels['bass'].amplitude.min_value = 1.0
        self.channels['bass'].amplitude.max_value = 1.0
        
        self.channels['bass'].filter_cutoff.enabled = False
        self.channels['bass'].filter_cutoff.min_value = 8000.0
        self.channels['bass'].filter_cutoff.max_value = 8000.0
        
        self.channels['bass'].filter_resonance.enabled = False
        self.channels['bass'].filter_resonance.min_value = 0.0
        self.channels['bass'].filter_resonance.max_value = 0.0
        
        self.channels['bass'].attack_time.enabled = False
        self.channels['bass'].attack_time.min_value = 0.01
        self.channels['bass'].attack_time.max_value = 0.01
        
        # CHORDS - Subtle amplitude, wide filter range
        # Keep chords present even at medium velocities (power curves can get too quiet).
        self.channels['chords'].amplitude.curve = 'sigmoid'
        self.channels['chords'].amplitude.min_value = 0.45
        self.channels['chords'].amplitude.max_value = 1.0
        self.channels['chords'].amplitude.exponent = 1.6
        self.channels['chords'].filter_cutoff.min_value = 300.0
        self.channels['chords'].filter_cutoff.max_value = 8000.0
        self.channels['chords'].filter_cutoff.exponent = 2.5
        
        # MELODY - Very expressive, wide dynamic range
        # Ensure the lead is audible at typical velocities (60-100).
        self.channels['melody'].amplitude.curve = 'sigmoid'
        self.channels['melody'].amplitude.min_value = 0.50
        self.channels['melody'].amplitude.max_value = 1.0
        self.channels['melody'].amplitude.exponent = 1.8
        self.channels['melody'].filter_cutoff.min_value = 400.0
        self.channels['melody'].filter_cutoff.max_value = 10000.0
        self.channels['melody'].filter_cutoff.exponent = 3.0  # Dramatic filter sweep

        # COUNTER MELODY - second line; close to lead but slightly tighter floor.
        self.channels['counter_melody'].amplitude.curve = 'sigmoid'
        self.channels['counter_melody'].amplitude.min_value = 0.48
        self.channels['counter_melody'].amplitude.max_value = 1.0
        self.channels['counter_melody'].amplitude.exponent = 1.75
        self.channels['counter_melody'].filter_cutoff.min_value = 400.0
        self.channels['counter_melody'].filter_cutoff.max_value = 9800.0
        self.channels['counter_melody'].filter_cutoff.exponent = 2.9

        # ARP - Similar to melody but slightly less dynamic (stable bed).
        self.channels['arp'].amplitude.curve = 'sigmoid'
        self.channels['arp'].amplitude.min_value = 0.48
        self.channels['arp'].amplitude.max_value = 1.0
        self.channels['arp'].amplitude.exponent = 1.7
        self.channels['arp'].filter_cutoff.min_value = 450.0
        self.channels['arp'].filter_cutoff.max_value = 9500.0
        self.channels['arp'].filter_cutoff.exponent = 2.8
        
        # HARMONY - Similar to chords but gentler
        self.channels['harmony'].amplitude.curve = 'sigmoid'
        self.channels['harmony'].amplitude.min_value = 0.40
        self.channels['harmony'].amplitude.max_value = 1.0
        self.channels['harmony'].amplitude.exponent = 1.6
        self.channels['harmony'].filter_cutoff.min_value = 300.0
        self.channels['harmony'].filter_cutoff.max_value = 6000.0
        self.channels['harmony'].filter_cutoff.exponent = 2.0

        # DRONE - Almost no velocity dynamics; keep stable bed level.
        self.channels['drone'].amplitude.enabled = False
        self.channels['drone'].amplitude.min_value = 0.85
        self.channels['drone'].amplitude.max_value = 0.85
        self.channels['drone'].filter_cutoff.enabled = False
        self.channels['drone'].filter_cutoff.min_value = 6000.0
        self.channels['drone'].filter_cutoff.max_value = 6000.0
        self.channels['drone'].filter_resonance.enabled = False
        self.channels['drone'].attack_time.enabled = False
    
    def get_channel(self, channel_name: str) -> ChannelVelocityMapper:
        """Get velocity mapper for a channel"""
        if channel_name not in self.channels:
            # Create on-demand if doesn't exist
            self.channels[channel_name] = ChannelVelocityMapper(channel_name)
        return self.channels[channel_name]
    
    def get_parameters(self, channel_name: str, velocity: int) -> Dict[str, float]:
        """Get all parameters for a channel at given velocity"""
        mapper = self.get_channel(channel_name)
        return {
            'amplitude': mapper.get_amplitude(velocity),
            'filter_cutoff': mapper.get_filter_cutoff(velocity),
            'filter_resonance': mapper.get_filter_resonance(velocity),
            'attack_time': mapper.get_attack_time(velocity),
        }
    
    def configure_amplitude(self, channel: str, min_value: float = 0.0, 
                           max_value: float = 1.0, curve: str = 'exponential',
                           exponent: float = 2.0, enabled: bool = True):
        """Configure amplitude mapping for a channel"""
        mapper = self.get_channel(channel)
        mapper.amplitude.min_value = min_value
        mapper.amplitude.max_value = max_value
        mapper.amplitude.curve = curve
        mapper.amplitude.exponent = exponent
        mapper.amplitude.enabled = enabled
    
    def configure_filter(self, channel: str, min_cutoff: float = 200.0,
                        max_cutoff: float = 8000.0, curve: str = 'exponential',
                        exponent: float = 2.5, enabled: bool = True):
        """Configure filter cutoff mapping for a channel"""
        mapper = self.get_channel(channel)
        mapper.filter_cutoff.min_value = min_cutoff
        mapper.filter_cutoff.max_value = max_cutoff
        mapper.filter_cutoff.curve = curve
        mapper.filter_cutoff.exponent = exponent
        mapper.filter_cutoff.enabled = enabled
    
    def print_mapping_curves(self, channel: str):
        """Print how velocity maps to parameters for debugging"""
        print(f"\n{channel.upper()} - Velocity Mapping Curves:")
        print("=" * 60)
        print(f"{'Vel':<5} {'Amplitude':<12} {'Filter (Hz)':<12}")
        print("-" * 60)
        
        mapper = self.get_channel(channel)
        for vel in [0, 32, 64, 96, 127]:
            amp = mapper.get_amplitude(vel)
            cutoff = mapper.get_filter_cutoff(vel)
            print(f"{vel:<5} {amp:<12.3f} {cutoff:<12.1f}")
        print("=" * 60)


# Global instance
VELOCITY_MAPPER = VelocityMappingManager()


# ============================================================================
# PRESET CONFIGURATIONS
# ============================================================================

def apply_preset_natural():
    """Natural, realistic instrument response"""
    VELOCITY_MAPPER.configure_amplitude('bass', exponent=2.5)
    VELOCITY_MAPPER.configure_amplitude('chords', exponent=2.0)
    VELOCITY_MAPPER.configure_amplitude('melody', curve='sigmoid')
    
    VELOCITY_MAPPER.configure_filter('bass', min_cutoff=100, max_cutoff=2000, exponent=2.0)
    VELOCITY_MAPPER.configure_filter('chords', min_cutoff=300, max_cutoff=8000, exponent=2.5)
    VELOCITY_MAPPER.configure_filter('melody', min_cutoff=400, max_cutoff=10000, exponent=3.0)
    print("Applied 'Natural' velocity preset")


def apply_preset_dramatic():
    """Dramatic, expressive response with wide dynamic range"""
    VELOCITY_MAPPER.configure_amplitude('bass', min_value=0.1, max_value=1.0, exponent=3.0)
    VELOCITY_MAPPER.configure_amplitude('chords', min_value=0.1, max_value=1.0, exponent=2.5)
    VELOCITY_MAPPER.configure_amplitude('melody', min_value=0.05, max_value=1.0, curve='sigmoid')
    
    VELOCITY_MAPPER.configure_filter('bass', min_cutoff=50, max_cutoff=3000, exponent=3.0)
    VELOCITY_MAPPER.configure_filter('chords', min_cutoff=200, max_cutoff=12000, exponent=3.5)
    VELOCITY_MAPPER.configure_filter('melody', min_cutoff=300, max_cutoff=15000, exponent=4.0)
    print("Applied 'Dramatic' velocity preset")


def apply_preset_subtle():
    """Subtle, compressed dynamic range"""
    VELOCITY_MAPPER.configure_amplitude('bass', min_value=0.6, max_value=1.0, exponent=1.5)
    VELOCITY_MAPPER.configure_amplitude('chords', min_value=0.6, max_value=1.0, exponent=1.5)
    VELOCITY_MAPPER.configure_amplitude('melody', min_value=0.5, max_value=1.0, curve='linear')
    
    VELOCITY_MAPPER.configure_filter('bass', min_cutoff=500, max_cutoff=1500, exponent=1.5)
    VELOCITY_MAPPER.configure_filter('chords', min_cutoff=1000, max_cutoff=6000, exponent=2.0)
    VELOCITY_MAPPER.configure_filter('melody', min_cutoff=1000, max_cutoff=8000, exponent=2.0)
    print("Applied 'Subtle' velocity preset")


def apply_preset_electronic():
    """Electronic/synthetic response with extreme filter sweeps"""
    VELOCITY_MAPPER.configure_amplitude('bass', min_value=0.3, max_value=1.0, exponent=2.0)
    VELOCITY_MAPPER.configure_amplitude('chords', min_value=0.3, max_value=1.0, exponent=2.0)
    VELOCITY_MAPPER.configure_amplitude('melody', min_value=0.2, max_value=1.0, exponent=2.0)
    
    VELOCITY_MAPPER.configure_filter('bass', min_cutoff=80, max_cutoff=4000, exponent=4.0)
    VELOCITY_MAPPER.configure_filter('chords', min_cutoff=150, max_cutoff=15000, exponent=4.5)
    VELOCITY_MAPPER.configure_filter('melody', min_cutoff=200, max_cutoff=18000, exponent=5.0)
    print("Applied 'Electronic' velocity preset")