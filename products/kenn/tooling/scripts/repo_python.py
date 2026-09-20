"""Minimal KENN-owned replacement for the old monorepo's shared ``repo_python`` module.

The original implementation lived in the NITE DSP umbrella repository and
resolved a shared virtualenv interpreter across sibling products. This
standalone repository has no such umbrella venv, so this simply returns the
interpreter currently running -- the correct standalone behaviour is to use
whatever Python environment the caller has already activated.
"""

from __future__ import annotations

import sys


def python_executable() -> str:
    return sys.executable
