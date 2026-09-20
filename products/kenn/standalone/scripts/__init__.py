"""Compatibility import path for KENN tooling.

New code should import ``tooling.scripts``. This shim keeps older extensions
and tests using ``scripts.<module>`` working after the workspace reorganisation.
"""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[1] / "tooling" / "scripts")]
