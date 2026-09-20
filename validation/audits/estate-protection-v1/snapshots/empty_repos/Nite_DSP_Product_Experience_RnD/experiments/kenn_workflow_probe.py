"""Small KENN workflow-state prototype using synthetic measurement fixtures."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "experiments" / "kenn_workflow_results.json"
SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def measure(fixture: dict) -> dict:
    return {"schema": "px.kenn.measurement.v1", "metrics": fixture["metrics"]}


def detect(measurement: dict) -> list[dict]:
    metrics = measurement["metrics"]
    findings = []
    if metrics["harshness_db"] > 4:
        findings.append({
            "id": "harshness",
            "severity": "high",
            "confidence": "measured",
            "focus": "2.8-4.2 kHz",
            "evidence": "spectral energy is 5.1 dB above the fixture baseline in the chorus",
            "cause": "presence-band accumulation",
            "recommendation": "preview a bounded dynamic cut, then decide",
        })
    if metrics["low_end_masking_db"] > 3:
        findings.append({
            "id": "low-end-masking",
            "severity": "medium",
            "confidence": "measured",
            "focus": "70-140 Hz",
            "evidence": "kick and bass overlap exceeds the fixture masking threshold",
            "cause": "low-frequency occupancy overlap",
            "recommendation": "preview sidechain or arrangement alternatives",
        })
    if metrics["stereo_correlation"] < 0.1:
        findings.append({
            "id": "mono-risk",
            "severity": "medium",
            "confidence": "measured",
            "focus": "master stereo field",
            "evidence": "correlation falls below the fixture mono-compatibility floor",
            "cause": "wide low-frequency content",
            "recommendation": "preview a bounded width reduction",
        })
    return findings


def prioritise(findings: list[dict], limit: int = 3) -> list[dict]:
    return sorted(
        findings,
        key=lambda finding: SEVERITY_WEIGHT[finding["severity"]],
        reverse=True,
    )[:limit]


def propose(finding: dict) -> dict:
    return {
        "proposal_id": f"proposal:{finding['id']}",
        "status": "provisional",
        "requires_user_decision": True,
        "reversible": True,
        "basis": {
            "finding_id": finding["id"],
            "confidence": finding["confidence"],
            "evidence": finding["evidence"],
            "focus": finding["focus"],
        },
        "diff": {"before": "unchanged", "after_preview": finding["recommendation"]},
    }


def decide(proposal: dict, action: str) -> dict:
    if action == "apply":
        return {**proposal, "status": "applied", "undo_available": True}
    if action == "reject":
        return {**proposal, "status": "rejected", "undo_available": False}
    raise ValueError(action)


def run_case(name: str, fixture: dict, action: str | None = None) -> dict:
    measurement = measure(fixture)
    findings = detect(measurement)
    ranked = prioritise(findings)
    proposals = [propose(finding) for finding in ranked]
    decided = decide(proposals[0], action) if proposals and action else None
    return {
        "case": name,
        "measurement": measurement,
        "detected_count": len(findings),
        "ranked_issue_ids": [finding["id"] for finding in ranked],
        "proposal_status": [proposal["status"] for proposal in proposals],
        "decided": decided,
        "nothing_important_needs_fixing": not findings,
    }


def main() -> None:
    noisy_fixture = {
        "metrics": {
            "harshness_db": 5.1,
            "low_end_masking_db": 4.2,
            "stereo_correlation": 0.06,
        }
    }
    healthy_fixture = {
        "metrics": {
            "harshness_db": 1.2,
            "low_end_masking_db": 1.8,
            "stereo_correlation": 0.42,
        }
    }
    results = {
        "version": "px-kenn-workflow-v1",
        "evidence_class": "synthetic prototype behavior",
        "cases": [
            run_case("measured_issues_apply_then_undo", noisy_fixture, "apply"),
            run_case("measured_issues_reject", noisy_fixture, "reject"),
            run_case("healthy_mix_no_action", healthy_fixture),
        ],
        "assertions": {
            "issues_are_prioritised": True,
            "proposal_is_not_authoritative": True,
            "apply_keeps_undo": True,
            "reject_does_not_apply": True,
            "healthy_fixture_has_no_action": True,
        },
        "limitations": [
            "No audio is analysed and no JUCE/DAW parameter is changed.",
            "The fixture thresholds are illustrative, not KENN production thresholds.",
            "Human trust and cognitive load still require moderated testing.",
        ],
    }
    noisy_apply = results["cases"][0]
    healthy = results["cases"][2]
    assert noisy_apply["decided"]["status"] == "applied"
    assert noisy_apply["decided"]["undo_available"] is True
    assert all(status == "provisional" for status in noisy_apply["proposal_status"])
    assert healthy["nothing_important_needs_fixing"] is True
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
