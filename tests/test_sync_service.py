"""Whoop and all-device sync orchestration, with clients and repos mocked."""

from __future__ import annotations

from clients import garmin_client, whoop_client
from repositories import garmin_raw_repo, whoop_raw_repo
from services import sync_service


def test_sync_whoop_writes_four_endpoints(monkeypatch):
    monkeypatch.setattr(whoop_client, "fetch_recoveries", lambda s, e: {"records": [1]})
    monkeypatch.setattr(whoop_client, "fetch_sleeps", lambda s, e: {"records": [2]})
    monkeypatch.setattr(whoop_client, "fetch_workouts", lambda s, e: {"records": [3]})
    monkeypatch.setattr(whoop_client, "fetch_cycles", lambda s, e: {"records": [4]})
    inserts = []
    monkeypatch.setattr(
        whoop_raw_repo,
        "insert",
        lambda payload, endpoint, recorded_at=None: inserts.append(endpoint),
    )

    result = sync_service.sync_whoop_last_7_days()

    assert result["ok"] is True
    assert result["rows_written"] == 4
    assert set(inserts) == {"recovery", "sleep", "workout", "cycle"}


def test_sync_whoop_failure_is_graceful(monkeypatch):
    def boom(s, e):
        raise RuntimeError("token expired")

    monkeypatch.setattr(whoop_client, "fetch_recoveries", boom)
    result = sync_service.sync_whoop_last_7_days()
    assert result["ok"] is False
    assert "token expired" in result["error"]


def test_sync_all_devices_combines(monkeypatch):
    monkeypatch.setattr(
        sync_service, "sync_garmin_range", lambda days=7: {"ok": True, "rows_written": 8}
    )
    monkeypatch.setattr(
        sync_service, "sync_whoop_range", lambda days=7: {"ok": False, "error": "no whoop"}
    )

    result = sync_service.sync_all_devices()

    assert result["ok"] is False  # one device failed
    assert result["garmin"]["rows_written"] == 8
    assert result["whoop"]["error"] == "no whoop"


def test_whoop_windows_span_full_range_without_overlap():
    windows = list(sync_service._whoop_windows(365, window=30))
    # A year split into 30-day slices -> 13 windows, contiguous and ordered.
    assert len(windows) == 13
    for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
        assert next_start[:10] > prev_end[:10]  # no overlap, strictly increasing


def test_sync_whoop_range_chunks_each_endpoint(monkeypatch):
    calls = []
    for name in ("fetch_recoveries", "fetch_sleeps", "fetch_workouts", "fetch_cycles"):
        monkeypatch.setattr(
            whoop_client, name, lambda s, e: calls.append((s, e)) or {"records": []}
        )
    inserts = []
    monkeypatch.setattr(
        whoop_raw_repo,
        "insert",
        lambda payload, endpoint, recorded_at=None: inserts.append(endpoint),
    )

    result = sync_service.sync_whoop_range(days=365)

    # 13 windows per endpoint across 4 endpoints.
    assert result["ok"] is True
    assert result["rows_written"] == 13 * 4
    assert inserts.count("recovery") == 13


def test_sync_garmin_range_loops_days(monkeypatch):
    monkeypatch.setattr(garmin_client, "login", lambda: object())
    monkeypatch.setattr(
        garmin_client, "fetch_recent_activities", lambda days, client=None: []
    )
    monkeypatch.setattr(
        garmin_client, "fetch_daily_stats", lambda day, client=None: {"date": day}
    )
    inserts = []
    monkeypatch.setattr(
        garmin_raw_repo,
        "insert",
        lambda payload, endpoint, recorded_at=None: inserts.append(endpoint),
    )

    result = sync_service.sync_garmin_range(days=30)

    # One activities row + one daily_stats row per day.
    assert result["ok"] is True
    assert result["rows_written"] == 1 + 30
    assert inserts.count("daily_stats") == 30


def test_backfill_defaults_to_a_year(monkeypatch):
    captured = {}

    def fake_garmin(days):
        captured["garmin"] = days
        return {"ok": True}

    def fake_whoop(days):
        captured["whoop"] = days
        return {"ok": True}

    monkeypatch.setattr(sync_service, "sync_garmin_range", fake_garmin)
    monkeypatch.setattr(sync_service, "sync_whoop_range", fake_whoop)

    result = sync_service.backfill_all_devices()

    assert result["ok"] is True
    assert captured["garmin"] == 365
    assert captured["whoop"] == 365
