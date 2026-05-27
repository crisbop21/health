"""Garmin client and sync service, with the Garmin API and repo mocked."""

from __future__ import annotations

from clients import garmin_client
from repositories import garmin_raw_repo
from services import sync_service


class FakeGarmin:
    def get_activities_by_date(self, start, end, *a, **k):
        return [{"activityId": 1, "start": start, "end": end}]

    def get_stats(self, day):
        return {"date": day, "steps": 8000}

    def get_sleep_data(self, day):
        return {"date": day, "sleep_hours": 7.5}

    def get_hrv_data(self, day):
        return {"date": day, "hrv_ms": 62}

    def get_rhr_day(self, day):
        return {"date": day, "resting_hr": 48}


def test_fetch_recent_activities(monkeypatch):
    monkeypatch.setattr(garmin_client, "login", lambda: FakeGarmin())
    acts = garmin_client.fetch_recent_activities(days=7)
    assert len(acts) == 1
    assert acts[0]["activityId"] == 1


def test_fetch_daily_stats_bundles_endpoints():
    stats = garmin_client.fetch_daily_stats("2026-05-27", client=FakeGarmin())
    assert stats["date"] == "2026-05-27"
    assert stats["stats"]["steps"] == 8000
    assert stats["sleep"]["sleep_hours"] == 7.5
    assert stats["hrv"]["hrv_ms"] == 62
    assert stats["resting_hr"]["resting_hr"] == 48


def test_daily_stats_one_endpoint_failure_is_isolated():
    class PartialGarmin(FakeGarmin):
        def get_hrv_data(self, day):
            raise RuntimeError("garmin hiccup")

    stats = garmin_client.fetch_daily_stats("2026-05-27", client=PartialGarmin())
    assert stats["hrv"] is None  # failed endpoint -> None, others intact
    assert stats["stats"]["steps"] == 8000


def test_sync_writes_raw_rows(monkeypatch):
    monkeypatch.setattr(garmin_client, "login", lambda: FakeGarmin())
    inserts = []
    monkeypatch.setattr(
        garmin_raw_repo,
        "insert",
        lambda payload, endpoint, recorded_at=None: inserts.append((endpoint, payload)),
    )

    result = sync_service.sync_garmin_last_7_days()

    assert result["ok"] is True
    assert result["rows_written"] == 8  # 1 activities + 7 daily_stats
    endpoints = [e for e, _ in inserts]
    assert endpoints.count("activities") == 1
    assert endpoints.count("daily_stats") == 7


def test_sync_handles_login_failure_gracefully(monkeypatch):
    def boom():
        raise RuntimeError("bad password")

    monkeypatch.setattr(garmin_client, "login", boom)
    result = sync_service.sync_garmin_last_7_days()
    assert result["ok"] is False
    assert "bad password" in result["error"]
