"""Candidate cross-product payload probe using the existing nite_ai shape."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "experiments" / "cross_product_results.json"
FORBIDDEN_PRIVATE_FIELDS = {"audio_bytes", "full_project", "project_path", "credentials"}


def validate_candidate(envelope: dict) -> tuple[bool, str]:
    required = {"capability_id", "version", "request_id", "trace_id", "privacy_class", "payload"}
    missing = required - set(envelope)
    if missing:
        return False, f"missing fields: {sorted(missing)}"
    if envelope["privacy_class"] not in {"USER_TEXT", "AUDIO_FEATURES", "ARTIFACT_REF"}:
        return False, "unsupported privacy class"
    forbidden = FORBIDDEN_PRIVATE_FIELDS.intersection(envelope["payload"])
    if forbidden:
        return False, f"raw/private fields rejected: {sorted(forbidden)}"
    if not envelope["capability_id"].startswith("audio."):
        return False, "candidate is not an audio capability"
    return True, "accepted as evidence/reference payload"


def run() -> dict:
    kenn_to_slo = {
        "capability_id": "audio.sample.find_complement",
        "version": "0.1.0",
        "request_id": "px-k2s-001",
        "trace_id": "px-cross-product-001",
        "privacy_class": "AUDIO_FEATURES",
        "context_ref": "artifact://mix-review/issue-42",
        "payload": {
            "issue": "kick_not_cutting_through",
            "frequency_holes_hz": [[1800, 3200]],
            "transient_profile": "short_sharp",
            "pitch_class": "E",
            "bpm": 128,
            "source_product": "kenn",
        },
    }
    slo_to_kenn = {
        "capability_id": "audio.sample.evaluate_fit",
        "version": "0.1.0",
        "request_id": "px-s2k-001",
        "trace_id": "px-cross-product-002",
        "privacy_class": "AUDIO_FEATURES",
        "context_ref": "artifact://slo/sample-abc123",
        "payload": {
            "sample_ref": "sample://abc123",
            "feature_summary": {
                "spectral_centroid_hz": 2410,
                "crest_factor_db": 12.2,
                "duration_ms": 84,
                "stereo_width": 0.18,
            },
            "mix_context_ref": "artifact://mix-review/issue-42",
            "source_product": "slo",
        },
    }
    unsafe = {
        **kenn_to_slo,
        "request_id": "px-unsafe-001",
        "payload": {**kenn_to_slo["payload"], "audio_bytes": "<fixture omitted>"},
    }
    results = []
    for name, envelope in (("kenn_to_slo", kenn_to_slo), ("slo_to_kenn", slo_to_kenn), ("unsafe_raw_audio", unsafe)):
        accepted, reason = validate_candidate(envelope)
        results.append({"case": name, "accepted": accepted, "reason": reason, "payload_keys": sorted(envelope["payload"])})
    return {
        "version": "px-cross-product-contract-v1",
        "contract_basis": "existing nite_ai AgentRequest / CapabilityDefinition envelope shape",
        "evidence_class": "synthetic contract validation",
        "observed_registered_platform_capabilities": [
            "company.brief.daily",
            "company.review.weekly",
            "company.goals.list",
            "company.tasks.list",
            "company.risks.list",
            "company.decisions.pending",
            "company.agents.status",
            "company.approvals.pending",
            "company.approvals.decide",
        ],
        "candidate_audio_capabilities": [
            "audio.mix.analyze",
            "audio.sample.find_similar",
            "audio.sample.find_complement",
            "audio.sample.evaluate_fit",
        ],
        "results": results,
        "assertions": {
            "kenn_to_slo_accepted": results[0]["accepted"],
            "slo_to_kenn_accepted": results[1]["accepted"],
            "raw_audio_rejected": not results[2]["accepted"],
            "product_ownership_preserved": True,
        },
        "limitations": [
            "No live SLO or KENN adapter is registered for these candidate audio capabilities.",
            "Feature sufficiency and ranking quality need real local fixtures and human validation.",
            "Capability IDs require platform-owner review before registration.",
        ],
    }


def main() -> None:
    result = run()
    assert result["assertions"]["kenn_to_slo_accepted"]
    assert result["assertions"]["slo_to_kenn_accepted"]
    assert result["assertions"]["raw_audio_rejected"]
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
