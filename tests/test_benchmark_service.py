"""Race-time benchmarking: Riegel equivalents, "if race day were today"
projections, the weekly fitness curve, and personal records — with the
workouts and goals repos mocked."""

from __future__ import annotations

from datetime import date, timedelta

from core import pace_zones
from repositories import goals_repo, workouts_repo
from services import benchmark_service


def _run(days_ago: int, km: float, seconds: int, sport: str = "running") -> dict:
    return {
        "date": (date.today() - timedelta(days=days_ago)).isoformat(),
        "sport": sport,
        "distance_km": km,
        "duration_seconds": seconds,
        "source": "garmin",
    }


GOAL = {"race_date": "2026-12-06", "goal_time_seconds": 3 * 3600 + 45 * 60,
        "race_distance_km": 42.195, "sport": "running"}


def _wire(monkeypatch, workouts, goal=GOAL):
    monkeypatch.setattr(workouts_repo, "get_range", lambda s, e: workouts)
    monkeypatch.setattr(goals_repo, "get_active", lambda: goal)


# --- Model math -------------------------------------------------------------

def test_riegel_scales_with_distance():
    # A 50:00 10K predicts ~1:50:30 for a half (ratio 2.11^1.06).
    half = benchmark_service.riegel(3000, 10.0, 21.0975)
    assert 6550 < half < 6700
    # Same distance -> same time.
    assert benchmark_service.riegel(3000, 10.0, 10.0) == 3000


def test_format_duration():
    assert pace_zones.format_duration(48 * 60 + 12) == "48:12"
    assert pace_zones.format_duration(3 * 3600 + 45 * 60) == "3:45:00"
    assert pace_zones.format_duration(None) is None


def test_confidence_tiers():
    assert benchmark_service._confidence(18.0, 21.0975) == "high"
    assert benchmark_service._confidence(10.0, 21.0975) == "medium"
    assert benchmark_service._confidence(5.0, 42.195) == "low"


def test_best_projection_prefers_closest_distance_evidence():
    # A slowish 30 km run is better marathon evidence than a fast 5K.
    runs = [_run(3, 5.0, 1200), _run(10, 30.0, 9900)]
    best = benchmark_service._best_projection(runs, 42.195)
    assert best["source"]["distance_km"] == 30.0
    assert best["confidence"] == "high"


def test_best_projection_falls_back_to_lower_confidence():
    runs = [_run(3, 6.0, 1500)]
    best = benchmark_service._best_projection(runs, 42.195)
    assert best["confidence"] == "low"
    assert best["projected_seconds"] > 1500


# --- Projections ------------------------------------------------------------

def test_race_projections_covers_three_targets_with_goal_delta(monkeypatch):
    # 90:00 for 18 km (5:00/km) two weeks ago; a short jog that shouldn't count.
    _wire(monkeypatch, [_run(14, 18.0, 5400), _run(2, 3.0, 1200)])

    result = benchmark_service.race_projections()

    assert result["ok"] is True
    assert result["runs_considered"] == 1
    by_label = {p["label"]: p for p in result["projections"]}
    assert set(by_label) == {"10K", "Half marathon", "Marathon"}
    mar = by_label["Marathon"]
    assert mar["projected_seconds"] > 5400
    assert mar["source"]["distance_km"] == 18.0
    # Goal is a marathon -> only the marathon projection carries the delta.
    assert mar["goal_seconds"] == GOAL["goal_time_seconds"]
    assert mar["delta_seconds"] == mar["projected_seconds"] - GOAL["goal_time_seconds"]
    assert by_label["10K"].get("goal_seconds") is None


def test_race_projections_without_runs_or_goal(monkeypatch):
    _wire(monkeypatch, [], goal=None)
    result = benchmark_service.race_projections()
    assert result["ok"] is True
    assert all(p.get("projected_seconds") is None for p in result["projections"])


def test_race_projections_only_counts_runs(monkeypatch):
    _wire(monkeypatch, [_run(5, 40.0, 5000, sport="cycling")])
    assert benchmark_service.race_projections()["runs_considered"] == 0


def test_race_projections_handles_failure(monkeypatch):
    monkeypatch.setattr(
        workouts_repo, "get_range", lambda s, e: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    result = benchmark_service.race_projections()
    assert result["ok"] is False


# --- Fitness curve ----------------------------------------------------------

def test_projection_history_improves_as_runs_get_faster(monkeypatch):
    # Same 10 km distance, 50:00 ten weeks ago vs 45:00 last week.
    _wire(monkeypatch, [_run(70, 10.0, 3000), _run(7, 10.0, 2700)])

    result = benchmark_service.projection_history(target_km=10.0, weeks=12)

    assert result["ok"] is True
    rows = result["rows"]
    assert len(rows) >= 2
    assert rows[-1]["projected_seconds"] < rows[0]["projected_seconds"]


# --- Personal records -------------------------------------------------------

def test_personal_records(monkeypatch):
    runs = [
        _run(30, 10.2, 2820),   # ~46:09 for 10.2 km -> 10K PR source
        _run(200, 21.5, 6600),  # half PR source
        _run(60, 32.0, 11520),  # longest run
        _run(60, 12.0, 4000),   # same day as the 32 km -> biggest week 44 km
    ]
    _wire(monkeypatch, runs)

    result = benchmark_service.personal_records()

    assert result["ok"] is True
    recs = result["records"]
    assert recs["10K"]["seconds"] < 2820  # downscaled from 10.2 km
    assert recs["10K"]["date"] == runs[0]["date"]
    assert recs["Half marathon"]["seconds"] < 6600
    assert recs["Marathon"] is None  # no run long enough
    assert result["longest_run"]["distance_km"] == 32.0
    assert result["biggest_week_km"] == 44.0
    assert result["total_runs"] == 4
