"""Plan service with Claude and all repositories mocked."""

from __future__ import annotations

from services import plan_service


CANNED_RESULT = {
    "summary": "16-week build to a December marathon.",
    "plan": [
        {
            "date": "2026-05-28",
            "planned_sport": "running",
            "planned_workout_type": "easy",
            "planned_distance_km": 8.0,
            "planned_duration_minutes": 45,
            "planned_pace": "6:00/km",
            "intensity_zone": "Z2",
            "notes": "Conversational pace.",
        },
        {
            "date": "2026-05-29",
            "planned_sport": "running",
            "planned_workout_type": "rest",
            "planned_distance_km": None,
            "planned_duration_minutes": None,
            "planned_pace": None,
            "intensity_zone": "rest",
            "notes": "Full rest.",
        },
    ],
    "tokens_in": 1200,
    "tokens_out": 3400,
    "cost_usd": 0.09,
    "model": "claude-opus-4-7",
    "raw_output": {"summary": "…", "plan": []},
}


def _wire(monkeypatch, goal):
    monkeypatch.setattr(plan_service.goals_repo, "get_active", lambda: goal)
    monkeypatch.setattr(
        plan_service.claude_client,
        "generate_plan",
        lambda g, m, *a, **k: CANNED_RESULT,
    )
    monkeypatch.setattr(plan_service.training_plan_repo, "next_version", lambda: 3)

    captured = {}
    monkeypatch.setattr(
        plan_service.training_plan_repo,
        "insert_many",
        lambda rows: captured.update(rows=rows) or len(rows),
    )
    monkeypatch.setattr(
        plan_service.plan_revisions_repo,
        "insert",
        lambda **kw: captured.update(revision=kw),
    )
    return captured


def test_generate_initial_plan_writes_versioned_rows(monkeypatch):
    goal = {"id": "g1", "sport": "running", "race_date": "2026-12-06"}
    captured = _wire(monkeypatch, goal)

    result = plan_service.generate_initial_plan()

    assert result["ok"] is True
    assert result["version"] == 3
    assert result["count"] == 2

    rows = captured["rows"]
    assert all(r["version"] == 3 for r in rows)
    assert rows[0]["date"] == "2026-05-28"
    assert rows[0]["planned_distance_km"] == 8.0
    assert rows[1]["planned_distance_km"] is None


def test_generate_initial_plan_logs_revision(monkeypatch):
    goal = {"id": "g1", "sport": "running", "race_date": "2026-12-06"}
    captured = _wire(monkeypatch, goal)

    plan_service.generate_initial_plan()

    rev = captured["revision"]
    assert rev["trigger"] == "initial"
    assert rev["tokens_in"] == 1200
    assert rev["tokens_out"] == 3400
    assert rev["cost_usd"] == 0.09
    assert rev["claude_input"]["goal"] == goal


def test_generate_initial_plan_no_goal(monkeypatch):
    monkeypatch.setattr(plan_service.goals_repo, "get_active", lambda: None)
    result = plan_service.generate_initial_plan()
    assert result["ok"] is False
    assert "No active goal" in result["error"]


def test_generate_initial_plan_claude_failure(monkeypatch):
    goal = {"id": "g1", "sport": "running", "race_date": "2026-12-06"}
    monkeypatch.setattr(plan_service.goals_repo, "get_active", lambda: goal)

    def boom(*a, **k):
        raise RuntimeError("claude timeout")

    monkeypatch.setattr(plan_service.claude_client, "generate_plan", boom)
    result = plan_service.generate_initial_plan()
    assert result["ok"] is False
    assert "claude timeout" in result["error"]


def test_recalibrate_plan_writes_new_version(monkeypatch):
    from datetime import date

    goal = {"id": "g1", "sport": "running", "race_date": "2026-12-06", "goal_time_seconds": 14400}
    monkeypatch.setattr(plan_service.goals_repo, "get_active", lambda: goal)
    # latest plan has a remaining (today) entry so recalibration has something to revise
    monkeypatch.setattr(
        plan_service.training_plan_repo,
        "get_plan",
        lambda: [{"date": date.today().isoformat(), "planned_distance_km": 8, "version": 2}],
    )

    captured = {}
    monkeypatch.setattr(plan_service.training_plan_repo, "next_version", lambda: 3)
    monkeypatch.setattr(
        plan_service.training_plan_repo,
        "insert_many",
        lambda rows: captured.update(rows=rows) or len(rows),
    )
    monkeypatch.setattr(
        plan_service.plan_revisions_repo, "insert", lambda **kw: captured.update(revision=kw)
    )

    seen = {}
    monkeypatch.setattr(
        plan_service.claude_client,
        "recalibrate_plan",
        lambda g, cur, m, z, reason, *a, **k: seen.update(current=cur, reason=reason) or CANNED_RESULT,
    )

    result = plan_service.recalibrate_plan("low recovery")

    assert result["ok"] is True
    assert result["version"] == 3
    assert seen["reason"] == "low recovery"
    assert len(seen["current"]) == 1  # the remaining-plan entry was passed through
    assert captured["revision"]["trigger"] == "recalibration"


def test_recalibrate_plan_no_existing_plan(monkeypatch):
    goal = {"id": "g1", "sport": "running", "race_date": "2026-12-06"}
    monkeypatch.setattr(plan_service.goals_repo, "get_active", lambda: goal)
    monkeypatch.setattr(plan_service.training_plan_repo, "get_plan", lambda: [])
    result = plan_service.recalibrate_plan("test")
    assert result["ok"] is False
    assert "No current plan" in result["error"]


def test_recalibrate_claude_failure_preserves_existing_plan(monkeypatch):
    """Failure injection: when Claude fails during recalibration, no new
    version is written — the existing plan stays as the source of truth."""
    from datetime import date

    goal = {"id": "g1", "sport": "running", "race_date": "2026-12-06"}
    monkeypatch.setattr(plan_service.goals_repo, "get_active", lambda: goal)
    monkeypatch.setattr(
        plan_service.training_plan_repo,
        "get_plan",
        lambda: [{"date": date.today().isoformat(), "version": 2}],
    )

    writes = {"insert_many": 0, "revision": 0}
    monkeypatch.setattr(
        plan_service.training_plan_repo,
        "insert_many",
        lambda rows: writes.__setitem__("insert_many", writes["insert_many"] + 1) or len(rows),
    )
    monkeypatch.setattr(
        plan_service.plan_revisions_repo,
        "insert",
        lambda **kw: writes.__setitem__("revision", writes["revision"] + 1),
    )

    def boom(*a, **k):
        raise RuntimeError("claude timeout")

    monkeypatch.setattr(plan_service.claude_client, "recalibrate_plan", boom)

    result = plan_service.recalibrate_plan("test")

    assert result["ok"] is False
    assert "claude timeout" in result["error"]
    assert writes["insert_many"] == 0  # no new plan rows written
    assert writes["revision"] == 0  # no audit row either
