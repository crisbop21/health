"""Planned-vs-actual adherence: weekly km comparison and completed-day
detection, with repos mocked."""

from __future__ import annotations

from datetime import date, timedelta

from repositories import training_plan_repo, workouts_repo
from services import plan_service


def _monday(weeks_ago: int) -> date:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(weeks=weeks_ago)


def test_adherence_weekly_planned_vs_actual(monkeypatch):
    wk1, wk0 = _monday(1), _monday(0)
    plan = [
        # Last week: 10 km planned Monday, 8 km Wednesday.
        {"date": wk1.isoformat(), "planned_distance_km": 10},
        {"date": (wk1 + timedelta(days=2)).isoformat(), "planned_distance_km": 8},
        # This week, today or earlier: 5 km.
        {"date": wk0.isoformat(), "planned_distance_km": 5},
        # Future days must not count against adherence yet.
        {"date": (date.today() + timedelta(days=1)).isoformat(), "planned_distance_km": 30},
    ]
    workouts = [
        {"date": wk1.isoformat(), "sport": "running", "distance_km": 10.5},
        {"date": (wk1 + timedelta(days=2)).isoformat(), "sport": "running", "distance_km": 4.0},
    ]
    monkeypatch.setattr(training_plan_repo, "get_plan", lambda: plan)
    monkeypatch.setattr(workouts_repo, "get_range", lambda s, e: workouts)

    result = plan_service.adherence(weeks=4)

    assert result["ok"] is True
    by_week = {r["week"]: r for r in result["weeks"]}
    last = by_week[wk1.isoformat()]
    assert last["planned_km"] == 18.0
    assert last["actual_km"] == 14.5
    assert last["planned_days"] == 2
    assert last["active_days"] == 2
    # Overall: 14.5 of 23 planned km so far (future 30 km excluded).
    assert result["planned_km"] == 23.0
    assert result["actual_km"] == 14.5
    assert result["adherence_pct"] == 63
    assert set(result["completed_dates"]) == {w["date"] for w in workouts}


def test_adherence_with_no_plan(monkeypatch):
    monkeypatch.setattr(training_plan_repo, "get_plan", lambda: [])
    monkeypatch.setattr(workouts_repo, "get_range", lambda s, e: [])
    result = plan_service.adherence()
    assert result["ok"] is True
    assert result["weeks"] == []
    assert result["adherence_pct"] is None


def test_adherence_survives_failure(monkeypatch):
    monkeypatch.setattr(
        training_plan_repo, "get_plan", lambda: (_ for _ in ()).throw(RuntimeError("db"))
    )
    result = plan_service.adherence()
    assert result["ok"] is False
