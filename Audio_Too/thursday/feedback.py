"""Feedback & Learning System — collects explicit and implicit feedback signals,
trains a lightweight model to predict helpfulness, and feeds into the
personalization layer.

Explicit signals:
  - Thumbs up (+1) / Thumbs down (-1) on responses

Implicit signals:
  - Dwell time on a response (seconds before next user action)
  - Follow-up type (new topic, clarification, correction)
  - Intent override (user rephrased → different service was used)
  - Copy action (user selected text from response)

Stored in Thursday/user_data/feedback.jsonl (append-only log).
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from thursday.runtime_paths import DATA_DIR
FEEDBACK_LOG = DATA_DIR / "feedback.jsonl"
HABITS_FILE = DATA_DIR / "habits.json"
PATTERNS_FILE = DATA_DIR / "patterns.json"
SUGGESTIONS_FILE = DATA_DIR / "suggestions.json"

import fcntl

from thursday.atomic_io import atomic_write


# ─── Feedback Recording ──────────────────────────────────────────────────


def record_feedback(
    *,
    turn_id: str,
    session_id: str = "",
    service_id: str = "",
    intent_name: str = "",
    explicit_rating: int | None = None,  # +1 (thumbs up), -1 (thumbs down), None (implicit only)
    dwell_seconds: float | None = None,
    had_followup: bool = False,
    followup_type: str | None = None,  # "new_topic", "clarification", "correction", "continuation"
    correction_from: str | None = None,  # What service was originally matched
    correction_to: str | None = None,    # What service should have been matched
    response_text: str = "",
    user_text: str = "",
) -> dict:
    """Record a single feedback event (explicit or implicit) to the append-only log.

    Returns the stored record.
    """
    record = {
        "turn_id": turn_id,
        "session_id": session_id,
        "service_id": service_id,
        "intent_name": intent_name,
        "explicit_rating": explicit_rating,
        "dwell_seconds": dwell_seconds,
        "had_followup": had_followup,
        "followup_type": followup_type,
        "correction_from": correction_from,
        "correction_to": correction_to,
        "response_text_snippet": response_text[:200] if response_text else "",
        "user_text_snippet": user_text[:200] if user_text else "",
        "timestamp": datetime.now().isoformat(),
        "day_of_week": datetime.now().strftime("%A"),
        "hour_of_day": datetime.now().hour,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(json.dumps(record) + "\n")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass

    # Update habits & patterns in memory
    _update_habits(record)
    _detect_patterns()
    _generate_suggestions()

    return record


# ─── Feedback Analysis ────────────────────────────────────────────────────


def _load_feedback(limit: int = 1000) -> list[dict]:
    """Load the last N feedback entries from the append-only log."""
    if not FEEDBACK_LOG.exists():
        return []

    records = []
    try:
        with FEEDBACK_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass

    return records[-limit:]


def get_service_helpfulness(
    service_id: str | None = None, min_samples: int = 3
) -> dict[str, float]:
    """Get helpfulness scores aggregated by service.

    Helpfulness = ratio of positive signals (explicit thumbs up or implicit
    signal indicating satisfaction) to total signals with a clear outcome.

    Args:
        service_id: If provided, return only for this service.
        min_samples: Minimum number of feedback entries to report a score.

    Returns:
        Dict mapping service_id → helpfulness ratio (0.0–1.0) or
        {"error": "insufficient_data"}.
    """
    records = _load_feedback()
    service_signals: dict[str, list[float]] = {}

    for r in records:
        sid = r.get("service_id", "")
        if service_id and sid != service_id:
            continue
        if not sid:
            continue

        signal = _compute_signal_score(r)
        if signal is not None:
            service_signals.setdefault(sid, []).append(signal)

    result = {}
    for sid, signals in service_signals.items():
        if len(signals) < min_samples:
            continue
        result[sid] = round(sum(signals) / len(signals), 3)

    return result


def _compute_signal_score(record: dict) -> float | None:
    """Compute a helpfulness score [0, 1] from a feedback record.

    Returns None if the record has no useful signal.
    """
    rating = record.get("explicit_rating")

    # Explicit rating is strongest signal
    if rating == 1:
        return 1.0
    if rating == -1:
        return 0.0

    # Implicit signals
    dwell = record.get("dwell_seconds")
    followup_type = record.get("followup_type")

    # Dwell-based signals
    if dwell is not None:
        if dwell > 15.0 and followup_type == "continuation":
            return 0.9  # Read the response, then continued the topic
        if dwell > 8.0 and not followup_type:
            return 0.8  # Read the response, no follow-up needed
        if dwell > 15.0 and followup_type == "new_topic":
            return 0.7  # Finished reading, moved on
        if dwell < 3.0 and followup_type == "correction":
            return 0.1  # Quick dismiss + correction
        if dwell < 2.0 and followup_type == "clarification":
            return 0.3  # Quick response wasn't enough

    # Correction signals
    if followup_type == "correction":
        return 0.15

    return None  # No clear signal


def get_helpfulness_summary() -> dict:
    """Get a human-readable summary of feedback data."""
    records = _load_feedback()
    total = len(records)
    if total == 0:
        return {"total_records": 0, "message": "No feedback data collected yet."}

    explicit = [r for r in records if r.get("explicit_rating") is not None]
    thumbs_up = sum(1 for r in explicit if r["explicit_rating"] == 1)
    thumbs_down = sum(1 for r in explicit if r["explicit_rating"] == -1)

    corrections = [r for r in records if r.get("followup_type") == "correction"]
    dwell_times = [r["dwell_seconds"] for r in records if r.get("dwell_seconds") is not None]

    service_help = get_service_helpfulness()

    return {
        "total_records": total,
        "explicit_feedback": len(explicit),
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "thumbs_up_ratio": round(thumbs_up / max(len(explicit), 1), 3),
        "corrections": len(corrections),
        "avg_dwell_seconds": round(sum(dwell_times) / max(len(dwell_times), 1), 1) if dwell_times else None,
        "services_rated": len(service_help),
        "best_service": max(service_help, key=service_help.get) if service_help else None,
        "worst_service": min(service_help, key=service_help.get) if service_help else None,
    }


# ─── Habit Tracking ──────────────────────────────────────────────────────


def _update_habits(record: dict) -> None:
    """Update usage habits from a feedback record.

    Tracks:
      - Services used by hour of day
      - Services used by day of week
      - Most-used sequences (pairs of consecutive services)
    """
    habits = _load_habits()
    service_id = record.get("service_id")
    hour = record.get("hour_of_day")
    day = record.get("day_of_week")

    if service_id and hour is not None:
        hour_key = f"hour_{hour}"
        habits.setdefault("by_hour", {}).setdefault(hour_key, {}).setdefault(service_id, 0)
        habits["by_hour"][hour_key][service_id] += 1

    if service_id and day:
        habits.setdefault("by_day", {}).setdefault(day, {}).setdefault(service_id, 0)
        habits["by_day"][day][service_id] += 1

    # Track consecutive pairs (rolled from previous session context)
    # This is stored in the patterns module for sequence tracking

    _save_habits(habits)


def _load_habits() -> dict:
    """Load habits data from disk."""
    HABITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HABITS_FILE.exists():
        try:
            return json.loads(HABITS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"by_hour": {}, "by_day": {}, "sequences": {}}


def _save_habits(habits: dict) -> None:
    """Save habits data to disk."""
    try:
        atomic_write(HABITS_FILE, json.dumps(habits, indent=2))
    except OSError:
        pass


def get_busiest_hours() -> list[tuple[int, int]]:
    """Get the busiest hours of day sorted by request count.

    Returns list of (hour, count) tuples.
    """
    habits = _load_habits()
    hours = {}
    for hour_key, services in habits.get("by_hour", {}).items():
        try:
            h = int(hour_key.replace("hour_", ""))
            total = sum(services.values())
            hours[h] = total
        except (ValueError, TypeError):
            pass
    return sorted(hours.items(), key=lambda x: -x[1])


def get_busiest_days() -> list[tuple[str, int]]:
    """Get the busiest days of week sorted by request count.

    Returns list of (day_name, count) tuples.
    """
    habits = _load_habits()
    days = {}
    for day, services in habits.get("by_day", {}).items():
        total = sum(services.values())
        days[day] = total
    return sorted(days.items(), key=lambda x: -x[1])


def get_favorite_service_for_hour(hour: int) -> str | None:
    """Get the most-used service at a given hour."""
    habits = _load_habits()
    hour_key = f"hour_{hour}"
    services = habits.get("by_hour", {}).get(hour_key, {})
    if services:
        return max(services, key=services.get)
    return None


# ─── Pattern Detection ────────────────────────────────────────────────────


def _detect_patterns() -> None:
    """Detect common request patterns and sequences.

    Looks for:
      - Frequent two-step sequences (service A → service B)
      - Time-bound patterns (service A always at hour X)
      - Correction patterns (service A frequently miscorrected to service B)
    """
    records = _load_feedback(limit=500)
    patterns = _load_patterns()

    # Track sequences using session_id groupings
    session_sequences: dict[str, list[str]] = {}
    for r in records:
        sid = r.get("session_id", "")
        svc = r.get("service_id", "")
        if sid and svc:
            session_sequences.setdefault(sid, []).append(svc)

    # Count pairs. Self-transitions (checking the same service twice in a
    # row, e.g. asking KENN two questions back to back) are excluded --
    # they're not an actionable "after X, try Y" suggestion, and since the
    # most-used service is also the one most likely to be asked twice in a
    # row, an unguarded self-pair reliably out-counts every real pattern and
    # dominates the top-10 list (surfaced as "After checking kenn, you often
    # check kenn").
    pair_counts: dict[tuple[str, str], int] = {}
    for seq in session_sequences.values():
        for i in range(len(seq) - 1):
            if seq[i] == seq[i + 1]:
                continue
            pair = (seq[i], seq[i + 1])
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

    # Store top pairs
    top_pairs = sorted(pair_counts.items(), key=lambda x: -x[1])[:10]
    patterns["top_sequences"] = [
        {"first": a, "second": b, "count": c}
        for (a, b), c in top_pairs
    ]

    # Track correction patterns
    correction_counts: dict[tuple[str, str], int] = {}
    for r in records:
        cf = r.get("correction_from")
        ct = r.get("correction_to")
        if cf and ct:
            pair = (cf, ct)
            correction_counts[pair] = correction_counts.get(pair, 0) + 1

    top_corrections = sorted(correction_counts.items(), key=lambda x: -x[1])[:5]
    patterns["correction_patterns"] = [
        {"from": a, "to": b, "count": c}
        for (a, b), c in top_corrections
    ]

    _save_patterns(patterns)


def _load_patterns() -> dict:
    """Load pattern data from disk."""
    PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PATTERNS_FILE.exists():
        try:
            return json.loads(PATTERNS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"top_sequences": [], "correction_patterns": []}


def _save_patterns(patterns: dict) -> None:
    """Save pattern data to disk."""
    try:
        atomic_write(PATTERNS_FILE, json.dumps(patterns, indent=2))
    except OSError:
        pass


def get_suggested_sequences(min_count: int = 3) -> list[dict]:
    """Get suggested follow-up sequences based on learned patterns.

    E.g., after checking pipeline, offer to check invoices.

    Returns:
        List of {after, suggest, count} dicts.
    """
    patterns = _load_patterns()
    return [
        {"after": p["first"], "suggest": p["second"], "count": p["count"]}
        for p in patterns.get("top_sequences", [])
        if p["count"] >= min_count
    ]


# ─── Suggestion Generation ────────────────────────────────────────────────


def _generate_suggestions() -> None:
    """Generate context-aware suggestions based on learned data.

    Produces:
      - Shortcut suggestions for frequent clients
      - Sequence suggestions (after X, you usually do Y)
      - Time-based suggestions (you always check pipeline at 10am)
      - Efficiency tips (you might want a macro for this pattern)
    """
    patterns = _load_patterns()
    suggestions = []

    # Sequence suggestions
    for seq in patterns.get("top_sequences", []):
        if seq.get("count", 0) >= 3:
            suggestions.append({
                "type": "sequence",
                "trigger": seq["first"],
                "suggestion": seq["second"],
                "count": seq["count"],
                "message": f"I notice you often check {seq['first']} then {seq['second']}. Would you like me to do both?",
            })

    # Time-based suggestions
    hour = datetime.now().hour
    fav = get_favorite_service_for_hour(hour)
    if fav:
        suggestions.append({
            "type": "time_based",
            "hour": hour,
            "suggestion": fav,
            "message": f"It's {hour}:00 — you usually check {fav} around now. Want me to run it?",
        })

    # Correction patterns
    for corr in patterns.get("correction_patterns", []):
        if corr.get("count", 0) >= 2:
            suggestions.append({
                "type": "auto_correct",
                "from": corr["from"],
                "to": corr["to"],
                "count": corr["count"],
                "message": f"I've noticed you correct {corr['from']} to {corr['to']}. Should I default to {corr['to']} when you ask about this?",
            })

    _save_suggestions(suggestions)


def _load_suggestions() -> list[dict]:
    """Load generated suggestions from disk."""
    SUGGESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SUGGESTIONS_FILE.exists():
        try:
            return json.loads(SUGGESTIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_suggestions(suggestions: list[dict]) -> None:
    """Save generated suggestions to disk."""
    try:
        atomic_write(SUGGESTIONS_FILE, json.dumps(suggestions, indent=2))
    except OSError:
        pass


def get_active_suggestions(service_id: str | None = None, limit: int = 3) -> list[dict]:
    """Get currently active learning-based suggestions.

    Args:
        service_id: If provided, filter suggestions relevant to this service.
        limit: Max suggestions to return.

    Returns:
        List of suggestion dicts.
    """
    suggestions = _load_suggestions()
    if service_id:
        relevant = []
        for s in suggestions:
            if s.get("trigger") == service_id or s.get("suggestion") == service_id:
                relevant.append(s)
        return relevant[:limit]
    return suggestions[:limit]


# ─── Auto-Correction Learning ────────────────────────────────────────────


class AutoCorrectStore:
    """Learning store for auto-correcting common misspellings and mis-routings.

    When a user corrects "Jorden" → "Jordan", this remembers the correction
    and applies it automatically in future requests.
    """

    def __init__(self) -> None:
        self._path = DATA_DIR / "auto_correct.json"
        self._data = self._load()

    def _load(self) -> dict:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "spelling_corrections": {},
            "intent_overrides": {},
            "service_preferences": {},
        }

    def _save(self) -> None:
        try:
            atomic_write(self._path, json.dumps(self._data, indent=2))
        except OSError:
            pass

    def learn_spelling(self, misspelling: str, correction: str) -> None:
        """Learn a spelling correction.

        Args:
            misspelling: The incorrect spelling (e.g., "Jorden").
            correction: The correct form (e.g., "Jordan").
        """
        key = misspelling.lower().strip()
        self._data["spelling_corrections"][key] = {
            "correction": correction,
            "count": self._data["spelling_corrections"].get(key, {}).get("count", 0) + 1,
            "last_seen": datetime.now().isoformat(),
        }
        self._save()

    def apply_spelling(self, text: str) -> str:
        """Apply all learned spelling corrections to text."""
        result = text
        for misspelling, info in self._data.get("spelling_corrections", {}).items():
            correction = info.get("correction", "")
            if correction:
                result = re.sub(
                    rf"\b{re.escape(misspelling)}\b",
                    correction,
                    result,
                    flags=re.IGNORECASE,
                )
        return result

    def learn_intent_override(self, original_intent: str, corrected_intent: str) -> None:
        """Learn that a query matched the wrong intent and should prefer another.

        Args:
            original_intent: The intent that was originally matched.
            corrected_intent: The intent the user expected.
        """
        key = f"{original_intent}→{corrected_intent}"
        self._data["intent_overrides"][key] = {
            "from": original_intent,
            "to": corrected_intent,
            "count": self._data["intent_overrides"].get(key, {}).get("count", 0) + 1,
            "last_seen": datetime.now().isoformat(),
        }
        self._save()

    def get_intent_override(self, original_intent: str) -> str | None:
        """Check if an intent should be overridden based on learned corrections.

        Args:
            original_intent: The initially matched intent.

        Returns:
            Corrected intent name if an override exists, None otherwise.
        """
        best_override = None
        best_count = 0
        for key, info in self._data.get("intent_overrides", {}).items():
            if info.get("from") == original_intent and info.get("count", 0) > best_count:
                best_override = info.get("to")
                best_count = info["count"]
        return best_override

    def learn_service_preference(self, intent_name: str, preferred_service: str) -> None:
        """Learn that a particular intent should use a specific service.

        Args:
            intent_name: The intent name.
            preferred_service: The service to use for this intent.
        """
        key = f"{intent_name}→{preferred_service}"
        self._data["service_preferences"][key] = {
            "intent": intent_name,
            "service": preferred_service,
            "count": self._data["service_preferences"].get(key, {}).get("count", 0) + 1,
        }
        self._save()

    def get_preferred_service(self, intent_name: str) -> str | None:
        """Get the preferred service for an intent, if learned."""
        best_service = None
        best_count = 0
        for key, info in self._data.get("service_preferences", {}).items():
            if info.get("intent") == intent_name and info.get("count", 0) > best_count:
                best_service = info.get("service")
                best_count = info["count"]
        return best_service

    def to_dict(self) -> dict:
        """Get the full auto-correct state (for display/debugging)."""
        return self._data.copy()


# Singleton auto-correct store
_auto_correct = AutoCorrectStore()


def get_auto_correct() -> AutoCorrectStore:
    """Get the shared AutoCorrectStore singleton."""
    return _auto_correct
