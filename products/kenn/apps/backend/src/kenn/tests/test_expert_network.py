"""Tests for Expert Network knowledge vetting, versioning, and gatekeeping (Milestone E11).

Verifies:
1. Submissions start unvetted in pending_review status with SHA-256 digest.
2. Strict gatekeeper: unvetted or rejected content is NEVER surfaced to producers.
3. Reviewer approval sets vetted=True and makes content surfaced.
4. Content revisions bump the version number, record immutable history, and invalidate prior approval.
5. Content tamper detection: mismatched digest prevents surfacing.
"""

from __future__ import annotations

import json
import sqlite3
import pytest

from kenn.core.expert_network import (
    ExpertContribution,
    ExpertNetworkStore,
    SCHEMA_CONTRIBUTION,
)


@pytest.fixture
def temp_expert_store(tmp_path):
    """Provide an isolated ExpertNetworkStore instance with a clean SQLite DB."""
    db_file = tmp_path / "test_expert_network.sqlite3"
    return ExpertNetworkStore(db_path=db_file)


def test_submit_contribution_starts_unvetted(temp_expert_store):
    """Verify new submissions default to unvetted pending_review with cryptographic digest."""
    store = temp_expert_store

    contrib = store.submit_contribution(
        contributor_name="Al Schmitt",
        credentials="20x Grammy Winner, Capitol Studios",
        content_type="note",
        topic="vocal_presence",
        title="Microphone Placement Over Heavy Equalization",
        content_markdown=(
            "Position the singer 6 to 9 inches (15 to 23 cm) from a large diaphragm condenser "
            "with a pop filter angled at 15 degrees to minimize plosives without needing steep high-pass cuts."
        ),
        target_standards=["HOUSE_RULE"],
    )

    assert contrib["schema"] == SCHEMA_CONTRIBUTION
    assert contrib["vetted"] is False
    assert contrib["vetting_status"] == "pending_review"
    assert contrib["version"] == 1
    assert len(contrib["sha256_digest"]) == 64

    # Strict gatekeeper: pending content must NEVER be surfaced
    surfaced = store.list_surfaced_expert_content()
    assert len(surfaced) == 0


def test_review_approval_and_rejection_gates(temp_expert_store):
    """Verify that only explicitly approved expert contributions pass the surfacing gate."""
    store = temp_expert_store

    c1 = store.submit_contribution(
        contributor_name="Senior Mix Engineer",
        credentials="AES Fellow",
        content_type="lesson",
        topic="low_end_phase",
        title="Phase Alignment on Acoustic Kick and Sub Bass",
        content_markdown=(
            "Always inspect the initial transient waveform of the kick drum and bass guitar. "
            "Aligning the fundamental peaks within 0.5 ms prevents low-end destructive cancellation."
        ),
    )
    c2 = store.submit_contribution(
        contributor_name="Unvetted User",
        credentials="None",
        content_type="note",
        topic="dynamics",
        title="Excessive Limiting Suggestion",
        content_markdown="Just slam the master limiter until the gain reduction meter reads 12 dB permanently.",
    )

    # Approve c1
    reviewed_c1 = store.review_contribution(
        contribution_id=c1["contribution_id"],
        decision="approved",
        reviewer_name="Jack Gandy",
        feedback="Verified against house acoustic standards; excellent transient alignment advice.",
    )
    assert reviewed_c1["vetted"] is True
    assert reviewed_c1["vetting_status"] == "approved"
    assert reviewed_c1["vetted_by"] == "Jack Gandy"

    # Reject c2
    reviewed_c2 = store.review_contribution(
        contribution_id=c2["contribution_id"],
        decision="rejected",
        reviewer_name="Jack Gandy",
        feedback="Violates AES TD1008 and EBU dynamic standards. Dangerous advice.",
    )
    assert reviewed_c2["vetted"] is False
    assert reviewed_c2["vetting_status"] == "rejected"

    # Surfacing check: ONLY approved c1 is returned
    surfaced = store.list_surfaced_expert_content()
    assert len(surfaced) == 1
    assert surfaced[0]["contribution_id"] == c1["contribution_id"]
    assert surfaced[0]["title"] == "Phase Alignment on Acoustic Kick and Sub Bass"

    # Filtered by topic
    assert len(store.list_surfaced_expert_content(topic="low_end_phase")) == 1
    assert len(store.list_surfaced_expert_content(topic="dynamics")) == 0


def test_content_revision_bumps_version_and_resets_vetting(temp_expert_store):
    """Verify that editing an approved contribution resets vetting status until re-approved."""
    store = temp_expert_store

    c = store.submit_contribution(
        contributor_name="Mastering Engineer",
        credentials="AES Member",
        content_type="note",
        topic="spectral_balance",
        title="De-essing Vocal Sibilance",
        content_markdown="Place dynamic notch de-esser at 6.5 kHz with 3.0 dB maximum reduction.",
    )

    store.review_contribution(
        contribution_id=c["contribution_id"],
        decision="approved",
        reviewer_name="Lead Reviewer",
    )
    assert len(store.list_surfaced_expert_content()) == 1

    # Contributor updates content
    updated = store.update_contribution_content(
        contribution_id=c["contribution_id"],
        content_markdown="Place dynamic notch de-esser between 5.5 kHz and 8.0 kHz with 2.5 to 4.0 dB reduction.",
        title="Refined De-essing Vocal Sibilance Guide",
    )

    assert updated["version"] == 2
    assert updated["vetted"] is False
    assert updated["vetting_status"] == "pending_review"

    # Due to reset, content is no longer surfaced
    assert len(store.list_surfaced_expert_content()) == 0

    # History shows both revisions
    history = store.get_contribution_history(c["contribution_id"])
    assert len(history) == 2
    assert history[0]["version"] == 1
    assert history[1]["version"] == 2
    assert history[0]["sha256_digest"] != history[1]["sha256_digest"]


def test_tampered_payload_is_rejected_by_gatekeeper(temp_expert_store):
    """Verify that payload modification without matching digest is rejected by surfacing gate."""
    store = temp_expert_store

    c = store.submit_contribution(
        contributor_name="Legitimate Engineer",
        credentials="Staff Mixer",
        content_type="note",
        topic="general",
        title="Clean Mix Bus Gain Staging",
        content_markdown="Leave at least 6 dB of peak headroom on channel faders prior to master summing.",
    )
    store.review_contribution(
        contribution_id=c["contribution_id"],
        decision="approved",
        reviewer_name="Jack Gandy",
    )
    assert len(store.list_surfaced_expert_content()) == 1

    # Manually tamper with DB content without updating sha256_digest
    conn = store._connect()
    try:
        row = conn.execute(
            "SELECT payload_json FROM expert_contributions WHERE contribution_id = ?",
            (c["contribution_id"],),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["content_markdown"] = "MALICIOUS MODIFICATION: clip everything by +10 dB."
        conn.execute(
            "UPDATE expert_contributions SET payload_json = ? WHERE contribution_id = ?",
            (json.dumps(payload), c["contribution_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    # Integrity verification must catch the discrepancy and refuse to surface
    surfaced = store.list_surfaced_expert_content()
    assert len(surfaced) == 0


def test_expert_network_rest_endpoints(monkeypatch, tmp_path):
    """Verify FastAPI endpoints for Expert Network contribution submission, review, and surfacing."""
    from fastapi.testclient import TestClient
    from kenn.routes.fastapi_app import app

    db_file = tmp_path / "test_expert_rest.sqlite3"
    monkeypatch.setattr("kenn.core.expert_network.DB_PATH", db_file)

    client = TestClient(app)

    # 1. Initially empty
    res = client.get("/api/expert-network/contributions")
    assert res.status_code == 200
    assert len(res.json()["contributions"]) == 0

    # 2. Submit contribution
    submit_payload = {
        "contributor_name": "Bruce Swedien",
        "credentials": "Legendary Recording Engineer (Thriller)",
        "content_type": "note",
        "topic": "stereo_imaging",
        "title": "Early Reflections and Acoustic Space",
        "content_markdown": (
            "Avoid excessive stereo widening plugins that smear natural phase. "
            "Use Blumlein stereo microphone pairs to capture natural acoustic space."
        ),
        "target_standards": ["HOUSE_RULE"],
    }
    res = client.post("/api/expert-network/submit", json=submit_payload)
    assert res.status_code == 201
    cid = res.json()["contribution"]["contribution_id"]
    assert res.json()["contribution"]["vetted"] is False

    # 3. Still not surfaced (unvetted)
    res = client.get("/api/expert-network/contributions")
    assert len(res.json()["contributions"]) == 0

    # 4. Review and approve
    review_payload = {
        "contribution_id": cid,
        "decision": "approved",
        "reviewer_name": "Jack Gandy",
        "feedback": "Seminal stereo imaging practice. Approved for knowledge base.",
    }
    res = client.post("/api/expert-network/review", json=review_payload)
    assert res.status_code == 200
    assert res.json()["contribution"]["vetted"] is True

    # 5. Now surfaced
    res = client.get("/api/expert-network/contributions")
    assert res.status_code == 200
    contributions = res.json()["contributions"]
    assert len(contributions) == 1
    assert contributions[0]["contribution_id"] == cid

    # 6. History lookup
    res = client.get(f"/api/expert-network/history/{cid}")
    assert res.status_code == 200
    history = res.json()["history"]
    assert len(history) == 1
    assert history[0]["version"] == 1

