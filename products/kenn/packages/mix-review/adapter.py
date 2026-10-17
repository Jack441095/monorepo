"""Local-only Mix Review adapter.

Default engine: the KENN-owned analyzer in ``core/local_engine.py``, with an
optional NumPy accelerator and a Python standard-library fallback. This module
has no runtime dependency on any external ``Audio_Too`` checkout and runs
standalone from this repository alone.

The opt-in ``KENN_MIX_REVIEW_ENGINE=audio_too_legacy`` parity engine was removed
with Audio_Too on 17 Oct 2026; the C++ analysis path replaced it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


SERVICE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_ROOT.parents[1]
RUNTIME_DIR = Path(
    os.environ.get("KENN_MIX_REVIEW_RUNTIME_DIR", str(Path(tempfile.gettempdir()) / "nite-kenn-mix-review"))
).expanduser().resolve()
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

from core import MixReviewBoundary  # noqa: E402
from core.local_engine import (  # noqa: E402
    DECODABLE_SUFFIXES,
    DEFAULT_MIX_GOAL,
    MAX_UPLOAD_BYTES,
)
from core.local_engine import analyze_wav as engine_analyze_wav  # noqa: E402
from core.local_engine import validate_wav_upload as engine_validate_wav_upload  # noqa: E402

ENGINE_NAME = "kenn-owned mix-review/core/local_engine.py (no external dependency)"

BOUNDARY = MixReviewBoundary(
    product_root=SERVICE_ROOT,
    runtime_root=RUNTIME_DIR,
    max_upload_bytes=MAX_UPLOAD_BYTES,
    decodable_suffixes=frozenset(DECODABLE_SUFFIXES),
)


def analyze_local_path(
    path: Path,
    *,
    mix_goal: str = DEFAULT_MIX_GOAL,
    light: bool = False,
    include_bands: bool = True,
) -> dict[str, Any]:
    """Analyse one local audio file and return a product-owned receipt.

    The original bytes are held only for the duration of the engine call. A
    SHA-256 source fingerprint is retained in the returned receipt so later
    evidence can be associated without retaining audio content.
    """
    receipt = BOUNDARY.analyze_path(
        path,
        validate=lambda payload, filename: engine_validate_wav_upload(
            payload, filename, label="Local mix"
        ),
        analyze=engine_analyze_wav,
        mix_goal=mix_goal,
        light=light,
        include_bands=include_bands,
    )
    receipt["engine"] = ENGINE_NAME
    if receipt.get("status") == "completed":
        # Keep the historical fault-family report stable while attaching the
        # newer KENN-owned spectral contract.  Audio is read for this second
        # deterministic analysis only; the boundary still stores only the
        # source hash and report metadata.
        try:
            source_root = REPO_ROOT / "apps" / "backend" / "src"
            if str(source_root) not in sys.path:
                sys.path.insert(0, str(source_root))
            from kenn.core.audio_analysis import analyze_wav as analyze_spectral_wav
            receipt["analysis"]["spectral_evidence"] = analyze_spectral_wav(
                path.expanduser().resolve().read_bytes(), filename=path.name
            )
        except Exception as exc:
            receipt["analysis"]["spectral_evidence"] = {
                "schema": "kenn.audio_analysis.result.v1",
                "ok": False,
                "analysis_status": "error",
                "error": f"Spectral analysis unavailable: {type(exc).__name__}: {exc}",
            }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Local audio file to analyse")
    parser.add_argument("--mix-goal", default=DEFAULT_MIX_GOAL)
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--no-bands", action="store_true")
    args = parser.parse_args()
    receipt = analyze_local_path(
        args.path,
        mix_goal=args.mix_goal,
        light=args.light,
        include_bands=not args.no_bands,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return 0 if receipt["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
