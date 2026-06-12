"""Whoop and all-device sync orchestration, with clients and repos mocked."""

from __future__ import annotations

from datetime import date, timedelta

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
        sync_service, "sync_garmin_range", lambda days=7, **kw: {"ok": True, "rows_written": 8}
    )
    monkeypatch.setattr(
        sync_service, "sync_whoop_range", lambda days=7, **kw: {"ok": False, "error": "no whoop"}
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


def test_sync_garmin_range_reports_progress(monkeypatch):
    """The UI shows a progress bar during long backfills; the service reports
    (done, total) after each day's stats."""
    monkeypatch.setattr(garmin_client, "login", lambda: object())
    monkeypatch.setattr(garmin_client, "fetch_recent_activities", lambda days, client=None: [])
    monkeypatch.setattr(garmin_client, "fetch_daily_stats", lambda day, client=None: {"date": day})
    monkeypatch.setattr(
        garmin_raw_repo,
        "upsert_records",
        lambda records, endpoint, key_field, recorded_at=None: len(records),
    )
    seen = []

    result = sync_service.sync_garmin_range(days=5, on_progress=lambda d, t: seen.append((d, t)))

    assert result["ok"] is True
    assert seen == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]


def test_backfill_skips_days_already_stored(monkeypatch):
    """A re-run after rate limiting should only fetch the gaps, not re-pull
    every day's four endpoints."""
    monkeypatch.setattr(garmin_client, "login", lambda: object())
    monkeypatch.setattr(garmin_client, "fetch_recent_activities", lambda days, client=None: [])
    fetched = []
    monkeypatch.setattr(
        garmin_client, "fetch_daily_stats",
        lambda day, client=None: fetched.append(day) or {"date": day},
    )
    stored_day = (date.today() - timedelta(days=1)).isoformat()
    monkeypatch.setattr(garmin_raw_repo, "existing_ids", lambda endpoint: {stored_day})
    monkeypatch.setattr(
        garmin_raw_repo, "upsert_records",
        lambda records, endpoint, key_field, recorded_at=None: len(records),
    )
    seen = []

    result = sync_service.sync_garmin_range(
        days=3, skip_existing=True, on_progress=lambda d, t: seen.append((d, t))
    )

    assert result["ok"] is True
    assert stored_day not in fetched and len(fetched) == 2
    assert result["skipped_days"] == 1
    assert seen == [(1, 3), (2, 3), (3, 3)]  # progress still covers every day


def test_routine_sync_never_skips_stored_days(monkeypatch):
    """The default path re-pulls recent days so edits/late data refresh."""
    monkeypatch.setattr(garmin_client, "login", lambda: object())
    monkeypatch.setattr(garmin_client, "fetch_recent_activities", lambda days, client=None: [])
    monkeypatch.setattr(garmin_client, "fetch_daily_stats", lambda day, client=None: {"date": day})
    monkeypatch.setattr(
        garmin_raw_repo, "existing_ids",
        lambda endpoint: (_ for _ in ()).throw(AssertionError("must not be queried")),
    )
    monkeypatch.setattr(
        garmin_raw_repo, "upsert_records",
        lambda records, endpoint, key_field, recorded_at=None: len(records),
    )

    result = sync_service.sync_garmin_range(days=2)

    assert result["ok"] is True
    assert result["rows_written"] == 2


def test_backfill_passes_skip_existing(monkeypatch):
    captured = {}

    def fake_garmin(days, on_progress=None, skip_existing=False):
        captured["skip_existing"] = skip_existing
        return {"ok": True}

    monkeypatch.setattr(sync_service, "sync_garmin_range", fake_garmin)
    monkeypatch.setattr(sync_service, "sync_whoop_range", lambda days, **kw: {"ok": True})

    sync_service.backfill_all_devices(days=90)

    assert captured["skip_existing"] is True


def test_device_status_reports_counts_and_last_sync(monkeypatch):
    monkeypatch.setattr(garmin_raw_repo, "latest_ingested_at", lambda: "2026-06-01T06:30:00")
    monkeypatch.setattr(garmin_raw_repo, "count", lambda: 1234)
    monkeypatch.setattr(whoop_raw_repo, "latest_ingested_at", lambda: "2026-06-02T06:30:00")
    monkeypatch.setattr(whoop_raw_repo, "count", lambda: 567)
    monkeypatch.setattr(whoop_client, "is_connected", lambda: True)
    monkeypatch.setattr(whoop_client, "token_expiry", lambda: "2026-06-02T08:00:00")

    status = sync_service.device_status()

    assert status["garmin"] == {"last_sync": "2026-06-01T06:30:00", "rows": 1234}
    assert status["whoop"] == {
        "connected": True, "last_sync": "2026-06-02T06:30:00", "rows": 567,
        "token_expires_at": "2026-06-02T08:00:00",
    }


def test_device_status_survives_db_failure(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("db down")

    for repo in (garmin_raw_repo, whoop_raw_repo):
        monkeypatch.setattr(repo, "latest_ingested_at", boom)
        monkeypatch.setattr(repo, "count", boom)
    monkeypatch.setattr(whoop_client, "is_connected", boom)
    monkeypatch.setattr(whoop_client, "token_expiry", boom)

    status = sync_service.device_status()  # must not raise into the UI

    assert status["garmin"] == {"last_sync": None, "rows": None}
    assert status["whoop"] == {
        "connected": False, "last_sync": None, "rows": None, "token_expires_at": None,
    }


def test_backfill_defaults_to_a_year(monkeypatch):
    captured = {}

    def fake_garmin(days, **kw):
        captured["garmin"] = days
        return {"ok": True}

    def fake_whoop(days, **kw):
        captured["whoop"] = days
        return {"ok": True}

    monkeypatch.setattr(sync_service, "sync_garmin_range", fake_garmin)
    monkeypatch.setattr(sync_service, "sync_whoop_range", fake_whoop)

    result = sync_service.backfill_all_devices()

    assert result["ok"] is True
    assert captured["garmin"] == 365
    assert captured["whoop"] == 365
