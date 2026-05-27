"""Q&A and daily-status services, with Claude and repos mocked."""

from __future__ import annotations

from datetime import date

from services import qa_service


def _wire_context(monkeypatch):
    monkeypatch.setattr(qa_service.goals_repo, "get_active", lambda: {"sport": "running"})
    monkeypatch.setattr(qa_service.daily_metrics_repo, "get_recent", lambda n: [{"hrv_ms": 58}])
    monkeypatch.setattr(
        qa_service.training_plan_repo,
        "get_plan",
        lambda: [{"date": date.today().isoformat(), "planned_workout_type": "easy"}],
    )


def test_ask_returns_answer_and_logs(monkeypatch):
    _wire_context(monkeypatch)
    monkeypatch.setattr(
        qa_service.claude_client,
        "ask",
        lambda q, ctx: {
            "answer": "Training is on track.",
            "tokens_in": 10,
            "tokens_out": 20,
            "cost_usd": 0.001,
            "model": "claude-opus-4-7",
        },
    )
    logged = {}
    monkeypatch.setattr(
        qa_service.qa_log_repo,
        "insert",
        lambda q, a, context_sent=None, **kw: logged.update(q=q, a=a, ctx=context_sent),
    )

    result = qa_service.ask("How is my training?")

    assert result["ok"] is True
    assert result["answer"] == "Training is on track."
    assert logged["q"] == "How is my training?"
    assert logged["ctx"]["recent_metrics"] == [{"hrv_ms": 58}]


def test_ask_claude_failure(monkeypatch):
    _wire_context(monkeypatch)

    def boom(q, ctx):
        raise RuntimeError("api down")

    monkeypatch.setattr(qa_service.claude_client, "ask", boom)
    result = qa_service.ask("anything")
    assert result["ok"] is False
    assert "api down" in result["error"]


def test_daily_status(monkeypatch):
    today = date.today().isoformat()
    monkeypatch.setattr(qa_service.goals_repo, "get_active", lambda: {"sport": "running"})
    monkeypatch.setattr(
        qa_service.training_plan_repo,
        "get_plan",
        lambda: [{"date": today, "planned_workout_type": "tempo"}],
    )
    monkeypatch.setattr(
        qa_service.daily_metrics_repo, "get_recent", lambda n: [{"recovery_score": 70}]
    )
    monkeypatch.setattr(
        qa_service.claude_client,
        "daily_status",
        lambda goal, item, last: {"status": "Recovery is solid — hit the tempo.", "cost_usd": 0.0},
    )

    result = qa_service.daily_status()

    assert result["ok"] is True
    assert "tempo" in result["status"]
    assert result["today_item"]["planned_workout_type"] == "tempo"
    assert result["last_metrics"]["recovery_score"] == 70
