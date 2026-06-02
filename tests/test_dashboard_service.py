"""Dashboard coverage and series summaries, with the repos mocked."""

from __future__ import annotations

from services import dashboard_service
from repositories import daily_metrics_repo, workouts_repo

METRICS = [
    {"date": "2026-01-10", "hrv_ms": 60, "resting_hr": 48, "sleep_hours": 7.5,
     "recovery_score": 70, "strain": None, "source_hrv": "whoop", "source_sleep": "whoop"},
    {"date": "2026-01-11", "hrv_ms": None, "resting_hr": 50, "sleep_hours": None,
     "recovery_score": None, "strain": 12.0, "source_hrv": None, "source_sleep": None},
    {"date": "2026-01-12", "hrv_ms": 55, "resting_hr": None, "sleep_hours": 8.0,
     "recovery_score": 65, "strain": 9.0, "source_hrv": "garmin", "source_sleep": "garmin"},
]
WORKOUTS = [
    {"date": "2026-01-10", "sport": "running", "distance_km": 10.0},
    {"date": "2026-01-12", "sport": "running", "distance_km": 5.5},
    {"date": "2026-01-12", "sport": "cycling", "distance_km": 20.0},
]


def test_overview_summarizes_coverage(monkeypatch):
    monkeypatch.setattr(daily_metrics_repo, "get_range", lambda s, e: METRICS)
    monkeypatch.setattr(workouts_repo, "get_range", lambda s, e: WORKOUTS)

    result = dashboard_service.overview()

    assert result["ok"] is True
    m = result["metrics"]
    assert m["days"] == 3
    assert m["first"] == "2026-01-10"
    assert m["last"] == "2026-01-12"
    assert m["span_days"] == 3
    # hrv present on 2 of 3 days; strain on 2; resting_hr on 2.
    assert m["field_coverage"]["hrv_ms"] == 2
    assert m["field_coverage"]["strain"] == 2
    assert m["source_hrv"] == {"whoop": 1, "garmin": 1}

    w = result["workouts"]
    assert w["count"] == 3
    assert w["total_distance_km"] == 35.5
    assert w["by_sport"] == {"running": 2, "cycling": 1}


def test_overview_empty(monkeypatch):
    monkeypatch.setattr(daily_metrics_repo, "get_range", lambda s, e: [])
    monkeypatch.setattr(workouts_repo, "get_range", lambda s, e: [])

    result = dashboard_service.overview()

    assert result["ok"] is True
    assert result["metrics"]["days"] == 0
    assert result["metrics"]["first"] is None
    assert result["workouts"]["total_distance_km"] == 0


def test_overview_handles_failure(monkeypatch):
    def boom(s, e):
        raise RuntimeError("db down")

    monkeypatch.setattr(daily_metrics_repo, "get_range", boom)
    result = dashboard_service.overview()
    assert result["ok"] is False
    assert "db down" in result["error"]


def test_series_use_window(monkeypatch):
    captured = {}

    def fake_metrics(s, e):
        captured["metrics_start"] = s
        return METRICS

    def fake_workouts(s, e):
        captured["workouts_start"] = s
        return WORKOUTS

    monkeypatch.setattr(daily_metrics_repo, "get_range", fake_metrics)
    monkeypatch.setattr(workouts_repo, "get_range", fake_workouts)

    assert dashboard_service.metrics_series(days=30) == METRICS
    assert dashboard_service.workouts_series(days=30) == WORKOUTS
    # Both start dates are 30 days back, not the epoch floor used by overview.
    assert captured["metrics_start"] > "2000-01-01"
    assert captured["workouts_start"] > "2000-01-01"
