from __future__ import annotations

from kenn.core.assistant_profile_memory import AssistantProfileStore
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep
from kenn.core.session_context import build_session_context


def _completed_task(path) -> dict:
    context = build_session_context(
        session_id="song-1",
        snapshot={
            "status": "connected", "tempo": 120.0, "is_playing": False,
            "tracks": [{"index": 0, "name": "Bass", "type": "midi", "devices": []}],
        },
    )
    plan = DeliberativePlan.create(
        goal="Lower the bass slightly",
        context=context,
        status="ready",
        steps=[
            DeliberativeStep.create(
                step_id="propose", kind="live_proposal", action="create_live_proposal",
                objective="Prepare a bass level change.", rationale="The producer requested it.",
                expected_evidence=["verified receipt"],
            ),
        ],
    ).to_dict()
    tasks = AssistantTaskStore(path)
    task = tasks.start(plan=plan, context=context)["task"]
    tasks.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1", "action_id": "action-1",
            "status": "confirmation_required", "requires_confirmation": True,
        },
    )
    return tasks.record_step_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_receipt.v1", "action_id": "action-1",
            "receipt_id": "receipt-1", "status": "applied", "verified": True,
        },
    )["task"]


def test_only_explicit_allowlisted_producer_preferences_are_stored(tmp_path) -> None:
    store = AssistantProfileStore(tmp_path / "memory.db")
    accepted = store.record_preference(
        session_id="song-1", key="creative_direction", value="warm and intimate",
        source_turn_id="turn-1", user_statement="I want this record to feel warm and intimate.",
    )
    inferred = store.record_preference(
        session_id="song-1", key="genre", value="techno",
        source_turn_id="turn-2", user_statement="Can you inspect the kick?",
    )
    sensitive = store.record_preference(
        session_id="song-1", key="home_address", value="London",
        source_turn_id="turn-3", user_statement="I live in London.",
    )

    assert accepted["ok"] is True
    assert accepted["preference"]["confidence"] == "explicit"
    assert accepted["preference"]["advisory_only"] is True
    assert inferred["ok"] is False
    assert sensitive["ok"] is False
    assert [item["key"] for item in store.current_preferences("song-1")] == ["creative_direction"]


def test_new_explicit_preference_supersedes_prior_value_and_can_be_forgotten(tmp_path) -> None:
    store = AssistantProfileStore(tmp_path / "memory.db")
    store.record_preference(
        session_id="song-1", key="monitoring", value="headphones", source_turn_id="turn-1",
        user_statement="I am mixing on headphones.",
    )
    store.record_preference(
        session_id="song-1", key="monitoring", value="monitors", source_turn_id="turn-2",
        user_statement="I switched to monitors.",
    )

    assert [(item["key"], item["value"]) for item in store.current_preferences("song-1")] == [("monitoring", "monitors")]
    assert store.forget_preference(session_id="song-1", key="monitoring") is True
    assert store.current_preferences("song-1") == []


def test_completed_receipted_task_and_explicit_feedback_create_episode(tmp_path) -> None:
    path = tmp_path / "memory.db"
    task = _completed_task(path)
    store = AssistantProfileStore(path)

    result = store.record_task_outcome(
        task_id=task["task_id"], verdict="keep", source_turn_id="turn-9",
        user_statement="Keep that change, the bass sits much better now.",
        comment="The bass sits much better now.",
    )

    assert result["ok"] is True
    assert result["episode"]["verdict"] == "keep"
    assert result["episode"]["evidence_refs"][0]["receipt_id"] == "receipt-1"
    assert result["episode"]["advisory_only"] is True
    assert "Keep that change" not in str(result["episode"])
    assert store.recent_episodes("song-1")[0]["task_id"] == task["task_id"]


def test_incomplete_or_unreceipted_task_cannot_become_episode(tmp_path) -> None:
    path = tmp_path / "memory.db"
    context = build_session_context(
        session_id="song-1",
        snapshot={"status": "connected", "tracks": [], "is_playing": False},
    )
    plan = DeliberativePlan.create(
        goal="Inspect", context=context, status="ready",
        steps=[DeliberativeStep.create(
            step_id="inspect", kind="inspection", action="inspect_live",
            objective="Inspect Live.", rationale="Need state.", expected_evidence=["context"],
        )],
    ).to_dict()
    task = AssistantTaskStore(path).start(plan=plan, context=context)["task"]

    result = AssistantProfileStore(path).record_task_outcome(
        task_id=task["task_id"], verdict="keep", source_turn_id="turn-2",
        user_statement="Keep it.",
    )

    assert result["ok"] is False
    assert any("completed" in error for error in result["errors"])
    assert any("receipt" in error for error in result["errors"])


def test_one_task_cannot_generate_duplicate_episodes(tmp_path) -> None:
    path = tmp_path / "memory.db"
    task = _completed_task(path)
    store = AssistantProfileStore(path)
    kwargs = {
        "task_id": task["task_id"], "verdict": "keep", "source_turn_id": "turn-9",
        "user_statement": "Keep that exact change.",
    }

    assert store.record_task_outcome(**kwargs)["ok"] is True
    duplicate = store.record_task_outcome(**kwargs)

    assert duplicate["ok"] is False
    assert "already" in duplicate["errors"][0]


def test_profile_memory_enters_planner_context_as_advisory_evidence(tmp_path) -> None:
    path = tmp_path / "memory.db"
    task = _completed_task(path)
    store = AssistantProfileStore(path)
    store.record_preference(
        session_id="song-1", key="creative_direction", value="warm",
        source_turn_id="turn-1", user_statement="Please keep this mix warm.",
    )
    store.record_task_outcome(
        task_id=task["task_id"], verdict="keep", source_turn_id="turn-2",
        user_statement="Keep that bass change.", comment="The low end is clearer.",
    )
    memory = store.context_memory("song-1")

    context = build_session_context(
        session_id="song-1",
        snapshot={"status": "connected", "tracks": [], "is_playing": False},
        **memory,
    )

    assert context["producer_preferences"][0]["value"] == "warm"
    assert context["producer_preferences"][0]["advisory_only"] is True
    assert context["episodic_outcomes"][0]["verdict"] == "keep"
    assert context["episodic_outcomes"][0]["evidence_refs"][0]["receipt_id"] == "receipt-1"
    assert {source["kind"] for source in context["sources"]} >= {"producer_preference", "production_episode"}


def test_profile_and_episode_memory_can_be_forgotten_without_deleting_task(tmp_path) -> None:
    path = tmp_path / "memory.db"
    task = _completed_task(path)
    store = AssistantProfileStore(path)
    store.record_preference(
        session_id="song-1", key="genre", value="techno",
        source_turn_id="turn-1", user_statement="This project is techno.",
    )
    episode = store.record_task_outcome(
        task_id=task["task_id"], verdict="keep", source_turn_id="turn-2",
        user_statement="Keep that bass change.",
    )["episode"]

    assert store.forget_episode(session_id="another-session", episode_id=episode["episode_id"]) is False
    assert store.forget_episode(session_id="song-1", episode_id=episode["episode_id"]) is True
    assert store.recent_episodes("song-1") == []
    cleared = store.clear_profile("song-1")
    assert cleared == {"preferences": 1, "episodes": 0}
    assert AssistantTaskStore(path).load(task["task_id"])["status"] == "completed"
