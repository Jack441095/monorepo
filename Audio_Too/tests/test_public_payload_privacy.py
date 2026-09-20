"""Public/demo payloads expose only intentional fields."""

from __future__ import annotations

import demo_routes
import portfolio


def test_demo_analytics_excludes_row_level_data() -> None:
    result = demo_routes.safe_demo_analytics(
        {
            "total_recent_questions": 3,
            "questions": [{"question": "private client question"}],
            "feedback": [{"comment": "private comment"}],
            "sessions": [{"session_id": "private"}],
        }
    )
    assert result["total_recent_questions"] == 3
    assert "questions" not in result
    assert "feedback" not in result
    assert "sessions" not in result


def test_portfolio_uses_field_and_audio_path_allowlists(monkeypatch, tmp_path) -> None:
    path = tmp_path / "portfolio.json"
    path.write_text(
        '{"codebases":[{"title":"Tool","private_path":"/Users/client"}],'
        '"stats":[{"value":"1","label":"Project","email":"private@example.com"}],'
        '"audio":[{"title":"Safe","src":"/portfolio/audio/safe.wav","path":"/private/safe.wav"},'
        '{"title":"Unsafe","src":"file:///private/client.wav"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(portfolio, "PORTFOLIO_PATH", path)
    result = portfolio.load_portfolio()
    assert result["codebases"] == [{"type": None, "title": "Tool", "description": None, "tags": None}]
    assert result["stats"] == [{"value": "1", "label": "Project"}]
    assert result["audio"] == [{"title": "Safe", "description": None, "src": "/portfolio/audio/safe.wav"}]
