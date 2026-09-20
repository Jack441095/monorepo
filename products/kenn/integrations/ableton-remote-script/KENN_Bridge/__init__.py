"""Ableton Live 12 Remote Script Initialization for KENN_Bridge.

This package defines the Remote Script entrypoint for Ableton Live 12.
"""

from __future__ import annotations

from .KENN_Bridge import KENN_Bridge


def create_instance(c_instance):
    """Factory method called by Ableton Live to instantiate the Remote Script."""
    return KENN_Bridge(c_instance)
