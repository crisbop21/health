"""Structural guardrail checks on generated plans."""

from __future__ import annotations

from core import guardrails


def test_blackout_violation_flagged():
    goal = {"race_date": "2026-12-06", "blackout_dates": ["2026-06-08"]}
    plan = [
        {"date": "2026-06-08", "planned_workout_type": "long", "planned_distance_km": 20},
    ]
    warnings = guardrails.check_plan(plan, goal)
    assert any(w["type"] == "blackout" and w["date"] == "2026-06-08" for w in warnings)


def test_rest_on_blackout_is_fine():
    goal = {"race_date": "2026-12-06", "blackout_dates": ["2026-06-08"]}
    plan = [{"date": "2026-06-08", "planned_workout_type": "rest", "planned_distance_km": None}]
    warnings = guardrails.check_plan(plan, goal)
    assert not any(w["type"] == "blackout" for w in warnings)


def test_mileage_jump_flagged():
    goal = {"race_date": "2026-12-06", "blackout_dates": []}
    plan = [
        {"date": "2026-06-01", "planned_workout_type": "easy", "planned_distance_km": 10},
        {"date": "2026-06-08", "planned_workout_type": "long", "planned_distance_km": 20},
    ]
    warnings = guardrails.check_plan(plan, goal)
    assert any(w["type"] == "mileage_jump" for w in warnings)


def test_modest_increase_not_flagged():
    goal = {"race_date": "2026-12-06", "blackout_dates": []}
    plan = [
        {"date": "2026-06-01", "planned_workout_type": "easy", "planned_distance_km": 10},
        {"date": "2026-06-08", "planned_workout_type": "long", "planned_distance_km": 11},
    ]
    warnings = guardrails.check_plan(plan, goal)
    assert not any(w["type"] == "mileage_jump" for w in warnings)


def test_taper_increase_flagged():
    goal = {"race_date": "2026-06-22", "blackout_dates": []}
    plan = [
        {"date": "2026-06-01", "planned_workout_type": "long", "planned_distance_km": 10},
        {"date": "2026-06-08", "planned_workout_type": "long", "planned_distance_km": 15},
        {"date": "2026-06-15", "planned_workout_type": "long", "planned_distance_km": 20},
    ]
    warnings = guardrails.check_plan(plan, goal)
    assert any(w["type"] == "taper" for w in warnings)


def test_expand_blackouts_handles_range():
    expanded = guardrails._expand_blackouts(
        [{"start": "2026-07-01", "end": "2026-07-03"}, "2026-08-15"]
    )
    assert expanded == {"2026-07-01", "2026-07-02", "2026-07-03", "2026-08-15"}
