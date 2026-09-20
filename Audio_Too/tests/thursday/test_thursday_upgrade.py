from __future__ import annotations

import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "server" / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "app"))
if str(ROOT / "business") not in sys.path:
    sys.path.insert(0, str(ROOT / "business"))

from thursday import client
from thursday.formatter import format_response, suggest_follow_ups
from thursday.intent import classify_intent, resolve_entities
from thursday.orchestrator import handle
from thursday import orchestrator
from thursday.resolver import resolve_request
from thursday import session_manager


class ThursdayUpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(session_manager, "SESSION_DIR", root / "sessions"),
            patch.object(session_manager, "SESSION_FILE", root / ".session"),
            patch("thursday.orchestrator.should_check", return_value=False),
            patch("thursday.orchestrator.get_pending_alerts", return_value=[]),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    @staticmethod
    def records(table: str) -> list[dict]:
        if table == "clients":
            return [{"id": "client-1", "name": "Jordan", "email": "j@example.com"}]
        if table == "projects":
            return [{"client": "Jordan", "project": "EP Mix", "service": "Mixing", "status": "Open", "id": "p1"}]
        return []

    def test_context_chain_persists_client_and_both_roles(self) -> None:
        session = session_manager.new_session()
        with (
            patch("thursday.client.client_summary", return_value="Client: Jordan"),
            patch("thursday.client.admin_agent", return_value="Invoice drafted") as admin,
        ):
            first = handle("tell me about Jordan", session, self.records)
            second = handle("ask Adam to draft an invoice for her", session, self.records)

        self.assertIn("Client: Jordan", first)
        self.assertIn("Invoice drafted", second)
        self.assertIn("Jordan", admin.call_args.args[1])
        loaded = session_manager.load_session(session["session_id"])
        self.assertEqual("Jordan", loaded["context"]["current_client"])
        self.assertEqual("client_info", loaded["context"]["last_report"])
        self.assertEqual(["user", "thursday", "user", "thursday"], [t["role"] for t in loaded["turns"]])

    def test_intent_resolution_and_specific_routing_inputs(self) -> None:
        resolved, entities = resolve_request("send her an invoice", {"current_client": "Jordan"})
        self.assertEqual("send Jordan an invoice", resolved)
        self.assertEqual("Jordan", entities["current_client"])
        self.assertEqual("agent_tasks", classify_intent(resolved).name)
        self.assertEqual("audio_generation", classify_intent("render a joyful full song").name)
        self.assertEqual("Jordan", resolve_entities("send her an invoice", {"current_client": "Jordan"})["current_client"])

    def test_generic_questions_are_not_misrouted_to_kenn(self) -> None:
        self.assertEqual("unknown", classify_intent("how can I improve my website?").name)
        self.assertEqual("production_qa", classify_intent("how can I improve my vocal mix?").name)
        self.assertEqual("kenn_voice_mode", classify_intent("Could you send me to Ken please?").name)

    def test_weather_is_a_real_intent_not_generic_chitchat(self) -> None:
        # 2026-08-07: weather has a real, working service now (utility_tools.py,
        # Open-Meteo) — this used to be the routing test's own example of
        # "generic chit-chat that must not be misrouted to KENN"; now it should
        # route to the weather service instead of falling through as unknown.
        self.assertEqual("weather", classify_intent("what is the weather tomorrow?").name)

    def test_kenn_followup_inherits_intent_and_receives_history(self) -> None:
        session = session_manager.new_session()
        with patch("thursday.client.ask_kenn", side_effect=["Use sidechain compression", "Match the release to tempo"]) as kenn:
            handle("how do I sidechain my bass?", session, self.records)
            result = handle("why does that matter?", session, self.records)

        self.assertIn("Match the release to tempo", result)
        self.assertEqual(2, kenn.call_count)
        self.assertTrue(kenn.call_args.kwargs["history"])
        self.assertEqual(session["session_id"], kenn.call_args.kwargs["session_id"])

    def test_production_question_does_not_receive_routine_alert_or_briefing(self) -> None:
        session = session_manager.new_session()
        alert = {"id": "a1", "severity": "warning", "message": "One stale lead"}
        with (
            patch("thursday.orchestrator.get_pending_alerts", return_value=[alert]),
            patch("thursday.orchestrator.acknowledge_all") as acknowledge,
            patch(
                "thursday.orchestrator.daily_brief.build_daily_brief",
                return_value=({}, "BUSINESS BRIEFING"),
            ),
            patch("thursday.client.ask_kenn", return_value="Compress the vocal gently"),
        ):
            result = handle("how should I compress a vocal?", session, self.records)

        self.assertIn("Compress the vocal gently", result)
        self.assertNotIn("One stale lead", result)
        self.assertNotIn("BUSINESS BRIEFING", result)
        acknowledge.assert_not_called()

    def test_session_load_migrates_context_and_rejects_traversal(self) -> None:
        session_manager.SESSION_DIR.mkdir(parents=True)
        path = session_manager.SESSION_DIR / "old.json"
        path.write_text(json.dumps({"session_id": "old", "turns": [], "context": {}}))
        loaded = session_manager.load_session("old")
        self.assertIn("current_mix_review", loaded["context"])
        self.assertIn("feedback_state", loaded)
        self.assertIsNone(session_manager.load_session("../outside"))

    def test_implicit_feedback_is_isolated_between_concurrent_sessions(self) -> None:
        first = session_manager.get_or_create_session("feedback-a")
        second = session_manager.get_or_create_session("feedback-b")
        session_manager.add_turn(first, "thursday", "Answer A", "business_ops", "business_status", {})
        session_manager.add_turn(second, "thursday", "Answer B", "production_qa", "kenn", {})
        captured = []

        def capture_feedback(**kwargs):
            captured.append(kwargs)
            return kwargs

        with patch("thursday.orchestrator.record_feedback", side_effect=capture_feedback):
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(
                    lambda item: orchestrator._record_session_feedback(*item),
                    ((first, "Follow-up A"), (second, "Follow-up B")),
                ))

        assert {item["session_id"] for item in captured} == {"feedback-a", "feedback-b"}
        by_session = {item["session_id"]: item for item in captured}
        assert by_session["feedback-a"]["service_id"] == "business_status"
        assert by_session["feedback-a"]["response_text"] == "Answer A"
        assert by_session["feedback-b"]["service_id"] == "kenn"
        assert by_session["feedback-b"]["response_text"] == "Answer B"
        assert first["feedback_state"]["recorded"] is True
        assert second["feedback_state"]["recorded"] is True

    def test_monitor_is_marked_even_when_no_alerts_are_found(self) -> None:
        session = session_manager.new_session()
        with (
            patch("thursday.orchestrator.should_check", return_value=True),
            patch("thursday.orchestrator.run_checks", return_value=[]),
            patch("thursday.orchestrator.mark_checked") as marked,
            patch("thursday.client.business_status", return_value="All good"),
        ):
            handle("how's business", session, self.records)
        marked.assert_called_once_with()

    def test_structured_client_and_formatter_contract(self) -> None:
        api = client.APIClient(list_records_func=lambda kind: [{"kind": kind}])
        result = api.list_records("clients")
        self.assertEqual({"ok", "data", "error"}, set(result))
        rendered = format_response(result, "Records", "sessions", {})
        self.assertIn("Kind: clients", rendered)
        self.assertIn("**Try next:**", rendered)
        self.assertTrue(suggest_follow_ups("financial", result, {}))
        self.assertIn("**Try next:**", format_response(result, "Records", {}))

    def test_formatter_does_not_duplicate_kenn_followups(self) -> None:
        rendered = format_response(
            "Short answer: Use less gain.\n\nYou could also ask:\n- How much?",
            "KENN Knowledge Base",
            "kenn",
            {},
        )
        self.assertEqual(1, rendered.lower().count("you could also ask:"))
        self.assertNotIn("**Try next:**", rendered)

    def test_business_insight_filters_paid_revenue(self) -> None:
        def records(table: str) -> list[dict]:
            if table == "invoices":
                return [
                    {"status": "Paid", "service": "Mixing", "total": "500", "paid_at": "2026-02-01"},
                    {"status": "Paid", "service": "Mastering", "total": "200", "paid_at": "2026-02-03"},
                    {"status": "Draft", "service": "Mastering", "total": "900", "created_at": "2026-02-04"},
                ]
            return []

        session = session_manager.new_session()
        result = handle("what's the most profitable service in 2026?", session, records)
        self.assertIn("Mixing (£500.00 paid revenue)", result)

    def test_alerts_are_acknowledged_after_delivery(self) -> None:
        session = session_manager.new_session()
        alert = {"id": "a1", "severity": "warning", "message": "One stale lead"}
        with (
            patch("thursday.orchestrator.get_pending_alerts", return_value=[alert]),
            patch("thursday.orchestrator.acknowledge_all") as acknowledge,
            patch("thursday.client.business_status", return_value="All good"),
        ):
            rendered = handle("how's business", session, self.records)
        self.assertIn("One stale lead", rendered)
        acknowledge.assert_called_once_with()

    def test_sqlite_session_store_direct(self) -> None:
        import sqlite3
        session = session_manager.get_or_create_session("sqlite-direct")
        session_manager.update_context(session, {"current_client": "Jack"})
        
        # Verify db file is created
        db_path = session_manager.SESSION_DIR / "thursday_sessions.sqlite3"
        self.assertTrue(db_path.exists())
        
        # Query db file directly to verify contents
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT state FROM assistant_sessions WHERE session_id = 'sqlite-direct'").fetchone()
        self.assertIsNotNone(row)
        data = json.loads(row[0])
        self.assertEqual("Jack", data["context"]["current_client"])
        conn.close()

    def test_audiogen_render_chains_to_automix(self) -> None:
        session = session_manager.new_session()
        captured_kwargs = {}

        def fake_render_full_song(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "ok": True,
                "job": {
                    "id": "job-12345",
                    "status": "queued",
                    "emotion": kwargs.get("emotion"),
                    "bars": kwargs.get("bars"),
                },
            }

        with (
            patch("thursday.client.audiogen_infer_emotion", return_value="joy"),
            patch("thursday.client.audiogen_render_full_song", side_effect=fake_render_full_song),
        ):
            first_response = handle(
                "generate drums and bassline, then render an automix pass from these",
                session,
                self.records,
            )
            self.assertIn("confirm", first_response)

            import re
            m = re.search(r"confirm\s+([A-Za-z0-9_.:-]+)", first_response)
            self.assertTrue(m)
            token = m.group(1)

            second_response = handle(
                f"confirm {token}",
                session,
                self.records,
            )

        self.assertIn("Full song render queued!", second_response)
        self.assertIn("AutoMix: Chained", second_response)
        self.assertTrue(captured_kwargs.get("chain_to_automix"))
        self.assertTrue(captured_kwargs.get("project_id").startswith("kenn-"))


if __name__ == "__main__":
    unittest.main()
