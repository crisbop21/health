"""Progress-test scheduling and result logging, with Claude and repos mocked."""

from __future__ import annotations

from services import test_service


def _wire(monkeypatch, goal, plan):
    monkeypatch.setattr(test_service.goals_repo, "get_active", lambda: goal)
    monkeypatch.setattr(test_service.training_plan_repo, "get_plan", lambda: plan)
    monkeypatch.setattr(
        test_service.claude_client,
        "schedule_tests",
        lambda g, window: {
            "tests": [
                {
                    "scheduled_date": "2026-07-15",
                    "test_type": "5K time trial",
                    "target_metric": "5K time",
                    "notes": "all-out 5K",
                },
                {
                    "scheduled_date": "2026-09-01",
                    "test_type": "long run benchmark",
                    "target_metric": "32 km time",
                    "notes": "steady",
                },
            ],
            "cost_usd": 0.02,
        },
    )
    captured = {}
    monkeypatch.setattr(test_service.progress_tests_repo, "delete_incomplete", lambda: captured.update(cleared=True))
    monkeypatch.setattr(
        test_service.progress_tests_repo,
        "insert_many",
        lambda rows: captured.update(rows=rows) or len(rows),
    )
    return captured


def test_schedule_progress_tests(monkeypatch):
    goal = {"race_date": "2026-12-06"}
    plan = [{"date": "2026-06-01"}, {"date": "2026-12-05"}]
    captured = _wire(monkeypatch, goal, plan)

    result = test_service.schedule_progress_tests()

    assert result["ok"] is True
    assert result["count"] == 2
    assert captured["cleared"] is True
    assert all(r["completed"] is False for r in captured["rows"])
    assert captured["rows"][0]["test_type"] == "5K time trial"


def test_schedule_no_goal(monkeypatch):
    monkeypatch.setattr(test_service.goals_repo, "get_active", lambda: None)
    result = test_service.schedule_progress_tests()
    assert result["ok"] is False
    assert "No active goal" in result["error"]


def test_schedule_no_plan(monkeypatch):
    monkeypatch.setattr(test_service.goals_repo, "get_active", lambda: {"race_date": "2026-12-06"})
    monkeypatch.setattr(test_service.training_plan_repo, "get_plan", lambda: [])
    result = test_service.schedule_progress_tests()
    assert result["ok"] is False
    assert "No plan" in result["error"]


def test_log_result(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        test_service.progress_tests_repo,
        "mark_complete",
        lambda tid, actual, notes=None: captured.update(tid=tid, actual=actual, notes=notes),
    )
    result = test_service.log_result("t1", "22:14", "felt strong")
    assert result["ok"] is True
    assert captured["tid"] == "t1"
    assert captured["actual"] == {"result": "22:14"}
    assert captured["notes"] == "felt strong"
