"""Goal summary (the persistent race header) and the onboarding checklist,
with repos/services mocked."""

from __future__ import annotations

from datetime import date, timedelta

from repositories import goals_repo
from services import (
    dashboard_service,
    goal_service,
    onboarding_service,
    plan_service,
    sync_service,
)


# --- Race summary -----------------------------------------------------------

def test_race_summary(monkeypatch):
    race = (date.today() + timedelta(days=170)).isoformat()
    monkeypatch.setattr(
        goals_repo, "get_active",
        lambda: {"sport": "running", "race_date": race,
                 "goal_time_seconds": 13500, "race_distance_km": 42.195},
    )

    s = goal_service.race_summary()

    assert s["ok"] is True
    assert s["race_date"] == race
    assert s["days_to_race"] == 170
    assert s["weeks_to_race"] == 24
    assert s["goal_time"] == "3:45:00"
    assert s["distance_label"] == "Marathon"


def test_race_summary_without_goal(monkeypatch):
    monkeypatch.setattr(goals_repo, "get_active", lambda: None)
    s = goal_service.race_summary()
    assert s["ok"] is True
    assert s["race_date"] is None


def test_race_summary_survives_failure(monkeypatch):
    monkeypatch.setattr(
        goals_repo, "get_active", lambda: (_ for _ in ()).throw(RuntimeError("db"))
    )
    s = goal_service.race_summary()
    assert s["ok"] is True  # header silently disappears, never breaks a page
    assert s["race_date"] is None


def test_distance_label_falls_back_to_km(monkeypatch):
    monkeypatch.setattr(
        goals_repo, "get_active",
        lambda: {"race_date": "2026-12-06", "goal_time_seconds": 3600,
                 "race_distance_km": 15.0},
    )
    assert goal_service.race_summary()["distance_label"] == "15 km"


# --- Onboarding -------------------------------------------------------------

def _wire_onboarding(monkeypatch, *, whoop=True, garmin_rows=100, metric_days=200,
                     goal=True, plan_rows=1):
    monkeypatch.setattr(
        sync_service, "device_status",
        lambda: {"garmin": {"last_sync": "x", "rows": garmin_rows},
                 "whoop": {"connected": whoop, "last_sync": "x", "rows": 10,
                           "token_expires_at": None}},
    )
    monkeypatch.setattr(
        dashboard_service, "overview",
        lambda: {"ok": True, "metrics": {"days": metric_days},
                 "workouts": {"count": 5}},
    )
    monkeypatch.setattr(
        goals_repo, "get_active", lambda: {"race_date": "2026-12-06"} if goal else None
    )
    monkeypatch.setattr(
        plan_service, "current_plan",
        lambda: {"ok": True, "rows": [{"date": "2026-06-12"}] * plan_rows},
    )


def test_onboarding_complete(monkeypatch):
    _wire_onboarding(monkeypatch)
    result = onboarding_service.status()
    assert result["ok"] is True
    assert result["complete"] is True
    assert all(s["done"] for s in result["steps"])


def test_onboarding_flags_missing_steps(monkeypatch):
    _wire_onboarding(monkeypatch, whoop=False, metric_days=0, plan_rows=0)
    result = onboarding_service.status()
    assert result["complete"] is False
    by_key = {s["key"]: s["done"] for s in result["steps"]}
    assert by_key["whoop"] is False
    assert by_key["history"] is False
    assert by_key["plan"] is False
    assert by_key["garmin"] is True
    assert by_key["goal"] is True


def test_onboarding_survives_failures(monkeypatch):
    monkeypatch.setattr(
        sync_service, "device_status", lambda: (_ for _ in ()).throw(RuntimeError("db"))
    )
    monkeypatch.setattr(
        dashboard_service, "overview", lambda: {"ok": False, "error": "db"}
    )
    monkeypatch.setattr(
        goals_repo, "get_active", lambda: (_ for _ in ()).throw(RuntimeError("db"))
    )
    monkeypatch.setattr(plan_service, "current_plan", lambda: {"ok": False, "rows": []})

    result = onboarding_service.status()

    assert result["ok"] is True  # checklist renders with everything not-done
    assert result["complete"] is False
