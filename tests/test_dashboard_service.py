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


def test_snapshot_latest_and_delta(monkeypatch):
    # Latest HRV is 70; the prior week averages (60+50)/2 = 55 -> delta +15.
    rows = [
        {"date": "2026-01-05", "hrv_ms": 60, "resting_hr": 50},
        {"date": "2026-01-08", "hrv_ms": 50, "resting_hr": 52},
        {"date": "2026-01-11", "hrv_ms": 70, "resting_hr": 47},
    ]
    monkeypatch.setattr(daily_metrics_repo, "get_range", lambda s, e: rows)

    result = dashboard_service.snapshot()

    assert result["ok"] is True
    hrv = result["metrics"]["hrv_ms"]
    assert hrv["latest"] == 70
    assert hrv["date"] == "2026-01-11"
    assert hrv["baseline"] == 55.0
    assert hrv["delta"] == 15.0
    # A field with no data reports None cleanly.
    assert result["metrics"]["sleep_hours"]["latest"] is None


def test_snapshot_single_reading_has_no_delta(monkeypatch):
    monkeypatch.setattr(
        daily_metrics_repo, "get_range", lambda s, e: [{"date": "2026-01-11", "strain": 12.0}]
    )
    result = dashboard_service.snapshot()
    assert result["metrics"]["strain"]["latest"] == 12.0
    assert result["metrics"]["strain"]["delta"] is None


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


def test_series_all_history(monkeypatch):
    """days=None means everything: the dashboard's "All" period queries from
    the epoch floor instead of a rolling window."""
    captured = {}

    def fake_metrics(s, e):
        captured["metrics_start"] = s
        return METRICS

    def fake_workouts(s, e):
        captured["workouts_start"] = s
        return WORKOUTS

    monkeypatch.setattr(daily_metrics_repo, "get_range", fake_metrics)
    monkeypatch.setattr(workouts_repo, "get_range", fake_workouts)

    assert dashboard_service.metrics_series(days=None) == METRICS
    assert dashboard_service.workouts_series(days=None) == WORKOUTS
    assert captured["metrics_start"] == "2000-01-01"
    assert captured["workouts_start"] == "2000-01-01"


def test_training_load_acwr(monkeypatch):
    from datetime import date, timedelta

    day0 = (date.today() - timedelta(days=9)).isoformat()
    monkeypatch.setattr(
        workouts_repo, "get_range", lambda s, e: [{"date": day0, "distance_km": 14.0}]
    )

    result = dashboard_service.training_load(days=30)

    assert result["ok"] is True
    rows = result["rows"]
    assert len(rows) == 10  # day0 .. today inclusive
    first, last = rows[0], rows[-1]
    # Day 1: acute and chronic windows both contain only the 14 km -> ratio 1.
    assert first["load_km"] == 14.0
    assert first["acwr"] == 1.0
    # Today: nothing in the last 7 days (acute 0), chronic 14/10 -> ratio 0.
    assert last["load_km"] == 0.0
    assert last["acute"] == 0.0
    assert last["chronic"] == 1.4
    assert last["acwr"] == 0.0


def test_training_load_handles_no_distance_and_empty(monkeypatch):
    from datetime import date, timedelta

    day0 = (date.today() - timedelta(days=1)).isoformat()
    # A strength workout with no distance -> zero load -> chronic 0 -> no ratio.
    monkeypatch.setattr(
        workouts_repo, "get_range", lambda s, e: [{"date": day0, "distance_km": None}]
    )
    rows = dashboard_service.training_load()["rows"]
    assert rows[0]["acwr"] is None

    monkeypatch.setattr(workouts_repo, "get_range", lambda s, e: [])
    assert dashboard_service.training_load() == {"ok": True, "rows": []}


def test_training_load_failure(monkeypatch):
    monkeypatch.setattr(
        workouts_repo, "get_range", lambda s, e: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    result = dashboard_service.training_load()
    assert result["ok"] is False
    assert "db down" in result["error"]


def test_zone_distribution_easy_hard_split(monkeypatch):
    from repositories import goals_repo

    # 3:45 marathon goal -> marathon pace 5:20/km; easy 6:08, threshold 4:54.
    monkeypatch.setattr(
        goals_repo, "get_active",
        lambda: {"sport": "running", "goal_time_seconds": 13500},
    )
    runs = [
        {"date": "2026-06-01", "sport": "running", "distance_km": 10.0,
         "duration_seconds": 3700},  # 6:10/km -> easy
        {"date": "2026-06-03", "sport": "running", "distance_km": 8.0,
         "duration_seconds": 3240},  # 6:45/km -> recovery
        {"date": "2026-06-05", "sport": "running", "distance_km": 6.0,
         "duration_seconds": 1770},  # 4:55/km -> threshold
        {"date": "2026-06-05", "sport": "cycling", "distance_km": 40.0,
         "duration_seconds": 5000},  # not a run -> ignored
    ]
    monkeypatch.setattr(workouts_repo, "get_range", lambda s, e: runs)

    result = dashboard_service.zone_distribution(days=28)

    assert result["ok"] is True
    by_zone = {r["zone"]: r["km"] for r in result["rows"]}
    assert by_zone["easy"] == 10.0
    assert by_zone["recovery"] == 8.0
    assert by_zone["threshold"] == 6.0
    assert result["easy_pct"] == 75  # (10 + 8) / 24
    assert result["total_km"] == 24.0


def test_zone_distribution_without_goal(monkeypatch):
    from repositories import goals_repo

    monkeypatch.setattr(goals_repo, "get_active", lambda: None)
    result = dashboard_service.zone_distribution()
    assert result["ok"] is True
    assert result["rows"] == []
    assert result["easy_pct"] is None
