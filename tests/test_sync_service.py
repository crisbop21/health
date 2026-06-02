"""Whoop and all-device sync orchestration, with clients and repos mocked."""

from __future__ import annotations

from clients import garmin_client, whoop_client
from repositories import garmin_raw_repo, whoop_raw_repo
from services import sync_service


def test_sync_whoop_writes_four_endpoints(monkeypatch):
    monkeypatch.setattr(whoop_client, "fetch_recoveries", lambda s, e: {"records": [{"id": 1}]})
    monkeypatch.setattr(whoop_client, "fetch_sleeps", lambda s, e: {"records": [{"id": 2}]})
    monkeypatch.setattr(whoop_client, "fetch_workouts", lambda s, e: {"records": [{"id": 3}]})
    monkeypatch.setattr(whoop_client, "fetch_cycles", lambda s, e: {"records": [{"id": 4}]})
    upserts = []
    monkeypatch.setattr(
        whoop_raw_repo,
        "upsert_records",
        lambda records, endpoint, recorded_at=None: upserts.append(endpoint) or len(records),
    )

    result = sync_service.sync_whoop_last_7_days()

    assert result["ok"] is True
    assert result["rows_written"] == 4
    assert set(upserts) == {"recovery", "sleep", "workout", "cycle"}


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
    # One record per window so the per-record upsert count is deterministic.
    for name in ("fetch_recoveries", "fetch_sleeps", "fetch_workouts", "fetch_cycles"):
        monkeypatch.setattr(whoop_client, name, lambda s, e: {"records": [{"id": s}]})
    upserts = []
    monkeypatch.setattr(
        whoop_raw_repo,
        "upsert_records",
        lambda records, endpoint, recorded_at=None: upserts.append(endpoint) or len(records),
    )

    result = sync_service.sync_whoop_range(days=365)

    # 13 windows per endpoint across 4 endpoints, one record each.
    assert result["ok"] is True
    assert result["rows_written"] == 13 * 4
    assert upserts.count("recovery") == 13


def test_sync_garmin_range_loops_days(monkeypatch):
    monkeypatch.setattr(garmin_client, "login", lambda: object())
    monkeypatch.setattr(
        garmin_client, "fetch_recent_activities", lambda days, client=None: []
    )
    monkeypatch.setattr(
        garmin_client, "fetch_daily_stats", lambda day, client=None: {"date": day}
    )
    upserts = []
    monkeypatch.setattr(
        garmin_raw_repo,
        "upsert_records",
        lambda records, endpoint, key_field, recorded_at=None: upserts.append(endpoint) or len(records),
    )

    result = sync_service.sync_garmin_range(days=30)

    # No activities; one daily_stats record upserted per day.
    assert result["ok"] is True
    assert result["rows_written"] == 30
    assert result["failed_days"] == 0
    assert upserts.count("daily_stats") == 30


def test_sync_garmin_range_skips_failed_days(monkeypatch):
    monkeypatch.setattr(garmin_client, "login", lambda: object())
    monkeypatch.setattr(garmin_client, "fetch_recent_activities", lambda days, client=None: [])

    def flaky(day, client=None):
        if day.endswith("1"):  # fail on days ending in 1
            raise RuntimeError("429 rate limited")
        return {"date": day}

    monkeypatch.setattr(garmin_client, "fetch_daily_stats", flaky)
    monkeypatch.setattr(
        garmin_raw_repo,
        "upsert_records",
        lambda records, endpoint, key_field, recorded_at=None: len(records),
    )

    result = sync_service.sync_garmin_range(days=10)

    # Still ok overall; failed days counted, not fatal.
    assert result["ok"] is True
    assert result["failed_days"] >= 1
    assert result["rows_written"] == 10 - result["failed_days"]


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
