"""Tests for Thursday Feedback & Learning System (Phase 6)."""


import pytest

from thursday.feedback import (
    record_feedback,
    get_helpfulness_summary,
    get_service_helpfulness,
    get_busiest_hours,
    get_busiest_days,
    get_suggested_sequences,
    get_active_suggestions,
    get_auto_correct,
)
from thursday.bridge import feedback as bridge_feedback


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    """Use a temporary data directory for each test."""
    from thursday import feedback as fb
    monkeypatch.setattr(fb, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fb, "FEEDBACK_LOG", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(fb, "HABITS_FILE", tmp_path / "habits.json")
    monkeypatch.setattr(fb, "PATTERNS_FILE", tmp_path / "patterns.json")
    monkeypatch.setattr(fb, "SUGGESTIONS_FILE", tmp_path / "suggestions.json")
    # Also re-init auto-correct singleton
    monkeypatch.setattr(fb, "_auto_correct", fb.AutoCorrectStore())
    return tmp_path


# ─── Feedback Recording ──────────────────────────────────────────────────


class TestFeedbackRecording:
    def test_record_explicit_thumbs_up(self):
        r = record_feedback(
            turn_id="turn_001",
            session_id="sess_1",
            service_id="business_status",
            intent_name="business_health",
            explicit_rating=1,
            response_text="Business is good",
            user_text="how's business",
        )
        assert r["turn_id"] == "turn_001"
        assert r["explicit_rating"] == 1
        assert r["service_id"] == "business_status"
        assert r["session_id"] == "sess_1"
        assert r["day_of_week"] is not None
        assert r["hour_of_day"] >= 0

    def test_record_explicit_thumbs_down(self):
        r = record_feedback(
            turn_id="turn_002",
            service_id="pipeline",
            explicit_rating=-1,
            dwell_seconds=2.0,
        )
        assert r["explicit_rating"] == -1

    def test_record_implicit_dwell(self):
        r = record_feedback(
            turn_id="turn_003",
            service_id="reminders",
            dwell_seconds=18.0,
            had_followup=True,
            followup_type="continuation",
        )
        assert r["explicit_rating"] is None
        assert r["dwell_seconds"] == 18.0
        assert r["had_followup"] is True

    def test_record_correction_signal(self):
        r = record_feedback(
            turn_id="turn_004",
            service_id="invoices",
            followup_type="correction",
            correction_from="invoices",
            correction_to="pipeline",
            dwell_seconds=1.5,
        )
        assert r["followup_type"] == "correction"


# ─── Helpfulness Analysis ────────────────────────────────────────────────


class TestHelpfulnessAnalysis:
    def test_empty_feedback_returns_empty_summary(self):
        summary = get_helpfulness_summary()
        assert summary["total_records"] == 0

    def test_helpfulness_with_samples(self):
        # Record a mix of good and bad feedback
        for i in range(5):
            record_feedback(turn_id=f"good_{i}", service_id="business_status", explicit_rating=1)
        for i in range(2):
            record_feedback(turn_id=f"bad_{i}", service_id="business_status", explicit_rating=-1)

        summary = get_helpfulness_summary()
        assert summary["total_records"] == 7
        assert summary["thumbs_up"] == 5
        assert summary["thumbs_down"] == 2
        assert summary["thumbs_up_ratio"] == pytest.approx(5 / 7, 0.01)

    def test_service_helpfulness_with_min_samples(self):
        for i in range(3):
            record_feedback(turn_id=f"s1_g{i}", service_id="pipeline", explicit_rating=1)
        for i in range(1):
            record_feedback(turn_id=f"s1_b{i}", service_id="pipeline", explicit_rating=-1)

        result = get_service_helpfulness(min_samples=3)
        assert "pipeline" in result
        assert result["pipeline"] == pytest.approx(3 / 4, 0.01)

    def test_service_helpfulness_insufficient_data(self):
        for i in range(2):
            record_feedback(turn_id=f"insuf_{i}", service_id="rare_service", explicit_rating=1)

        result = get_service_helpfulness(min_samples=3)
        assert "rare_service" not in result

    def test_implicit_signal_scoring_long_dwell(self):
        record_feedback(turn_id="dwell_good", service_id="kenn", dwell_seconds=20.0, followup_type="continuation")
        result = get_service_helpfulness(service_id="kenn", min_samples=1)
        assert result == {"kenn": pytest.approx(0.9, 0.01)}

    def test_implicit_signal_scoring_quick_correction(self):
        record_feedback(turn_id="dwell_bad", service_id="kenn", dwell_seconds=1.0, followup_type="correction")
        result = get_service_helpfulness(service_id="kenn", min_samples=1)
        assert result == {"kenn": pytest.approx(0.1, 0.01)}


# ─── Habit Tracking ──────────────────────────────────────────────────────


class TestHabitTracking:
    def test_habits_update_automatically_on_record(self):
        """Recording feedback should update habits file as a side effect."""
        record_feedback(turn_id="h1", service_id="business_status")
        record_feedback(turn_id="h2", service_id="business_status")
        record_feedback(turn_id="h3", service_id="pipeline")

        busiest = get_busiest_hours()
        assert len(busiest) > 0

    def test_busiest_days(self):
        first = record_feedback(turn_id="d1", service_id="a")
        record_feedback(turn_id="d2", service_id="a")
        record_feedback(turn_id="d3", service_id="b")

        days = get_busiest_days()
        assert days[0][0] == first["day_of_week"]


# ─── Pattern Detection ───────────────────────────────────────────────────


class TestPatternDetection:
    def test_sequence_detection(self):
        """Recording consecutive services in the same session should detect sequences."""
        # Simulate multiple sessions with the same pattern: business_status → pipeline
        for i in range(4):
            sid = f"sess_seq_{i}"
            record_feedback(turn_id=f"sa_{i}_1", session_id=sid, service_id="business_status")
            record_feedback(turn_id=f"sa_{i}_2", session_id=sid, service_id="pipeline")

        sequences = get_suggested_sequences(min_count=3)
        seq_found = any(s["after"] == "business_status" and s["suggest"] == "pipeline" for s in sequences)
        assert seq_found, f"Expected business_status→pipeline sequence, got: {sequences}"

    def test_self_transitions_are_never_suggested_as_sequences(self):
        """Checking the same service twice in a row (e.g. asking KENN two
        questions back to back) must not be recorded as a learned "after X,
        try Y" sequence -- that produced the real bug "After checking kenn,
        you often check kenn." A repeated service is also typically the
        user's most-used one, so an unguarded self-pair reliably out-counts
        every real pattern and dominates the top-10 list."""
        for i in range(6):
            sid = f"sess_self_{i}"
            record_feedback(turn_id=f"sb_{i}_1", session_id=sid, service_id="kenn")
            record_feedback(turn_id=f"sb_{i}_2", session_id=sid, service_id="kenn")
        # A real, distinct pattern mixed in alongside the self-transitions.
        for i in range(3):
            sid = f"sess_real_{i}"
            record_feedback(turn_id=f"sc_{i}_1", session_id=sid, service_id="client_info")
            record_feedback(turn_id=f"sc_{i}_2", session_id=sid, service_id="invoices")

        sequences = get_suggested_sequences(min_count=3)
        assert not any(s["after"] == s["suggest"] for s in sequences), (
            f"Self-transition leaked into suggested sequences: {sequences}"
        )
        assert any(s["after"] == "client_info" and s["suggest"] == "invoices" for s in sequences)


# ─── Auto-Correct Learning ───────────────────────────────────────────────


class TestAutoCorrect:
    def test_learn_and_apply_spelling(self):
        store = get_auto_correct()
        store.learn_spelling("Jorden", "Jordan")
        store.learn_spelling("Jorden", "Jordan")  # Count increment

        result = store.apply_spelling("Tell me about Jorden")
        assert result == "Tell me about Jordan"

    def test_apply_multiple_corrections(self):
        store = get_auto_correct()
        store.learn_spelling("abltn", "Ableton")
        store.learn_spelling("prtool", "Pro Tools")

        result = store.apply_spelling("open abltn and prtool")
        assert result == "open Ableton and Pro Tools"

    def test_intent_override_learning(self):
        store = get_auto_correct()
        store.learn_intent_override("invoices", "pipeline")
        store.learn_intent_override("invoices", "pipeline")

        override = store.get_intent_override("invoices")
        assert override == "pipeline"

        # Low-count override should not override
        no_override = store.get_intent_override("business_status")
        assert no_override is None

    def test_service_preference(self):
        store = get_auto_correct()
        store.learn_service_preference("financial", "expenses_detail")

        pref = store.get_preferred_service("financial")
        assert pref == "expenses_detail"

    def test_to_dict(self):
        store = get_auto_correct()
        store.learn_spelling("tst", "test")
        d = store.to_dict()
        assert "spelling_corrections" in d
        assert d["spelling_corrections"]["tst"]["correction"] == "test"


# ─── Bridge Feedback API ─────────────────────────────────────────────────


class TestBridgeFeedback:
    def test_bridge_feedback_returns_ok(self):
        result = bridge_feedback(turn_id="bridge_turn", rating=1, session_id="bridge_sess")
        assert result["ok"] is True
        assert result["rating"] == 1

    def test_bridge_feedback_thumbs_down(self):
        result = bridge_feedback(turn_id="bridge_turn_2", rating=-1)
        assert result["ok"] is True
        assert result["rating"] == -1


# ─── Suggestion Generation ───────────────────────────────────────────────


class TestSuggestions:
    def test_active_suggestions_returns_list(self):
        """Should return a list (possibly empty) without error."""
        suggestions = get_active_suggestions()
        assert isinstance(suggestions, list)
