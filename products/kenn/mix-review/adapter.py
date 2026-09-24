"""Local-only Mix Review adapter around the preserved Audio_Too engine.

This module deliberately accepts a local path rather than exposing an HTTP
upload API. It decodes audio through the real product decoder
(``audio_analysis.utils.audio_io_api.decode_audio_bytes``) without copying or
modifying Audio_Too's source, then runs only the three fault detectors that
carry real qualification evidence (see ``qualified_detectors.py``). Every
other fault type the underlying engine can compute (masking, phase, dynamics,
arrangement, ...) is deliberately excluded from this receipt: it has no
precision/recall evidence and must not be presented as a finding in the beta.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


SERVICE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_ROOT.parents[2]
AUDIO_TOO_ROOT = Path(
    os.environ.get("KENN_AUDIO_TOO_ROOT", str(REPO_ROOT / "Audio_Too"))
).expanduser().resolve()
RUNTIME_DIR = Path(
    os.environ.get("KENN_MIX_REVIEW_RUNTIME_DIR", str(SERVICE_ROOT / ".runtime"))
).expanduser().resolve()

if not AUDIO_TOO_ROOT.is_dir():
    raise RuntimeError(f"Audio_Too checkout not found at {AUDIO_TOO_ROOT}")

# These are import paths only. The engine checkout remains read-only.
for import_root in (
    AUDIO_TOO_ROOT,
    AUDIO_TOO_ROOT / "studio",
    AUDIO_TOO_ROOT / "studio" / "audio_analysis",
    AUDIO_TOO_ROOT / "business" / "app",
    AUDIO_TOO_ROOT / "server" / "app",  # Audio_Too's business/app after the Sept 2026 restructure
    REPO_ROOT / "shared",  # nite_core, imported by Audio_Too's server/app since the restructure
):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("AUDIO_TOO_MIX_REVIEW_DATA_ROOT", str(RUNTIME_DIR / "mix-review-data"))

from audio_analysis.mix_review.mix_review import (  # noqa: E402
    validate_wav_upload as engine_validate_wav_upload,
)
from audio_analysis.mix_review.mix_review_config import (  # noqa: E402
    DECODABLE_SUFFIXES,
    MAX_UPLOAD_BYTES,
)
from audio_analysis.utils.audio_io_api import (  # noqa: E402
    decode_audio_bytes as engine_decode_audio_bytes,
)

from qualified_detectors import (  # noqa: E402
    ANALYSIS_VERSION,
    GATE_VERSION,
    QUALIFIED_FAULT_FAMILIES,
    GateAction,
    evaluate_qualified_families,
)


SCHEMA = "kenn.mix_review.local_receipt.v2"
QUALIFICATION_REPORT = "products/kenn-evaluation/reports/KENN_V2D_FINAL_REPORT.md"
DETECTOR_PROVENANCE = (
    "products/kenn/mix-review/qualified_detectors.py "
    "(promoted from products/kenn-evaluation/benchmark/measured_candidates_v2c.py "
    "+ recommendation_gate.py @ kenn-evaluation 7f76f620d9185d0f913e577dbfa2af8012529509)"
)

_EXPLANATIONS: dict[str, dict[str, str]] = {
    "clipping": {
        "explanation": "Sample values reach or exceed full scale with flat-topped waveform plateaus, which is audible digital distortion.",
        "next_step": "Reduce the level feeding this stage (input gain, fader, or a limiter with more headroom) and re-render, then re-analyze to confirm the plateaus are gone.",
    },
    "headroom": {
        "explanation": "Peak level leaves little margin below full scale for further processing or mastering.",
        "next_step": "If this is a mix-in-progress bus rather than a final master, consider leaving more headroom (commonly 6 dB or more) before the next mastering or loudness-normalization stage, then re-analyze.",
    },
    "lr_imbalance": {
        "explanation": "Left and right channels show a persistent, mix-wide energy difference rather than an intentional-sounding momentary pan move.",
        "next_step": "Check master-bus panning, dual-mono sources, and any stereo-widening or imaging processing for an unintended offset, then re-analyze.",
    },
}

_ACTION_TO_STATUS = {
    GateAction.RECOMMEND: "finding",
    GateAction.STRONG_RECOMMEND: "finding",
    GateAction.OBSERVE: "observed_not_actionable",
    GateAction.ABSTAIN: "no_issue_detected",
}


def _base_receipt(path: Path, *, status: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "receipt_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "beta_scope": "kenn_mix_review_beta_v1",
        "qualified_fault_families": list(QUALIFIED_FAULT_FAMILIES),
        "human_qualified": False,
        "source": {
            "filename": path.name,
            "sha256": "",
        },
        "audio_uploaded": False,
        "external_network": False,
        "storage": "memory_only",
        "runtime_dir": str(RUNTIME_DIR),
        "provenance": {
            "engine_decoder": "Audio_Too/studio/audio_analysis/audio_analysis/utils/audio_io_api.py::decode_audio_bytes",
            "detector_source": DETECTOR_PROVENANCE,
            "analysis_version": ANALYSIS_VERSION,
            "gate_version": GATE_VERSION,
            "qualification_report": QUALIFICATION_REPORT,
        },
    }


def _pcm_to_float(frames: bytes, sampwidth: int, channels: int) -> np.ndarray:
    if sampwidth == 1:
        pcm = (np.frombuffer(frames, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif sampwidth == 2:
        pcm = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32767.0
    elif sampwidth == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
        as_int = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        as_int[as_int >= (1 << 23)] -= 1 << 24
        pcm = as_int.astype(np.float64) / float(1 << 23)
    else:
        raise ValueError(f"unsupported PCM sample width for the qualified analysis path: {sampwidth * 8}-bit")
    return pcm.reshape(-1, channels)


def _decode_to_pcm(file_bytes: bytes, filename: str) -> tuple[np.ndarray, int, str]:
    decoded = engine_decode_audio_bytes(file_bytes, filename)
    with wave.open(io.BytesIO(decoded["wav_bytes"]), "rb") as w:
        frames = w.readframes(w.getnframes())
        sample_rate = w.getframerate()
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
    if channels not in (1, 2):
        raise ValueError(f"unsupported channel count for the qualified analysis path: {channels}")
    audio = _pcm_to_float(frames, sampwidth, channels)
    if channels == 1:
        audio = np.repeat(audio, 2, axis=1)
    return audio, sample_rate, decoded.get("decoder", "unknown")


def analyze_local_path(
    path: Path,
    *,
    scope: str = "unknown",
) -> dict[str, Any]:
    """Analyse one local audio file for the three qualified fault families.

    ``scope`` should be ``"mix_in_progress"`` for a bus still being mixed
    (not yet mastered), ``"master"`` for a final master, or ``"unknown"``
    (default). Headroom is only ever reported as an actionable finding when
    ``scope="mix_in_progress"`` — this mirrors the qualified gate's own
    behaviour and is not a beta-only restriction.
    """
    resolved = path.expanduser().resolve()
    receipt = _base_receipt(resolved, status="rejected")
    if scope not in ("mix_in_progress", "master", "unknown"):
        receipt["error"] = "scope must be one of: mix_in_progress, master, unknown"
        return receipt
    if not resolved.is_file():
        receipt["error"] = "Local audio path is not a file."
        return receipt
    if resolved.suffix.lower() not in DECODABLE_SUFFIXES:
        receipt["error"] = "File extension is not a supported audio format."
        return receipt
    if resolved.stat().st_size > MAX_UPLOAD_BYTES:
        receipt["error"] = "Local audio file exceeds the Mix Review size limit."
        return receipt

    file_bytes = resolved.read_bytes()
    receipt["source"]["sha256"] = hashlib.sha256(file_bytes).hexdigest()
    validation = engine_validate_wav_upload(file_bytes, resolved.name, label="Local mix")
    if not validation.get("ok"):
        receipt["error"] = str(validation.get("error") or "Audio validation failed.")
        return receipt

    try:
        audio, sample_rate, decoder = _decode_to_pcm(file_bytes, resolved.name)
    except Exception as exc:  # surfaced as a failed receipt, never as success
        receipt["status"] = "failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        return receipt

    receipt["input"] = {
        "sample_rate": sample_rate,
        "channels": 2,
        "duration_seconds": round(len(audio) / sample_rate, 3) if sample_rate else None,
        "decoder": decoder,
        "scope": scope,
    }

    try:
        results = evaluate_qualified_families(audio, sample_rate, scope=scope)
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        return receipt

    findings = []
    for candidate, decision in results:
        template = _EXPLANATIONS[candidate.issue_type]
        is_finding = decision.action in (GateAction.RECOMMEND, GateAction.STRONG_RECOMMEND)
        # OBSERVE/ABSTAIN can be driven by the gate's scope/persistence
        # overrides rather than the measured score, so the gate's own reason
        # text is used for anything short of a real finding — using the
        # "problem" template there would misrepresent why it was surfaced.
        findings.append(
            {
                "fault_family": candidate.issue_type,
                "status": _ACTION_TO_STATUS[decision.action],
                "recommendation_state": decision.state.value,
                "severity": candidate.severity,
                "confidence_bucket": candidate.confidence_bucket,
                "confidence_kind": candidate.confidence_kind,
                "score": round(candidate.score, 4),
                "measured_value": candidate.measured_value,
                "unit": candidate.unit,
                "evidence": candidate.evidence,
                "affected_channels": list(candidate.affected_channels),
                "explanation": template["explanation"] if is_finding else decision.reason,
                "suggested_next_step": template["next_step"] if is_finding else None,
                "limitations": list(candidate.limitations),
                "gate_reason": decision.reason,
            }
        )

    receipt["status"] = "completed"
    receipt["findings"] = findings
    receipt["unqualified_scope_note"] = (
        "Only clipping, headroom, and persistent L/R imbalance are qualified with "
        "measured precision/recall evidence. No other fault type was checked or is "
        "represented in this receipt."
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Local audio file to analyse")
    parser.add_argument(
        "--scope",
        choices=("mix_in_progress", "master", "unknown"),
        default="unknown",
        help="Whether this file is a mix-in-progress bus or a final master; affects headroom significance.",
    )
    args = parser.parse_args()
    receipt = analyze_local_path(args.path, scope=args.scope)
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return 0 if receipt["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
