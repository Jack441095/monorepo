import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from contracts import receipt_errors  # noqa: E402
from core import MixReviewBoundary  # noqa: E402


FIXTURE = Path(__file__).parent / "fixtures/mix_review_report_parity_v1.json"


def test_synthetic_report_shape_survives_owned_boundary(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    audio = tmp_path / "synthetic.wav"
    audio.write_bytes(b"synthetic-parity-bytes")
    boundary = MixReviewBoundary(ROOT, tmp_path / "runtime", 1024, frozenset({".wav"}))
    receipt = boundary.analyze_path(
        audio,
        validate=lambda payload, filename: {"ok": True},
        analyze=lambda payload, **options: fixture["analysis"],
    )
    assert receipt_errors(receipt) == []
    assert set(fixture["required_receipt_fields"]).issubset(receipt)
    assert set(fixture["required_analysis_fields"]).issubset(receipt["analysis"])
    assert set(fixture["required_metric_fields"]).issubset(receipt["analysis"]["metrics"])
    assert receipt["analysis"] == fixture["analysis"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    (("analysis", None), ("storage", "disk"), ("external_network", True)),
)
def test_parity_contract_rejects_unsafe_or_missing_fields(field: str, replacement: object) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    receipt = {
        "schema": "kenn.mix_review.local_receipt.v2",
        "status": "completed",
        "source": {"filename": "synthetic.wav", "sha256": "a" * 64},
        "audio_uploaded": False,
        "external_network": False,
        "storage": "memory_only",
        "runtime_dir": "/tmp/nite-kenn-mix-review",
        "analysis": fixture["analysis"],
    }
    receipt[field] = replacement
    assert receipt_errors(receipt)
