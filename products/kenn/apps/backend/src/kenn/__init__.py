"""KENN audio-engineering assistant package.

Import concrete APIs from ``KENN.core``, ``KENN.retrieval``, ``KENN.llm``, or
``KENN.training``. Keeping the root package lightweight prevents optional local
model dependencies from loading during deterministic and Website imports.
"""

from __future__ import annotations
