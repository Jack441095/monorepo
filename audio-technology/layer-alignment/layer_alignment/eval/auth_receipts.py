"""Authorisation receipts for Real-Audio Validation V1 (workspace-side).

Receipts live in the R&D workspace and REFERENCE the read-only source
paths. Nothing is written inside the source trees.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_receipts(import_root: Path) -> list[Path]:
    import_root.mkdir(parents=True, exist_ok=True)
    common = {
        "owner_authorised": True,
        "authorised_by": "owner",
        "use": "LOCAL INTERNAL R&D VALIDATION",
        "scope": "NITE DSP Layer Alignment Real-Audio Validation V1 "
                 "(frozen engine LAYER_ALIGNMENT_FROZEN_ENGINE_V1)",
        "source_audio_modification": "FORBIDDEN",
        "source_audio_redistribution": "FORBIDDEN",
        "source_audio_commit_push": "FORBIDDEN",
        "external_upload": "FORBIDDEN",
        "commercial_redistribution_rights_claimed": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    receipts = []
    specs = [
        ("sample_pack_testing",
         "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/"
         "Audio_Too/sample_pack_testing"),
        ("testing_track_stems",
         "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/"
         "Audio_Too/testing_track_stems"),
    ]
    for name, path in specs:
        doc = {"receipt_id": f"AUTH-{name}",
               "source_path": path,
               "source_treated_read_only": True,
               **common}
        p = import_root / f"LICENCE_{name}.json"
        p.write_text(json.dumps(doc, indent=1))
        receipts.append(p)
    return receipts
