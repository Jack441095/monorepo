"""Ableton Live 12 Remote Script Initialization for AudioToo_Bridge.

This package defines the Remote Script entrypoint for Ableton Live 12.
"""

from __future__ import annotations

from .AudioToo_Bridge import AudioToo_Bridge


def create_instance(c_instance):
    """Factory method called by Ableton Live to instantiate the Remote Script."""
    return AudioToo_Bridge(c_instance)
