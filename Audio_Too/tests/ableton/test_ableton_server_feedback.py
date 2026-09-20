"""Tests for standalone Audio Tips LLM feedback capture."""

from __future__ import annotations

import sys
from pathlib import Path
from io import BytesIO

LM = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM))

import server  # noqa: E402


class FakeHandler:
    def __init__(self) -> None:
        self.status = 0
        self.payload = {}
        self.headers = {}
        self.rfile = BytesIO()

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def test_main_chat_feedback_records_channel(monkeypatch) -> None:
    saved = {}

    class FakeFeedback:
        @staticmethod
        def record_feedback(payload: dict) -> dict:
            saved.update(payload)
            return {"id": "fb1", **payload}

    monkeypatch.setattr(server, "demo_feedback", FakeFeedback)
    handler = FakeHandler()

    server.Handler.handle_feedback(
        handler,
        {
            "question": "How do I fix muddy vocals?",
            "rating": "not_useful",
            "comment": "Wrong topic",
        },
    )

    assert handler.status == 201
    assert handler.payload["ok"] is True
    assert saved["channel"] == "main_chat"
    assert saved["rating"] == "not_useful"


def test_main_chat_feedback_rejects_unknown_rating(monkeypatch) -> None:
    class FakeFeedback:
        @staticmethod
        def record_feedback(_payload: dict) -> dict:
            raise AssertionError("should not record invalid ratings")

    monkeypatch.setattr(server, "demo_feedback", FakeFeedback)
    handler = FakeHandler()

    server.Handler.handle_feedback(handler, {"rating": "maybe"})

    assert handler.status == 400
    assert "rating" in handler.payload["error"]


def test_mix_review_rejects_non_multipart(monkeypatch) -> None:
    class FakeMixReview:
        MAX_UPLOAD_BYTES = 100

    monkeypatch.setattr(server, "mix_review", FakeMixReview)
    handler = FakeHandler()
    handler.headers = {"Content-Type": "application/json", "Content-Length": "2"}

    server.Handler.handle_mix_review(handler)

    assert handler.status == 400
    assert "multipart" in handler.payload["error"]


def test_mix_review_uses_shared_analyser(monkeypatch) -> None:
    captured = {}

    class FakeMixReview:
        MAX_UPLOAD_BYTES = 100

        @staticmethod
        def handle_multipart_review(content_type: str, body: bytes, *, project_id_override: str = "") -> dict:
            captured["content_type"] = content_type
            captured["body"] = body
            captured["project_id_override"] = project_id_override
            return {"ok": True, "review": {"summary": "analysis"}}

    monkeypatch.setattr(server, "mix_review", FakeMixReview)
    handler = FakeHandler()
    handler.headers = {"Content-Type": "multipart/form-data; boundary=x", "Content-Length": "4"}
    handler.rfile = BytesIO(b"body")

    server.Handler.handle_mix_review(handler)

    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert captured["body"] == b"body"


def test_mix_review_step_uses_shared_update(monkeypatch) -> None:
    captured = {}

    class FakeMixReview:
        @staticmethod
        def update_revision_agent_step(review_id: str, step_id: str, status: str) -> dict:
            captured["review_id"] = review_id
            captured["step_id"] = step_id
            captured["status"] = status
            return {"ok": True, "revision_agent": {"done_count": 1}}

    monkeypatch.setattr(server, "mix_review", FakeMixReview)
    handler = FakeHandler()

    server.Handler.handle_mix_review_step(
        handler,
        {"review_id": "rev1", "step_id": "step-1", "status": "done"},
    )

    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert captured == {"review_id": "rev1", "step_id": "step-1", "status": "done"}


def test_mix_review_context_turn_compacts_payload() -> None:
    turn = server.mix_review_context_turn(
        {
            "title": "Client Mix v2",
            "summary": "Low mids are heavy and crest factor is low.",
            "technical_score": 68,
            "crest_factor_db": 5.2,
            "dominant_band": "low_mids",
            "flags": ["low-mid buildup", "low crest factor"],
            "actions": ["Tighten kick and bass", "Ease limiter drive"],
            "previous_version": {"version_label": "v1", "created_at": "2026-06-07 10:00:00"},
            "version_comparison": {
                "rms_delta_db": -1.2,
                "crest_delta_db": 1.8,
                "stereo_width_delta": 0.04,
                "largest_spectral_difference": {"band": "presence", "delta": 0.08},
            },
            "version_advice": ["Dynamics increased compared with the previous version."],
            "revision_impact": {
                "verdict": "improved",
                "improvements": ["Crest factor increased, so the mix may have regained punch."],
                "regressions": ["New flag appeared: Low presence."],
                "checks": ["1 previous checklist step(s) were marked done before this revision."],
            },
            "reference_filename": "commercial-reference.wav",
            "reference_comparison": {
                "rms_delta_db": -2.4,
                "crest_delta_db": 1.1,
                "stereo_width_delta": -0.08,
                "largest_spectral_difference": {"band": "low_mids", "delta_db": 3.6},
            },
            "comparison_advice": ["Pull low mids down before limiting."],
            "revision_agent": {
                "goal": "Create the next focused revision for Client Mix v2.",
                "steps": [
                    {
                        "focus": "Low-mid cleanup",
                        "action": "Cut muddy low mids before pushing the limiter again.",
                    }
                ],
            },
        }
    )

    assert turn is not None
    assert turn["role"] == "user"
    assert "Mix Review Lab context for Client Mix v2" in turn["content"]
    assert "crest factor db=5.2" in turn["content"]
    assert "low-mid buildup" in turn["content"]
    assert "Previous version: v1" in turn["content"]
    assert "largest version spectral change=presence" in turn["content"]
    assert "Dynamics increased compared with the previous version." in turn["content"]
    assert "Revision impact verdict: improved" in turn["content"]
    assert "Crest factor increased" in turn["content"]
    assert "New flag appeared: Low presence." in turn["content"]
    assert "Reference WAV: commercial-reference.wav" in turn["content"]
    assert "largest spectral difference=low_mids" in turn["content"]
    assert "Pull low mids down before limiting." in turn["content"]
    assert "Revision agent goal: Create the next focused revision for Client Mix v2." in turn["content"]
    assert "Cut muddy low mids before pushing the limiter again." in turn["content"]


def test_mix_review_context_turn_accepts_structured_handoff() -> None:
    turn = server.mix_review_context_turn(
        {
            "schema": "kenn_mix_review_handoff.v1",
            "title": "Structured Mix",
            "context_lines": [
                "Mix Review Lab context for Structured Mix.",
                "Summary: Solid with checks.",
            ],
            "metrics": {"technical_score": 72, "crest_factor_db": 4.8},
            "technical_metrics": {"peak_dbfs": -2.1, "true_peak_dbfs": -1.8, "crest_factor_db": 4.8},
            "judgment": {"technical_score": 72, "summary": "Needs dynamics work."},
            "section_highlights": {
                "loudest_section": {"label": "Section 2", "rms_dbfs": -12.4},
                "lowest_correlation_section": {"label": "Section 3", "stereo_correlation": 0.12},
            },
            "flags": [{"severity": "medium", "label": "Low dynamics", "detail": "Crest is low.", "confidence": "medium"}],
            "priority_actions": [
                {
                    "rank": 1,
                    "decision": "fix_first",
                    "confidence": "medium",
                    "focus": "Low dynamics",
                    "action": "Ease the limiter.",
                }
            ],
            "ableton_repair_templates": [
                {
                    "flag": "Low dynamics",
                    "device_chain": "Glue Compressor or Limiter",
                    "move": "Back off threshold.",
                }
            ],
            "revision_steps": [{"focus": "Export", "action": "Re-export the next version."}],
            "reference": {"filename": "ref.wav", "comparison": {"rms_delta_db": -2.1}},
            "next_revision_plan": {
                "focus": "Remaining flag to address: Low dynamics.",
                "steps": [{"focus": "Dynamics", "action": "Reduce limiter input by 2 dB."}],
                "checks": ["Level-match v1 and v2."],
            },
        }
    )

    assert turn is not None
    assert turn["role"] == "user"
    assert "Use this structured uploaded-track analysis" in turn["content"]
    assert "technical score=72" in turn["content"]
    assert "#1 fix_first (medium confidence) Low dynamics" in turn["content"]
    assert "Structured judgment" in turn["content"]
    assert "Objective technical metrics" in turn["content"]
    assert "Structured section highlights" in turn["content"]
    assert "Low dynamics" in turn["content"]
    assert "Ease the limiter." in turn["content"]
    assert "Glue Compressor or Limiter" in turn["content"]
    assert "Structured next revision focus" in turn["content"]
    assert "Reduce limiter input by 2 dB" in turn["content"]
    assert "ref.wav" in turn["content"]
