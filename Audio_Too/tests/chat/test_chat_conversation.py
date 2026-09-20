"""Tests for conversational chat turns that should not hit weak retrieval."""

from __future__ import annotations

import sys
from pathlib import Path

LM = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM.parent))

import json
from types import SimpleNamespace

from kenn.core import chat  # noqa: E402
from kenn.core import chat_answer, chat_retrieval, chat_routing  # noqa: E402
from kenn.core.chat import answer_payload, conversational_payload, history_context_line, route_query, search_query_with_history  # noqa: E402


def test_greeting_returns_chat_starter_payload() -> None:
    payload = conversational_payload("hello")
    assert payload is not None
    assert payload["conversation_only"] is True
    assert payload["confidence"] == "high"
    assert payload["related_questions"]
    # 2026-07-27: the greeting copy now picks one of 4 warm variants via
    # `hash(query) % 4` (chat_routing.py) -- and Python's string hash is
    # per-process salted by default, so the exact wording isn't stable
    # even for the same input text across runs/restarts. Checking
    # membership in the actual pool (rather than one hardcoded substring)
    # is the only assertion that isn't flaky by construction.
    greeting_variants = {
        "Hey! Good to have you in the studio. What are we focusing on today?",
        "Yo! Ready when you are. What are we mixing, tweaking, or building next?",
        "Hey there! Got a specific audio problem or track to review?",
        "Good day! I'm set for session work or production chat. What's the plan?",
    }
    assert payload["answer"] in greeting_variants


def test_check_in_does_not_retrieve_random_manual_answer() -> None:
    payload = answer_payload("how're you?", allow_llm=False)
    assert payload["conversation_only"] is True
    assert payload["intent"] == "check_in"
    assert payload["route"] == "conversation"
    assert payload["sources"] == []
    assert payload["source_quality"] == "not_needed"
    # 2026-07-27: same hash(query)%4 variant pool as the greeting/thanks
    # cases in this file -- membership check, not a substring.
    check_in_variants = {
        "Doing great, thanks! Ready to dive into some audio. What are we working on today?",
        "All good on my end! The studio setup is warmed up—what track are we tuning or mixing?",
        "Feeling sharp! Ready to inspect stems, fix phase issues, or chat through mix decisions. What's on your mind?",
        "Everything's running smoothly! Let me know what session problem we should solve next.",
    }
    assert payload["answer"] in check_in_variants
    assert "automation clip" not in payload["answer"].lower()


def test_retrieval_payload_includes_answer_diagnostics() -> None:
    payload = answer_payload("How do I sidechain bass to the kick?", allow_llm=False)
    assert "conversation_only" not in payload
    assert payload["intent"] in {"steps", "general", "troubleshooting", "explain", "why"}
    assert payload["intent_guard"] in {"strong", "medium", "weak"}
    assert isinstance(payload["weak_match"], bool)
    assert payload["search_query"]
    assert payload["diagnostic_reason"]
    assert "answer_self_check" in payload
    assert "grounding" in payload
    assert 0 <= payload["grounding"]["score"] <= 100
    assert payload["grounding_mode"] in {"strong", "medium", "weak"}


def test_production_answer_uses_professional_rubric() -> None:
    payload = answer_payload("How do I sidechain bass to the kick?", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["route"] == "production"
    # The intent-based system uses "Here are the steps:" for "steps" intent
    assert "here are the steps:" in answer
    assert "why this works:" in answer
    assert "listening check:" in answer
    assert payload["answer_self_check"]["sections"]["check"] is True
    assert payload["grounding"]["top_source_trust"] > 0
    assert payload["grounding_mode"] == "strong"
    assert "branches" in payload


def test_diagnostic_answer_prioritizes_first_move() -> None:
    payload = answer_payload("My 808 disappears on phone speakers, what should I fix first?", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "mix_diagnosis"
    # The intent-based troubleshooting template uses symptom-first structure
    assert "symptom and likely cause:" in answer
    assert "try this in your session:" in answer
    assert "symptom" in answer
    assert "matched loudness" in answer
    assert answer.index("symptom and likely cause:") < answer.index("try this in your session:")
    assert payload["answer_quality"]["score"] >= 94


def test_sidechain_diagnosis_answer_keeps_symptom_boundary() -> None:
    payload = answer_payload("How do I sidechain bass to the kick?", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "mix_diagnosis"
    # The intent-based system uses "Symptom and likely cause:" instead of "diagnosis boundary:"
    assert "symptom and likely cause:" in answer or "symptom" in answer
    assert "matched loudness" in answer
    assert "listening check:" in answer


def test_game_audio_answer_includes_runtime_tradeoff() -> None:
    payload = answer_payload("How should I prepare loudness for mobile game audio in Wwise?", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "game_audio_implementation"
    # Intent-based system uses "Here are the steps:" for steps intent
    assert "here are the steps:" in answer
    assert "implementation check:" in answer
    assert "headroom" in answer or "loudness" in answer
    assert payload["answer_quality"]["score"] >= 80


def test_mastering_answer_includes_loudness_boundary() -> None:
    payload = answer_payload("My master is loud but distorted, what should I check first?", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "mastering_safety"
    # General template uses "For the final master, here is the direct advice:"
    assert "for the final master, here is the direct advice:" in answer
    assert "mastering check:" in answer
    assert "true peak" in answer
    assert "balance" in answer
    assert "loudness" in answer
    assert payload["answer_quality"]["score"] >= 70


def test_mastering_clipper_answer_keeps_loudness_boundary() -> None:
    payload = answer_payload("Should I use a clipper before the limiter in mastering?", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "mastering_safety"
    assert "mastering check:" in answer or "mastering boundary:" in answer
    assert "true peak" in answer


def test_feedback_repair_note_answers_boxy_vocals() -> None:
    payload = answer_payload("How do I fix boxy vocals?", allow_llm=False)
    answer = payload["answer"].lower()
    labels = " ".join(source["label"] for source in payload["sources"]).lower()

    assert payload["weak_match"] is False
    assert payload["confidence"] == "high"
    assert "boxy-vocal-correction" in labels
    assert "200-500 hz" in answer
    assert "drum processing" not in answer


def test_pricing_followup_uses_quote_context() -> None:
    history = [{"role": "user", "content": "I need to quote a mix for a client."}]

    payload = answer_payload("What should I ask first?", history=history, allow_llm=False)
    labels = " ".join(source["label"] for source in payload["sources"]).lower()

    assert payload["weak_match"] is False
    assert payload["answer_mode"] == "client_delivery"
    assert "client-mix-pricing-and-quotes" in labels
    assert "scope" in payload["answer"].lower()


def test_client_pricing_answer_includes_scope_boundary() -> None:
    payload = answer_payload(
        "Can you give me an exact cheap price for mixing 100 stems by tomorrow?",
        allow_llm=False,
    )
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "client_delivery"
    # The general template uses "Here is the recommended production technique:" for production route
    assert "here is the recommended production technique:" in answer
    assert "scope boundary:" in answer
    assert "deadline" in answer or "rush" in answer
    assert payload["answer_quality"]["score"] >= 80


def test_client_delivery_answer_keeps_scope_boundary() -> None:
    payload = answer_payload("What should I send a client after the final mix is approved?", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "client_delivery"
    assert "scope boundary:" in answer or "delivery check:" in answer or "before you send" in answer


def test_stereo_width_answer_names_phase_check() -> None:
    payload = answer_payload(
        "How do I make a mix wider without it falling apart in mono?", allow_llm=False
    )

    assert "phase" in payload["answer"].lower()


def test_pricing_answer_excludes_unrelated_mix_bus_source() -> None:
    payload = answer_payload("How should I price a mix?", allow_llm=False)
    labels = " ".join(source["label"] for source in payload["sources"]).lower()

    assert "client-mix-pricing-and-quotes" in labels
    assert "mix bus" not in payload["answer"].lower()


def test_next_step_followup_uses_mix_context() -> None:
    history = [{"role": "user", "content": "My mix sounds flat and the chorus does not lift."}]

    payload = answer_payload("What should I do next?", history=history, allow_llm=False)

    assert payload["weak_match"] is False
    assert payload["confidence"] == "high"
    assert "mixing" in payload["topics"]
    assert payload["sources"]


def test_medium_grounding_adds_cautious_language(monkeypatch) -> None:
    def medium_grounding(*args, **kwargs):
        return {
            "score": 60,
            "top_source_trust": 0.78,
            "approved_note": False,
            "source_topic_match": True,
            "answered_intent": True,
            "route_known": True,
            "warnings": [],
        }

    monkeypatch.setattr(chat_answer, "grounding_report", medium_grounding)

    payload = answer_payload("How do I automate filter cutoff?", allow_llm=False)

    assert payload["grounding_mode"] == "medium"
    assert payload["weak_match"] is False
    assert "closest local notes" in payload["answer"].lower()


def test_weak_grounding_avoids_forced_answer(monkeypatch) -> None:
    def weak_grounding(*args, **kwargs):
        return {
            "score": 40,
            "top_source_trust": 0.55,
            "approved_note": False,
            "source_topic_match": False,
            "answered_intent": False,
            "route_known": True,
            "warnings": ["source topic mismatch", "answer may miss intent"],
        }

    monkeypatch.setattr(chat_answer, "grounding_report", weak_grounding)

    payload = answer_payload("How do I automate filter cutoff?", allow_llm=False)

    assert payload["grounding_mode"] == "weak"
    assert payload["weak_match"] is True
    assert payload["sources"] == []
    assert payload["source_quality"] == "low"
    # 2026-07-27: weak grounding now asks a clarifying follow-up instead of
    # a blunt refusal ("...could you share a bit more context?") -- still
    # correctly avoids forcing an unsupported answer, just phrased warmer.
    assert "more context" in payload["answer"].lower()
    assert "grounding score was too low" in payload["diagnostic_reason"].lower()


def test_ableton_answer_uses_live_check() -> None:
    payload = answer_payload("How do I automate filter cutoff?", allow_llm=False)
    answer = payload["answer"].lower()
    labels = " ".join(source["label"] for source in payload["sources"]).lower()

    assert payload["route"] == "ableton"
    assert payload["answer_mode"] == "ableton_steps"
    assert payload["grounding_mode"] == "strong"
    assert "filter-cutoff-automation" in labels
    assert "auto filter" in answer
    assert "cutoff" in answer
    # Intent-based system: "steps" intent uses "Here are the steps:" instead of "first move in live:"
    assert "here are the steps:" in answer or "try this:" in answer
    assert "listening check:" in answer or "check:" in answer
    assert "duplicate" in answer or "save" in answer or "ableton" in answer or "live" in answer


def test_cpu_overload_answer_keeps_live_safety_boundary() -> None:
    payload = answer_payload("ableton cpu overload what should I do", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "ableton_steps"
    assert payload["grounding_mode"] == "strong"
    assert "live" in answer or "ableton" in answer
    assert payload["answer_quality"]["score"] >= 80


def test_reverb_send_track_is_not_client_delivery() -> None:
    payload = answer_payload("reverb on a send track", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["route"] == "ableton"
    assert payload["answer_mode"] == "ableton_steps"
    assert "reverb" in answer
    assert "return track" in answer or "send" in answer or "reverb" in answer


def test_client_stem_send_stays_client_delivery() -> None:
    payload = answer_payload("how should a client send stems for mixing", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "client_delivery"
    assert "stem" in answer


def test_podcast_dialogue_uses_cleanup_mode() -> None:
    payload = answer_payload("how should I edit podcast dialogue", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "dialogue_cleanup"
    # Steps intent uses "Here are the steps:"
    assert "here are the steps:" in answer or "try this:" in answer
    assert "dialogue check:" in answer or "listening check:" in answer
    assert payload["answer_quality"]["score"] >= 80


def test_noisy_dialogue_cleanup_preserves_room_tone_boundary() -> None:
    payload = answer_payload("how do I clean noisy dialogue without artifacts", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "dialogue_cleanup"
    assert "room tone" in answer
    assert "noise" in answer or "noisy" in answer


def test_typo_sidechain_query_is_strongly_grounded() -> None:
    payload = answer_payload("sidechane bas to kik", allow_llm=False)
    answer = payload["answer"].lower()

    assert payload["answer_mode"] == "mix_diagnosis"
    assert payload["grounding_mode"] == "strong"
    assert "sidechain" in answer
    assert "bass" in answer
    assert "kick" in answer
    assert payload["answer_quality"]["score"] >= 74


def test_out_of_scope_audio_adjacent_query_skips_retrieval() -> None:
    payload = answer_payload("can ableton fix my car engine", allow_llm=False, profile=True)

    assert payload["intent"] == "out_of_scope"
    assert payload["route"] == "out_of_scope"
    assert payload["sources"] == []
    assert payload["found"] is False
    assert payload["confidence"] == "low"
    # This is the real invariant this test guards: retrieval was skipped
    # entirely, not that a random spurious topical match slipped through.
    # (2026-07-27: the old "mud"/"eq" not-in-answer proxy checks broke
    # against the new canned out-of-scope copy, which legitimately lists
    # "harshness, muddy low-end" as an example of in-scope topics -- that's
    # intentional copy, not a retrieval leak, and search_ms/sources/found
    # already directly verify retrieval never ran.)
    assert payload["timings_ms"]["search_ms"] == 0.0


def test_check_in_variants_are_conversational() -> None:
    for query in ("how are you?", "how's it going?", "you good?"):
        payload = conversational_payload(query)
        assert payload is not None
        assert payload["intent"] == "check_in"
        assert payload["conversation_only"] is True


def test_thanks_keeps_conversation_flowing() -> None:
    payload = conversational_payload("thanks", [{"role": "user", "content": "How do I export stems?"}])
    assert payload is not None
    assert payload["used_history"] is True
    # 2026-07-27: same hash(query)%4 variant pool as the greeting case
    # above -- membership check, not a substring, since exact wording isn't
    # stable across process restarts.
    thanks_variants = {
        "Anytime! Let me know if you want to test another move in the session.",
        "You got it! I'm right here whenever you want to work through the next track.",
        "Happy to help! Let's keep the momentum going on this project.",
        "Cheers! Let me know what track or mix problem we're tackling next.",
    }
    assert payload["answer"] in thanks_variants


def test_meta_chat_does_not_retrieve_random_audio_answer() -> None:
    payload = conversational_payload("sorry! wrong LLM, thought you were DeepSeek")
    assert payload is not None
    assert payload["conversation_only"] is True
    assert payload["route"] == "conversation"
    assert payload["sources"] == []
    assert "kenn" in payload["answer"].lower()
    # 2026-07-27: updated to match current copy ("...your studio AI
    # companion for Ableton, mixing, mastering, stems, client deliverables,
    # and audio production workflow. Ask me anything!").
    assert "studio ai companion" in payload["answer"].lower()


def test_meta_chat_answer_payload_stays_conversational() -> None:
    payload = answer_payload("sorry! wrong LLM, thought you were DeepSeek", allow_llm=False)
    assert payload["conversation_only"] is True
    assert payload["sources"] == []
    assert payload["source_quality"] == "not_needed"
    assert "deliver final mix" not in payload["answer"].lower()


def test_audio_generation_prompt_routes_to_audiogen(monkeypatch) -> None:
    fake = SimpleNamespace(
        prompt_requests_generation=lambda query: "chorus" in query.lower(),
        generation_request_kind=lambda query: "loop",
        requests_variation=lambda query: False,
        generate_for_kenn=lambda query: {
            "ok": True,
            "emotion": "sadness",
            "wav_path": "/tmp/sad.wav",
            "portfolio_entry": {"title": "Sad chorus", "src": "/portfolio/audio/sad.wav"},
        },
    )
    monkeypatch.setitem(sys.modules, "audiogen_bridge", fake)

    payload = answer_payload("generate a sad chorus", allow_llm=False)

    assert payload["route"] == "audiogen"
    assert payload["found"] is True
    assert payload["grounding_mode"] == "strong"
    assert "generated an audiogen chorus" in payload["answer"].lower()
    assert payload["is_variation"] is False


def test_audio_generation_variation_request_is_framed_as_a_variation(monkeypatch) -> None:
    # D3.5 (docs/KENN_FUTURE_PLAN.md Phase 3), buildable half: "too
    # repetitive, give me a variation" reuses the same generation
    # pipeline, just framed differently in the reply.
    fake = SimpleNamespace(
        prompt_requests_generation=lambda query: True,
        generation_request_kind=lambda query: "loop",
        requests_variation=lambda query: True,
        generate_for_kenn=lambda query: {
            "ok": True,
            "emotion": "joy",
            "wav_path": "/tmp/variation.wav",
            "portfolio_entry": {"title": "Joy chorus", "src": "/portfolio/audio/joy.wav"},
        },
    )
    monkeypatch.setitem(sys.modules, "audiogen_bridge", fake)

    payload = answer_payload("my loop is too repetitive, give me a variation", allow_llm=False)

    assert payload["route"] == "audiogen"
    assert payload["is_variation"] is True
    assert "here's a variation" in payload["answer"].lower()


def test_audio_generation_full_song_queues_background_job(monkeypatch) -> None:
    fake = SimpleNamespace(
        prompt_requests_generation=lambda query: True,
        generation_request_kind=lambda query: "full_song",
        infer_emotion=lambda query: "joy",
        requests_automix_chain=lambda query: False,
        enqueue_full_song_render=lambda **kwargs: {
            "ok": True,
            "job": {
                "id": "job-123",
                "status": "queued",
                "emotion": kwargs["emotion"],
                "bars": kwargs["bars"],
            },
        },
    )
    monkeypatch.setitem(sys.modules, "audiogen_bridge", fake)

    payload = answer_payload("generate a full joy song", allow_llm=False)

    assert payload["route"] == "audiogen"
    assert payload["found"] is True
    assert payload["audiogen"]["job"]["id"] == "job-123"
    assert "queued a full audiogen song" in payload["answer"].lower()
    assert payload["chained_to_automix"] is False


def test_audio_generation_full_song_with_automix_chain_phrasing(monkeypatch, tmp_path) -> None:
    # D3.2: "generate drums and bassline, then render an AutoMix pass
    # from these" -- the underlying stem-capture -> AutoMix chain already
    # existed (queue_automix_from_stem_files in audiogen_bridge.py) but
    # was only reachable via the authenticated dashboard, never chat.
    WEBSITE = Path(__file__).resolve().parent.parent.parent / "server" / "app"
    sys.path.insert(0, str(WEBSITE))
    import db as business_db

    monkeypatch.setattr(business_db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(business_db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(business_db, "_migration_done", False)
    business_db.init_db()
    from kenn.core import session_memory

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")

    captured_kwargs = {}

    def fake_enqueue(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "ok": True,
            "job": {"id": "job-456", "status": "queued", "emotion": kwargs["emotion"], "bars": kwargs["bars"]},
        }

    fake = SimpleNamespace(
        prompt_requests_generation=lambda query: True,
        generation_request_kind=lambda query: "full_song",
        infer_emotion=lambda query: "joy",
        requests_automix_chain=lambda query: True,
        enqueue_full_song_render=fake_enqueue,
    )
    monkeypatch.setitem(sys.modules, "audiogen_bridge", fake)

    payload = answer_payload(
        "generate drums and bassline, then render an automix pass from these",
        allow_llm=False,
        session_id="s1",
    )

    assert payload["route"] == "audiogen"
    assert payload["chained_to_automix"] is True
    assert "chain straight into an automix render" in payload["answer"].lower()
    assert captured_kwargs["chain_to_automix"] is True
    # A real project gets minted for continuity (same resolve-or-create
    # pattern server.py::resolve_session_project() uses elsewhere).
    assert captured_kwargs["project_id"].startswith("kenn-")

    from kenn.core.session_memory import get_remembered_automix_project

    assert get_remembered_automix_project("s1") == captured_kwargs["project_id"]


def test_audio_generation_vague_request_asks_loop_or_full_song(monkeypatch) -> None:
    fake = SimpleNamespace(
        prompt_requests_generation=lambda query: True,
        generation_request_kind=lambda query: "clarify",
        infer_emotion=lambda query: "joy",
    )
    monkeypatch.setitem(sys.modules, "audiogen_bridge", fake)

    payload = answer_payload("generate some music", allow_llm=False)

    assert payload["route"] == "audiogen"
    assert payload["conversation_only"] is True
    assert "short loop" in payload["answer"].lower()
    assert "full-song render" in payload["answer"].lower()


def test_unclear_prompt_asks_for_clarification() -> None:
    payload = answer_payload("make it better", allow_llm=False, profile=True)

    assert payload["route"] == "clarify"
    assert payload["intent"] == "clarify"
    assert payload["sources"] == []
    assert payload["source_quality"] == "not_needed"
    assert "mix problem" in payload["answer"].lower()
    assert payload["conversation_only"] is True


def test_route_memory_can_force_fallback_without_retrieval(tmp_path, monkeypatch) -> None:
    route_memory = tmp_path / "kenn_route_memory.jsonl"
    route_memory.write_text(
        json.dumps(
            {
                "schema": "kenn.route_memory.v1",
                "case_id": "fallback-test",
                "question": "best tax setup for a music business",
                "observed_route": "production",
                "target_route": "out_of_scope",
                "answer_policy": "should_fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_retrieval, "ROUTE_MEMORY_PATH", route_memory)
    chat._load_route_memory_cached.cache_clear()

    payload = answer_payload("best tax setup for a music business", allow_llm=False, profile=True)

    assert payload["route"] == "out_of_scope"
    assert payload["sources"] == []
    assert payload["timings_ms"]["search_ms"] == 0.0
    chat._load_route_memory_cached.cache_clear()


def test_audio_adjacent_legal_prompt_falls_back_before_audiogen() -> None:
    payload = answer_payload("Can you write my music business contract?", allow_llm=False, profile=True)

    assert payload["route"] == "out_of_scope"
    assert payload["intent"] == "out_of_scope"
    assert payload["sources"] == []
    assert payload["confidence"] == "low"
    # 2026-07-27: updated to match the current canned out-of-scope copy
    # ("I specialize in audio engineering, studio production, mixing,
    # mastering, and Ableton Live workflows...") -- a self-description
    # instead of a blunt refusal, still correctly declines the off-topic ask.
    assert "i specialize in audio engineering" in payload["answer"].lower()
    assert "generate a loop" not in payload["answer"].lower()


def test_medical_and_financial_prompts_skip_retrieval() -> None:
    for question in [
        "Can Ableton diagnose my ear infection after a loud show?",
        "Should I invest my music income in crypto?",
    ]:
        payload = answer_payload(question, allow_llm=False, profile=True)
        assert payload["route"] == "out_of_scope"
        assert payload["sources"] == []
        assert payload["confidence"] == "low"
        assert "i specialize in audio engineering" in payload["answer"].lower()


def test_standalone_question_ignores_stale_history() -> None:
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi. Ask a question."},
        {"role": "user", "content": "Mix bus compression before or after EQ?"},
    ]
    query = "EQ before or after compression?"

    assert search_query_with_history(query, history) == query

    payload = answer_payload(query, history=history, allow_llm=False)
    answer = payload["answer"].lower()
    assert payload["used_history"] is False
    assert "following up" not in answer
    assert "hello" not in answer


def test_standalone_sidechain_query_ignores_default_premaster_context(monkeypatch) -> None:
    history = [
        {"role": "user", "content": "How loud should my master be?"},
        {"role": "assistant", "content": "Use a mastering-safe target."},
        {
            "role": "user",
            "content": (
                "Session context for this KENN conversation.\n"
                "Mix target: Premaster / general mix (premaster).\n"
                "Use this context to make advice more specific, but keep source grounding rules."
            ),
        },
    ]
    monkeypatch.setattr(
        chat_answer,
        "_build_session_context",
        lambda session_id="": "Earlier, we were discussing mastering and limiting.",
    )

    assert chat.should_use_history("sidechain", history) is False
    assert search_query_with_history("sidechain", history) == "sidechain"

    payload = answer_payload(
        "sidechain",
        history=history,
        allow_llm=False,
        session_id="sidechain-context-regression",
    )
    answer = payload["answer"].lower()
    assert payload["search_query"] == "sidechain"
    assert payload["topics"] == ["compression"]
    assert payload["answer_mode"] == "mix_diagnosis"
    assert payload["used_history"] is False
    assert "sidechain" in answer
    assert "mastering-safe" not in answer
    assert "before you send that file" not in answer
    assert "earlier, we were discussing mastering" not in answer

    events = list(
        chat.answer_payload_stream(
            "sidechain",
            history=history,
            allow_llm=False,
            session_id="sidechain-stream-context-regression",
        )
    )
    metadata = next(event["data"] for event in events if event["event"] == "metadata")
    streamed_answer = "".join(
        event["token"] for event in events if event["event"] == "token"
    ).lower()
    assert metadata["search_query"] == "sidechain"
    assert metadata["answer_mode"] == "mix_diagnosis"
    assert metadata["used_history"] is False
    assert "sidechain" in streamed_answer
    assert "mastering-safe" not in streamed_answer


def test_matching_session_target_does_not_pollute_retrieval_query() -> None:
    history = [
        {
            "role": "user",
            "content": (
                "Session context for this KENN conversation.\n"
                "Mix target: Premaster / general mix (premaster).\n"
                "Use this context to make advice more specific, but keep source grounding rules."
            ),
        }
    ]
    query = "How loud should my master be?"

    assert chat.should_use_history(query, history) is True
    assert search_query_with_history(query, history) == query
    assert history_context_line(query, history).startswith("[Session Context]: Using session context:")


def test_true_followup_uses_last_useful_user_turn() -> None:
    history = [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "How do I sidechain bass to the kick?"},
    ]
    query = "what about release time?"

    search_query = search_query_with_history(query, history)
    assert "sidechain bass" in search_query.lower()
    assert query in search_query


def test_referential_diagnostic_followup_uses_history() -> None:
    history = [{"role": "user", "content": "My encoded master clips even though the WAV stays below zero."}]
    query = "What kind of peak am I missing?"
    search_query = search_query_with_history(query, history)
    assert "encoded master clips" in search_query.lower()
    assert chat.should_use_history(query, history) is True


def test_referential_question_without_history_requests_clarification() -> None:
    payload = answer_payload("Should I make it wider now?", allow_llm=False)
    assert payload["route"] == "clarify"
    assert payload["confidence"] == "low"
    assert payload["weak_match"] is True


def test_mix_phrase_wording_does_not_trigger_audio_generation() -> None:
    payload = answer_payload(
        "How can I make phrase-ending reverb or delay audible without washing every vocal line?",
        allow_llm=False,
    )
    assert payload["route"] != "audiogen"
    assert payload["route"] == "production"


def test_true_followup_skips_session_directive_when_selecting_prior_question() -> None:
    history = [
        {"role": "user", "content": "How do I sidechain bass to the kick?"},
        {
            "role": "user",
            "content": (
                "Session context for this KENN conversation.\n"
                "Mix target: Premaster / general mix (premaster)."
            ),
        },
    ]
    query = "what about release time?"

    search_query = search_query_with_history(query, history)
    assert "sidechain bass" in search_query.lower()
    assert "premaster" not in search_query.lower()


def test_mix_review_context_supports_metric_followups() -> None:
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Test Mix.\n"
                "Metrics: crest factor db=5.2, dominant band=low mids.\n"
                "Flags: low-mid buildup, low crest factor."
            ),
        }
    ]
    query = "How do I improve the crest factor?"

    search_query = search_query_with_history(query, history)

    assert "Mix Review Lab context" in search_query
    assert "crest factor" in search_query
    assert history_context_line(query, history) == "[Mix Review Context]: Using the latest Mix Review Lab analysis from your uploaded track."
    assert route_query(query, history) == "mix_review_followup"


def test_mix_review_followup_answers_from_latest_review_context() -> None:
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Test Mix.\n"
                "Use this structured uploaded-track analysis before general retrieval notes.\n"
                "Structured metrics: technical score=72, crest factor db=5.2.\n"
                "Structured flags: Low dynamics: crest factor is tight | Low-mid buildup: 250 Hz feels crowded.\n"
                "Structured priority actions: Dynamics: Ease limiter by 2 dB | Low mids: Cut 250 Hz gently.\n"
                "Structured revision checklist: Export: Re-export one revision at matched loudness."
            ),
        }
    ]

    payload = chat.answer_payload("What should I fix first?", history=history, allow_llm=False)

    assert payload["route"] == "mix_review_followup"
    assert payload["found"] is True
    assert payload["used_history"] is True
    assert "Ease limiter by 2 dB" in payload["answer"]
    assert "Low dynamics" in payload["answer"]
    assert payload["sources"][0]["label"] == "Mix Review Lab context from the latest uploaded review"


def test_mix_review_first_priority_keeps_actions_separate_and_shows_measurements() -> None:
    """A real review may contain both legacy prose and structured data.

    The structured priority actions must win; otherwise semicolon-delimited
    legacy repair templates collapse into a misleading mega-step.
    """
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Measured Test.\n"
                "Priority actions: #1 legacy First: stale action; #2 legacy Second: stale action.\n"
                "Structured priority actions: #1 fix_first (high confidence) Low headroom: Lower output. | "
                "#2 fix_first (high confidence) Clipping risk: Bypass clippers in order.\n"
                "Objective technical metrics: {\"true_peak_dbfs\": 0.01, \"integrated_lufs\": -1.87, \"crest_factor_db\": 3.01}\n"
                "Structured Ableton repairs: Low headroom: Utility -> Lower gain.; Clipping: Limiter -> Bypass drive."
            ),
        }
    ]

    payload = chat.answer_payload("What should I fix first?", history=history, allow_llm=False)
    answer = payload["answer"]

    assert "Start with: #1 fix_first" in answer
    assert "#2 fix_first" in answer
    assert "legacy First" not in answer
    assert "Measured evidence from the uploaded file:" in answer
    assert "True peak: 0.01 dBFS" in answer
    assert "Integrated loudness: -1.87 LUFS" in answer
    assert "Lower gain.; Clipping" not in answer


def test_mix_review_followup_stream_answers_from_latest_review_context() -> None:
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Stream Test.\n"
                "Structured priority actions: Balance: Turn the bass down 1 dB."
            ),
        }
    ]

    events = list(chat.answer_payload_stream("What should I do next?", history=history, allow_llm=False))

    assert events[0]["event"] == "metadata"
    assert events[0]["data"]["route"] == "mix_review_followup"
    assert any("Turn the bass down 1 dB" in str(event.get("token")) for event in events)


def test_mix_review_followup_includes_ableton_repair_templates() -> None:
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Ableton Repair Test.\n"
                "Structured Ableton repairs: Low-mid build-up: EQ Eight on dense instruments -> "
                "Cut around 150-400 Hz on the source creating the cloud."
            ),
        }
    ]

    payload = chat.answer_payload("How do I fix that in Ableton?", history=history, allow_llm=False)

    assert payload["route"] == "mix_review_followup"
    assert "EQ Eight on dense instruments" in payload["answer"]
    assert "150-400 Hz" in payload["answer"]


def test_mix_review_followup_prioritizes_next_revision_plan() -> None:
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Revision Plan Test.\n"
                "Structured priority actions: Low dynamics: Ease the limiter.\n"
                "Structured next revision focus: Remaining flag to address: Low dynamics.\n"
                "Structured next revision steps: Dynamics: Reduce limiter input by 2 dB | "
                "Export: Re-upload v3 at matched loudness."
            ),
        }
    ]

    payload = chat.answer_payload("What should I do for the next version?", history=history, allow_llm=False)

    assert payload["route"] == "mix_review_followup"
    assert "Start with: Dynamics: Reduce limiter input by 2 dB" in payload["answer"]
    assert "Next revision focus" in payload["answer"]
    assert "Remaining flag to address: Low dynamics" in payload["answer"]


def test_mix_review_followup_flags_reference_eq_moves_as_unvalidated() -> None:
    # Known Gap #5 (docs/KENN_FUTURE_PLAN.md §2): genre classification and
    # reference-track EQ moves used to be merged into one bucket with no
    # way to tell them apart -- an EQ move is a suggestion (blind-gate law),
    # not a measured fact, and the payload must say so.
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Reference Test.\n"
                "Structured reference EQ moves: Boost 2.5 dB around 8 kHz to match the reference's air."
            ),
        }
    ]

    payload = chat.answer_payload("How does this compare to my reference?", history=history, allow_llm=False)

    assert payload["route"] == "mix_review_followup"
    assert payload["contains_unvalidated_suggestions"] is True
    assert payload["grounding_mode"] == "strong"  # unchanged -- the response itself is still real


def test_mix_review_followup_genre_classification_alone_is_not_flagged() -> None:
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Genre Test.\n"
                "Structured genre classification: Genre: melodic techno (confidence 0.82)."
            ),
        }
    ]

    payload = chat.answer_payload("What genre does this compare to?", history=history, allow_llm=False)

    assert payload["route"] == "mix_review_followup"
    assert payload["contains_unvalidated_suggestions"] is False


def test_mix_review_followup_priority_actions_route_is_not_flagged() -> None:
    # A different branch of the same function (priority actions, not
    # reference notes) must never be flagged -- only the reference-notes
    # branch can contain an unvalidated EQ-move suggestion.
    history = [
        {
            "role": "user",
            "content": (
                "Mix Review Lab context for Priority Test.\n"
                "Structured priority actions: Dynamics: Ease limiter by 2 dB."
            ),
        }
    ]

    payload = chat.answer_payload("What should I fix first?", history=history, allow_llm=False)

    assert payload["route"] == "mix_review_followup"
    assert payload["contains_unvalidated_suggestions"] is False


def test_track_memory_lookup_uses_latest_session_report(monkeypatch) -> None:
    class FakeMixReview:
        @staticmethod
        def list_reviews(limit=200):
            return [
                {
                    "id": "abc123",
                    "title": "Neon Low End",
                    "session_report": {
                        "kenn_memory_lines": [
                            "Track: Neon Low End",
                            "Target: Club / electronic",
                            "Fix first: Add 808 harmonics for small speakers",
                            "Leave alone: Vocal brightness",
                        ]
                    },
                    "kenn_handoff": {},
                }
            ]

    monkeypatch.setattr(chat_routing, "mix_review", FakeMixReview)

    memory = chat.latest_track_memory_lookup("What should I fix in Neon Low End?")
    formatted = chat.format_track_memory(memory)

    assert memory["id"] == "abc123"
    assert "Add 808 harmonics" in formatted
    assert "Vocal brightness" in formatted


def test_answer_payload_exposes_query_route() -> None:
    assert answer_payload("How do I automate filter cutoff?", allow_llm=False)["route"] == "ableton"
    assert answer_payload("How do I fix muddy vocals?", allow_llm=False)["route"] == "production"
    assert answer_payload("How does Wwise handle game audio events?", allow_llm=False)["route"] == "game_audio"
    assert answer_payload("My Unity health RTPC is not changing the Wwise sound.", allow_llm=False)["route"] == "game_audio"
    assert answer_payload("Can sample-rate conversion make a Wwise ambience loop click?", allow_llm=False)["route"] == "game_audio"


def test_mix_review_timeline_lookup_keywords_and_matching(monkeypatch) -> None:
    # 1. No timeline keywords -> None
    assert chat.mix_review_timeline_lookup("How do I fix muddy vocals?") is None

    # Mock list_reviews
    mock_reviews = [
        {
            "id": "rev1",
            "title": "Track Alpha",
            "created_at": "2026-06-10 10:00:00",
            "version_label": "v1",
            "summary": "First mix.",
            "metrics": {"technical_score": 70, "peak_dbfs": -1.0},
        },
        {
            "id": "rev2",
            "title": "Track Alpha",
            "created_at": "2026-06-11 11:00:00",
            "version_label": "v2",
            "summary": "Second mix.",
            "metrics": {"technical_score": 85, "peak_dbfs": -2.0},
        },
        {
            "id": "rev3",
            "title": "Track Beta",
            "created_at": "2026-06-12 12:00:00",
            "version_label": "v1",
            "summary": "Beta version.",
            "metrics": {"technical_score": 90},
        }
    ]
    
    class FakeMixReview:
        @staticmethod
        def list_reviews(limit=50):
            return mock_reviews
            
    monkeypatch.setattr(chat_routing, "mix_review", FakeMixReview)
    
    # 2. Matching track Alpha timeline query
    res = chat.mix_review_timeline_lookup("show me the timeline of Track Alpha")
    assert res is not None
    title, timeline = res
    assert title == "Track Alpha"
    assert len(timeline) == 2
    assert timeline[0]["id"] == "rev1"
    assert timeline[1]["id"] == "rev2"
    
    # 3. Default to most recent track (Beta is most recent since 2026-06-12)
    res_default = chat.mix_review_timeline_lookup("show me the mix review history evolution")
    assert res_default is not None
    title_default, timeline_default = res_default
    assert title_default == "Track Beta"
    assert len(timeline_default) == 1
    assert timeline_default[0]["id"] == "rev3"
    
    # 4. format_timeline_report output
    report = chat.format_timeline_report(title, timeline)
    assert "# Mix Review Timeline: Track Alpha" in report
    assert "### Version: v1 (2026-06-10 10:00:00)" in report
    assert "- **Technical Score**: 70/100" in report
    assert "- **Summary**: First mix." in report
    
    # 5. answer_payload with timeline query bypasses weak checks and returns timeline
    payload = chat.answer_payload("timeline of Track Alpha", allow_llm=False)
    assert payload["route"] == "mix_review"
    assert payload["found"] is True
    assert payload["confidence"] == "high"
    assert "# Mix Review Timeline: Track Alpha" in payload["answer"]
    
    # 6. answer_payload_stream handles it too
    events = list(chat.answer_payload_stream("timeline of Track Alpha", allow_llm=False))
    assert len(events) >= 2
    assert events[0]["event"] == "metadata"
    assert events[0]["data"]["route"] == "mix_review"
    assert any("# Mix Review Timeline: Track Alpha" in str(evt.get("token")) for evt in events if evt["event"] == "token")


def test_stems_masking_context_routing_and_rewrite(monkeypatch) -> None:
    monkeypatch.delenv("KENN_LM_ENABLED", raising=False)
    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: True)
    
    called = []
    def mock_enhance(query, template, results, history, context_line, label, norm_history, answer_mode, route, timeline_context, skill_level=""):
        called.append(query)
        return """Short answer: The 45% kick and 50% bass clarity readings suggest masking.

Symptom and likely cause: The kick and bass are competing in the low end.

Try this:
1. Separate the kick and bass with level or EQ changes.
2. Re-run the masking analysis after each change.

Listening check: Compare the revised low end at matched loudness.

Sources:
- Stems Masking Analysis Context
"""
        
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", mock_enhance)
    
    query = "[Stems Masking Analysis Context]\n- Kick: 45% clarity\n- Bass: 50% clarity\n\nHow do I fix this?"
    
    ans, llm_used = chat.make_answer(query, results=[], allow_llm=True)

    assert llm_used is True
    assert "45% kick and 50% bass" in ans
    assert "Stems Masking Analysis Context" in ans
    assert len(called) == 1
    assert "Stems Masking" in called[0]


def test_audio_characterization_context_routing_and_rewrite(monkeypatch) -> None:
    monkeypatch.delenv("KENN_LM_ENABLED", raising=False)
    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: True)
    
    called = []
    def mock_enhance(query, template, results, history, context_line, label, norm_history, answer_mode, route, timeline_context, skill_level=""):
        called.append(query)
        return """Short answer: The supplied snare characterization reports a 0.1 DFS peak amplitude.

Symptom and likely cause: The characterization needs to be compared with the snare body and decay.

Try this:
1. Compare the peak with the body and decay of the snare.
2. Inspect the waveform before making a gain change.

Listening check: Match playback level before comparing it with another snare.

Sources:
- Audio Characterization Context
"""
        
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", mock_enhance)
    
    query = "[Audio Characterization: snare.wav]\n- Peak Amplitude: 0.1 DFS\n\nWhat is this?"
    
    ans, llm_used = chat.make_answer(query, results=[], allow_llm=True)

    assert llm_used is True
    assert "0.1 DFS peak amplitude" in ans
    assert "Audio Characterization Context" in ans
    assert len(called) == 1
    assert "Audio Characterization" in called[0]


def test_local_lm_cannot_bypass_weak_retrieval_gate(monkeypatch) -> None:
    monkeypatch.setenv("KENN_LM_ENABLED", "1")

    def fail_if_loaded():
        raise AssertionError("local LM must not run for weak retrieval")

    monkeypatch.setattr(chat_answer, "_get_kenn_lm", fail_if_loaded)
    answer, llm_used = chat.make_answer(
        "What tax deduction should I claim?",
        results=[],
        allow_llm=True,
    )

    assert llm_used is False
    assert answer


def test_low_quality_local_lm_answer_falls_back_to_grounded_template(monkeypatch) -> None:
    class WeakLocalLM:
        available = True

        @staticmethod
        def generate(*_args, **_kwargs):
            return "Maybe try changing some settings."

    monkeypatch.setenv("KENN_LM_ENABLED", "1")
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "0")
    monkeypatch.setattr(chat_answer, "_get_kenn_lm", lambda: WeakLocalLM())

    payload = chat.answer_payload(
        "How do I sidechain bass to a kick?",
        allow_llm=True,
    )

    assert payload["weak_match"] is False
    assert payload["llm_enhanced"] is False
    assert "sidechain" in payload["answer"].lower()
    assert "maybe try changing" not in payload["answer"].lower()
