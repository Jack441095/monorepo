import pytest

from kenn.core import chat_routing
from kenn.llm import llm_rewrite

# Wording that no keyword route claims, so route_query reaches its model fallback.
UNROUTABLE = "the harbour lights flicker whenever the tide turns"


def _count_model_routes(monkeypatch) -> list[str]:
    asked: list[str] = []

    def fake_route(query: str) -> str:
        asked.append(query)
        return "production"

    monkeypatch.setattr(llm_rewrite, "llm_route_query", fake_route)
    return asked


def test_the_model_free_foreground_answer_never_asks_the_model_for_a_route(monkeypatch) -> None:
    # On 2 Oct 2026 the 30-question runs showed route_query ignoring allow_llm, so the answer promised to be
    # model-free could still wait up to 20 s on a routing call.
    asked = _count_model_routes(monkeypatch)

    assert chat_routing.route_query(UNROUTABLE, None, allow_llm=False) == "unknown"
    assert asked == []


def test_routing_still_asks_the_model_when_a_model_is_allowed(monkeypatch) -> None:
    asked = _count_model_routes(monkeypatch)

    assert chat_routing.route_query(UNROUTABLE, None) == "production"
    assert asked == [UNROUTABLE]


@pytest.mark.parametrize("allow_llm", [False, True])
@pytest.mark.parametrize("query", [
    "Explain precedence effect.",
    "Explain phantom power.",
    "Explain balanced cabling.",
    "Explain the PRECEDENCE effect.",
    "Explain phantom   power.",
    "Explain balanced audio connections.",
])
def test_audio_fundamentals_reach_knowledge_without_a_model_route(monkeypatch, query, allow_llm) -> None:
    # These engineering questions missed the keyword route and could receive an unrelated fallback reply.
    asked = _count_model_routes(monkeypatch)

    assert chat_routing.route_query(query, allow_llm=allow_llm) == "production"
    assert asked == []


@pytest.mark.parametrize("query", [
    "Explain precedence.",
    "Explain phantom limbs.",
    "Explain a balanced diet.",
    "Explain counterbalanced cabling.",
])
def test_audio_fundamental_routes_do_not_claim_partial_or_non_audio_terms(monkeypatch, query) -> None:
    asked = _count_model_routes(monkeypatch)

    assert chat_routing.route_query(query, allow_llm=False) != "production"
    assert asked == []
